#!/usr/bin/env python3
"""
DCAD Scraper — Dallas County Central Appraisal District
Scrapes property records to find pre-1980 teardown candidates for land flipping.

Target buyer box:
  - ZIPs: 75230, 75229, 75220, 75218, 75214, 75206, 75225, 75212
  - Lot size: 8,000+ sq ft
  - Built: before 1980
  - Improvement value < 20% of land value (teardown indicator)
  - Budget: $350K-$450K land value
  - ARV: $1.8M

Usage:
  python dcad-scraper-v2.py --zip 75230 --street "Maple" --output leads.csv
  python dcad-scraper-v2.py --auto-streets --zip 75230 --max-pages 5 --output leads.csv
  python dcad-scraper-v2.py --batch addresses.txt --output leads.csv
  python dcad-scraper-v2.py --delinquent --zip 75230 --output delinquent.csv
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlencode, parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
DCAD_BASE = "https://www.dallascad.org"
DCAD_SEARCH_ADDR = f"{DCAD_BASE}/SearchAddr.aspx"
DCAD_SEARCH_OWNER = f"{DCAD_BASE}/SearchOwner.aspx"
DCAD_SEARCH_ACCT = f"{DCAD_BASE}/SearchAcct.aspx"
DCAD_DETAIL = f"{DCAD_BASE}/AccountDetail.aspx"
DCAD_GIS = "https://maps.dcad.org/prd/dpm/"

TARGET_ZIPS = ["75230", "75229", "75220", "75218", "75214", "75206", "75225", "75212"]
MIN_LOT_SIZE = 8000  # sq ft
MAX_YEAR_BUILT = 1980
MAX_IMPROVEMENT_RATIO = 0.20  # improvement value / land value
BUDGET_MIN = 350000
BUDGET_MAX = 450000

# Street names for auto-search mode
DALLAS_STREETS = [
    "Oak", "Maple", "Elm", "Pine", "Cedar", "Birch", "Willow", "Magnolia",
    "Peachtree", "Dogwood", "Hickory", "Ash", "Cherry", "Walnut", "Chestnut",
    "Main", "Broadway", "Park", "Lake", "Forest", "Highland", "Meadow",
    "Ridge", "Valley", "Hill", "Grove", "Court", "Place", "Circle",
    "Drive", "Lane", "Road", "Street", "Avenue", "Boulevard", "Way",
    "Trail", "Path", "Terrace", "Heights", "View", "Crest", "Gardens",
    "Knoll", "Point", "Shores", "Springs", "Glen", "Woods", "Fields",
    "Hollow", "Run", "Creek", "Brook", "Bridge", "Crossing", "Landing",
    "Parkway", "Expressway", "Freeway", "Highway", "Turnpike", "Tollway",
    "Preston", "Royal", "Lovers", "Mockingbird", "Skillman", "Abrams",
    "Garland", "Ross", "Fitzhugh", "Peak", "McKinney", "Knox", "Henderson",
    "Greenville", "Bishop", "Travis", "Live Oak", "Harwood", "Cole",
    "Reunion", "Lemmon", "Inwood", "Northwest", "Munger", "Sylvan",
    "Fort Worth", "Davis", "Jefferson", "Cadiz", "Colorado", "Beckley",
    "Polk", "Clinton", "Edgefield", "Montclair", "Kessler", "Stevens",
    "Hampton", "Westmoreland", "Pioneer", "Commerce", "Pacific", "Jackson",
    "Young", "Record", "Akard", "Ervay", "Field", "Howell", "Julius",
    "Scyene", "Bruton", "Buckner", "Jim Miller", "Lake June", "Prairie",
    "Spring", "Miller", "Corinth", "Carroll", "Keller", "Gaston",
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────
@dataclass
class DCADProperty:
    """Single property record from DCAD."""
    account_number: str = ""
    property_address: str = ""
    zip_code: str = ""
    owner_name: str = ""
    mailing_address: str = ""
    mailing_city: str = ""
    mailing_state: str = ""
    mailing_zip: str = ""
    is_absentee_owner: bool = False
    lot_size_sqft: int = 0
    year_built: int = 0
    land_value: int = 0
    improvement_value: int = 0
    total_value: int = 0
    improvement_ratio: float = 0.0
    tax_status: str = ""
    is_tax_delinquent: bool = False
    property_type: str = ""
    legal_description: str = ""
    neighborhood: str = ""
    score: str = "C"
    score_reasons: List[str] = field(default_factory=list)
    search_zip: str = ""
    search_street: str = ""
    scraped_at: str = ""
    dcad_url: str = ""
    # Deal analysis
    land_value_estimate: int = 0
    potential_profit: int = 0
    meets_budget: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["score_reasons"] = "; ".join(d["score_reasons"])
        return d


# ──────────────────────────────────────────────
# Session / HTTP
# ──────────────────────────────────────────────
class DCADSession:
    """Authenticated session wrapper for DCAD."""

    def __init__(self, proxy: Optional[str] = None, delay: float = 1.5):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.delay = delay
        self.logger = logging.getLogger("DCAD")

    def _sleep(self, multiplier: float = 1.0):
        time.sleep(self.delay * multiplier + random.uniform(0.3, 1.0))

    def get(self, url: str, **kwargs) -> requests.Response:
        self._sleep()
        try:
            resp = self.session.get(url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            self.logger.error(f"Request failed: {url} — {e}")
            raise

    def post(self, url: str, data: dict = None, **kwargs) -> requests.Response:
        self._sleep()
        try:
            resp = self.session.post(url, data=data, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            self.logger.error(f"POST failed: {url} — {e}")
            raise


# ──────────────────────────────────────────────
# Scraper
# ──────────────────────────────────────────────
class DCADScraper:
    """Scrape DCAD property search for teardown candidates."""

    def __init__(self, proxy: Optional[str] = None, delay: float = 1.5):
        self.http = DCADSession(proxy=proxy, delay=delay)
        self.logger = logging.getLogger("DCAD")
        self.results: List[DCADProperty] = []
        self.seen_accounts: set = set()
        # Fetch once for cookies/viewstate
        self._init_search_page()

    def _init_search_page(self):
        """Load search page to grab any cookies/csrf tokens."""
        try:
            resp = self.http.get(DCAD_SEARCH_ADDR)
            self._last_search_soup = BeautifulSoup(resp.text, "html.parser")
            self.logger.debug("Initialized search page session")
        except Exception as e:
            self.logger.warning(f"Could not init search page: {e}")
            self._last_search_soup = None

    def _get_viewstate(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract ASP.NET form fields."""
        fields = {}
        for field in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
            tag = soup.find("input", {"name": field})
            if tag:
                fields[field] = tag.get("value", "")
        return fields

    def search_by_address(
        self,
        street_name: str,
        zip_code: Optional[str] = None,
        address_num: Optional[str] = None,
        direction: Optional[str] = None,
        max_results: int = 100
    ) -> List[DCADProperty]:
        """
        Search DCAD by address components.
        Returns list of DCADProperty objects (detail pages parsed).
        """
        query = f"{street_name} {zip_code or ''}".strip()
        self.logger.info(f"Searching DCAD: {query}")

        try:
            # Get fresh search page
            resp = self.http.get(DCAD_SEARCH_ADDR)
            soup = BeautifulSoup(resp.text, "html.parser")
            form_data = self._get_viewstate(soup)

            # Build form data for address search
            form_data.update({
                "txtStreetName": street_name,
                "ddlAccountType": "RESIDENTIAL",
                "btnSearch": "Search",
            })
            if address_num:
                form_data["txtAddressNum"] = address_num
            if direction:
                form_data["ddlDirection"] = direction
            if zip_code:
                form_data["txtCity"] = zip_code  # DCAD uses city field for ZIP sometimes

            resp = self.http.post(DCAD_SEARCH_ADDR, data=form_data)
            return self._parse_search_results(resp.text, query)

        except Exception as e:
            self.logger.error(f"Search failed for {query}: {e}")
            return []

    def search_by_owner(self, owner_name: str, zip_code: Optional[str] = None) -> List[DCADProperty]:
        """Search by owner name."""
        self.logger.info(f"Searching owner: {owner_name}")
        try:
            resp = self.http.get(DCAD_SEARCH_OWNER)
            soup = BeautifulSoup(resp.text, "html.parser")
            form_data = self._get_viewstate(soup)
            form_data.update({
                "txtOwnerName": owner_name,
                "ddlAccountType": "RESIDENTIAL",
                "btnSearch": "Search",
            })
            resp = self.http.post(DCAD_SEARCH_OWNER, data=form_data)
            return self._parse_search_results(resp.text, f"owner:{owner_name}")
        except Exception as e:
            self.logger.error(f"Owner search failed: {e}")
            return []

    def search_by_account(self, account_num: str) -> Optional[DCADProperty]:
        """Lookup a single property by account number."""
        self.logger.info(f"Account lookup: {account_num}")
        try:
            url = f"{DCAD_DETAIL}?ID={account_num}"
            resp = self.http.get(url)
            return self._parse_detail_page(resp.text, account_num, url)
        except Exception as e:
            self.logger.error(f"Account lookup failed: {e}")
            return None

    def _parse_search_results(self, html: str, query: str) -> List[DCADProperty]:
        """Parse the search results table."""
        soup = BeautifulSoup(html, "html.parser")
        properties = []

        # Find results table
        table = soup.find("table", {"id": re.compile(r"grdResults|gvResults|Results", re.I)})
        if not table:
            table = soup.find("table", class_=re.compile(r"result|data|grid", re.I))
        if not table:
            # Try any table with rows
            table = soup.find("table")

        if not table:
            self.logger.warning(f"No results table found for: {query}")
            return []

        rows = table.find_all("tr")
        self.logger.info(f"Found {len(rows)} rows for: {query}")

        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            # Look for account link
            account_link = None
            for cell in cells:
                link = cell.find("a", href=re.compile(r"AccountDetail|ID=", re.I))
                if link:
                    account_link = link
                    break

            if not account_link:
                continue

            href = account_link.get("href", "")
            account_num = re.search(r"ID=(\d+)", href)
            if account_num:
                account_num = account_num.group(1)
            else:
                account_num = re.search(r"\d+", account_link.text)
                if account_num:
                    account_num = account_num.group()
                else:
                    continue

            if account_num in self.seen_accounts:
                continue
            self.seen_accounts.add(account_num)

            # Parse detail page
            detail_url = href if href.startswith("http") else f"{DCAD_BASE}/{href}"
            try:
                resp = self.http.get(detail_url)
                prop = self._parse_detail_page(resp.text, account_num, detail_url, query)
                if prop:
                    properties.append(prop)
            except Exception as e:
                self.logger.debug(f"Error parsing detail for {account_num}: {e}")
                continue

        return properties

    def _parse_detail_page(
        self,
        html: str,
        account_num: str,
        url: str,
        query: str = ""
    ) -> Optional[DCADProperty]:
        """Parse a property detail page."""
        soup = BeautifulSoup(html, "html.parser")
        prop = DCADProperty()
        prop.account_number = account_num
        prop.dcad_url = url
        prop.scraped_at = datetime.now().isoformat()

        # Parse query components
        parts = query.split()
        if parts and parts[-1].isdigit() and len(parts[-1]) == 5:
            prop.search_zip = parts[-1]
            prop.search_street = " ".join(parts[:-1])
        else:
            prop.search_street = query

        # ── Extract all fields ──
        text_map = self._extract_label_value_pairs(soup)

        prop.owner_name = text_map.get("owner", text_map.get("owner name", ""))
        prop.property_address = text_map.get(
            "property address",
            text_map.get("situs address", text_map.get("address", ""))
        )
        prop.mailing_address = text_map.get("mailing address", "")
        prop.mailing_city = text_map.get("mailing city", "")
        prop.mailing_state = text_map.get("mailing state", "")
        prop.mailing_zip = text_map.get("mailing zip", "")

        # Extract ZIP from property address
        zip_match = re.search(r'(\d{5}(?:-\d{4})?)', prop.property_address)
        if zip_match:
            prop.zip_code = zip_match.group(1)[:5]

        # Lot size
        lot_text = text_map.get("lot size", text_map.get("total sq ft", text_map.get("acreage", "")))
        prop.lot_size_sqft = self._parse_area(lot_text)

        # Year built
        year_text = text_map.get("year built", text_map.get("yr blt", ""))
        prop.year_built = self._parse_year(year_text)

        # Values
        prop.land_value = self._parse_money(text_map.get("land value", text_map.get("land", "")))
        prop.improvement_value = self._parse_money(text_map.get("improvement value", text_map.get("building value", "")))
        prop.total_value = self._parse_money(text_map.get("total value", text_map.get("total appraised", "")))

        # Tax status
        prop.tax_status = text_map.get("tax status", "")
        prop.is_tax_delinquent = "delinquent" in prop.tax_status.lower()

        # Property type
        prop.property_type = text_map.get("property type", text_map.get("type", ""))

        # Legal description
        prop.legal_description = text_map.get("legal description", "")

        # Neighborhood
        prop.neighborhood = text_map.get("neighborhood", text_map.get("nbhd", ""))

        # ── Calculate metrics ──
        if prop.land_value > 0:
            prop.improvement_ratio = prop.improvement_value / prop.land_value

        prop.meets_budget = BUDGET_MIN <= prop.land_value <= BUDGET_MAX

        # Estimate potential profit (wholesale flip model)
        if prop.land_value > 0:
            # Typical assignment fee model: contract at 70-80% of market
            prop.land_value_estimate = int(prop.total_value * 0.85)
            prop.potential_profit = prop.land_value_estimate - prop.land_value

        # Absentee owner check
        if prop.mailing_address and prop.property_address:
            prop_street = re.sub(r'\s+', ' ', prop.property_address.lower())
            mail_street = re.sub(r'\s+', ' ', prop.mailing_address.lower())
            # Simple check: if mailing doesn't contain property street number
            street_num = re.search(r'^(\d+)', prop.property_address)
            if street_num and street_num.group() not in prop.mailing_address:
                prop.is_absentee_owner = True
            elif prop.zip_code and prop.mailing_zip and prop.zip_code != prop.mailing_zip[:5]:
                prop.is_absentee_owner = True

        # ── Score ──
        prop.score, prop.score_reasons = self._score_property(prop)

        self.logger.info(
            f"Parsed: {prop.property_address or account_num} | "
            f"Owner: {prop.owner_name[:30] if prop.owner_name else 'N/A'} | "
            f"Lot: {prop.lot_size_sqft:,} | Year: {prop.year_built} | "
            f"Land: ${prop.land_value:,} | Score: {prop.score}"
        )
        return prop

    def _extract_label_value_pairs(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract label-value pairs from DCAD detail pages.
        Handles various layouts: table rows, definition lists, div pairs.
        """
        text_map = {}

        # Method 1: Table rows with label/value cells
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(strip=True)
                if label and value:
                    text_map[label.lower()] = value

        # Method 2: Definition lists
        for dt, dd in zip(soup.find_all("dt"), soup.find_all("dd")):
            label = dt.get_text(strip=True).rstrip(":").lower()
            value = dd.get_text(strip=True)
            if label and value:
                text_map[label] = value

        # Method 3: Div/spans with label classes
        for elem in soup.find_all(["div", "span", "label"]):
            text = elem.get_text(strip=True)
            if ":" in text and len(text) < 100:
                parts = text.split(":", 1)
                if len(parts) == 2:
                    label = parts[0].strip().lower()
                    value = parts[1].strip()
                    if label and value:
                        text_map[label] = value

        return text_map

    @staticmethod
    def _parse_money(text: str) -> int:
        """Extract dollar amount from text."""
        if not text:
            return 0
        # Remove $, commas, spaces; keep digits and decimal
        cleaned = re.sub(r'[$,\s]', '', text)
        match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if match:
            return int(float(match.group()))
        return 0

    @staticmethod
    def _parse_area(text: str) -> int:
        """Extract square footage from text."""
        if not text:
            return 0
        # Look for number followed by sq ft, sf, acres
        sqft_match = re.search(r'(\d[\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?|sf|square\s*feet)', text, re.I)
        if sqft_match:
            return int(float(sqft_match.group(1).replace(',', '')))
        # Acres
        acre_match = re.search(r'(\d[\d,]*(?:\.\d+)?)\s*(?:acres?|ac)', text, re.I)
        if acre_match:
            return int(float(acre_match.group(1).replace(',', '')) * 43560)
        # Just a number
        num_match = re.search(r'(\d[\d,]+)', text)
        if num_match:
            return int(num_match.group(1).replace(',', ''))
        return 0

    @staticmethod
    def _parse_year(text: str) -> int:
        """Extract year built from text."""
        if not text:
            return 0
        match = re.search(r'(19\d{2}|20\d{2})', text)
        if match:
            return int(match.group())
        return 0

    def _score_property(self, prop: DCADProperty) -> Tuple[str, List[str]]:
        """
        Score property A/B/C based on buyer box fit.
        A = Tax delinquent + absentee owner = HOT
        B = Absentee owner or good fit = WARM
        C = Local owner or doesn't match = COLD
        """
        reasons = []
        score = "C"

        # Buyer box checks
        fits_lot = prop.lot_size_sqft >= MIN_LOT_SIZE
        fits_year = 0 < prop.year_built <= MAX_YEAR_BUILT
        fits_ratio = prop.improvement_ratio <= MAX_IMPROVEMENT_RATIO or prop.improvement_value == 0
        in_target_zip = prop.zip_code in TARGET_ZIPS
        fits_budget = prop.meets_budget

        if fits_lot:
            reasons.append(f"Lot {prop.lot_size_sqft:,} sq ft")
        if fits_year:
            reasons.append(f"Built {prop.year_built}")
        if fits_ratio:
            reasons.append(f"Imp ratio {prop.improvement_ratio:.0%}")
        if in_target_zip:
            reasons.append(f"ZIP {prop.zip_code}")
        if fits_budget:
            reasons.append(f"Land ${prop.land_value:,} (in budget)")

        # Scoring logic
        if prop.is_tax_delinquent:
            reasons.append("Tax delinquent")
            if prop.is_absentee_owner:
                score = "A"
                reasons.append("Absentee owner")
            else:
                score = "A"
        elif prop.is_absentee_owner:
            score = "B"
            reasons.append("Absentee owner")
        elif fits_lot and fits_year and fits_ratio and in_target_zip:
            score = "B"
            reasons.append("Buyer box fit")

        return score, reasons

    def search_zip_auto(self, zip_code: str, max_streets: int = 20, max_per_street: int = 10) -> List[DCADProperty]:
        """Auto-search a ZIP by cycling through common street names."""
        self.logger.info(f"Starting auto-search for ZIP {zip_code}")
        all_props = []
        streets = random.sample(DALLAS_STREETS, min(max_streets, len(DALLAS_STREETS)))

        for street in streets:
            props = self.search_by_address(street, zip_code=zip_code)
            all_props.extend(props)
            self.logger.info(f"  {street}: {len(props)} props (total: {len(all_props)})")
            if len(all_props) >= max_per_street * max_streets:
                break
        return all_props

    def search_batch(self, filepath: str) -> List[DCADProperty]:
        """Read addresses from file and look up each."""
        props = []
        path = Path(filepath)
        if not path.exists():
            self.logger.error(f"Batch file not found: {filepath}")
            return props

        with open(path, "r") as f:
            for line in f:
                addr = line.strip()
                if not addr or addr.startswith("#"):
                    continue
                results = self.search_by_address(addr)
                props.extend(results)
                self.logger.info(f"Batch: {addr} -> {len(results)} results")
        return props

    def get_delinquent_list(self, zip_code: Optional[str] = None) -> List[DCADProperty]:
        """
        Placeholder: Dallas County tax delinquent list requires
        manual request from Dallas County Tax Office: 214-653-7811
        """
        self.logger.warning(
            "Delinquent list requires manual request from Dallas County Tax Office. "
            "Call 214-653-7811 or visit https://www.dallascityhall.com/ "
            "Once obtained, use --batch to process."
        )
        return []

    def export_csv(self, filepath: str):
        """Export all results to CSV."""
        if not self.results:
            self.logger.warning("No results to export")
            return

        fieldnames = [
            "account_number", "property_address", "zip_code",
            "owner_name", "mailing_address", "mailing_city",
            "mailing_state", "mailing_zip", "is_absentee_owner",
            "lot_size_sqft", "year_built", "land_value",
            "improvement_value", "total_value", "improvement_ratio",
            "tax_status", "is_tax_delinquent", "property_type",
            "legal_description", "neighborhood",
            "score", "score_reasons",
            "land_value_estimate", "potential_profit", "meets_budget",
            "search_zip", "search_street", "scraped_at", "dcad_url",
        ]

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for prop in self.results:
                writer.writerow(prop.to_dict())

        self.logger.info(f"Exported {len(self.results)} properties to {filepath}")

    def export_json(self, filepath: str):
        """Export all results to JSON."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in self.results], f, indent=2)
        self.logger.info(f"Exported {len(self.results)} properties to {filepath}")

    def export_dashboard_json(self, filepath: str):
        """Export in the format expected by land-flip-dashboard."""
        dashboard_data = {
            "generated_at": datetime.now().isoformat(),
            "total_leads": len(self.results),
            "score_breakdown": {
                "A": sum(1 for p in self.results if p.score == "A"),
                "B": sum(1 for p in self.results if p.score == "B"),
                "C": sum(1 for p in self.results if p.score == "C"),
            },
            "by_zip": {},
            "properties": [p.to_dict() for p in self.results],
        }

        for prop in self.results:
            z = prop.zip_code or "unknown"
            dashboard_data["by_zip"][z] = dashboard_data["by_zip"].get(z, 0) + 1

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2)
        self.logger.info(f"Exported dashboard data to {filepath}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="DCAD Scraper v2 — Find teardown candidates in Dallas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search a specific street
  python dcad-scraper-v2.py --street "Preston" --zip 75230 --output leads.csv

  # Auto-search common streets in a ZIP
  python dcad-scraper-v2.py --auto-streets --zip 75230 --output leads.csv

  # Multiple ZIPs
  python dcad-scraper-v2.py --auto-streets --zip 75230 75229 75225 --output leads.csv

  # Batch from file
  python dcad-scraper-v2.py --batch addresses.txt --output leads.csv

  # Dashboard export
  python dcad-scraper-v2.py --auto-streets --zip 75230 --dashboard data/dcad-leads.json
        """
    )
    parser.add_argument("--zip", nargs="+", default=TARGET_ZIPS,
                        help="Target ZIP code(s)")
    parser.add_argument("--street", type=str,
                        help="Street name to search")
    parser.add_argument("--auto-streets", action="store_true",
                        help="Auto-search common street names")
    parser.add_argument("--batch", type=str, metavar="FILE",
                        help="File with one address per line")
    parser.add_argument("--owner", type=str,
                        help="Search by owner name")
    parser.add_argument("--account", type=str,
                        help="Lookup single account number")
    parser.add_argument("--output", "-o", type=str, default="dcad-leads.csv",
                        help="Output CSV filename")
    parser.add_argument("--json", type=str, metavar="FILE",
                        help="Also export to JSON")
    parser.add_argument("--dashboard", type=str, metavar="FILE",
                        help="Export dashboard-compatible JSON")
    parser.add_argument("--max-streets", type=int, default=20,
                        help="Max streets in auto mode (default: 20)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay between requests (default: 1.5s)")
    parser.add_argument("--proxy", type=str,
                        help="HTTP proxy (http://user:pass@host:port)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    logger = logging.getLogger("DCAD")

    scraper = DCADScraper(proxy=args.proxy, delay=args.delay)

    try:
        if args.account:
            prop = scraper.search_by_account(args.account)
            if prop:
                scraper.results.append(prop)

        elif args.owner:
            props = scraper.search_by_owner(args.owner)
            scraper.results.extend(props)

        elif args.batch:
            props = scraper.search_batch(args.batch)
            scraper.results.extend(props)

        elif args.auto_streets:
            for zip_code in args.zip:
                logger.info(f"Auto-streets mode for ZIP {zip_code}")
                props = scraper.search_zip_auto(zip_code, max_streets=args.max_streets)
                scraper.results.extend(props)

        elif args.street:
            for zip_code in args.zip:
                query = f"{args.street} {zip_code}"
                props = scraper.search_by_address(args.street, zip_code=zip_code)
                scraper.results.extend(props)

        else:
            parser.print_help()
            sys.exit(1)

        # Export
        if scraper.results:
            scraper.export_csv(args.output)
            if args.json:
                scraper.export_json(args.json)
            if args.dashboard:
                scraper.export_dashboard_json(args.dashboard)

            # Summary
            total = len(scraper.results)
            score_a = sum(1 for p in scraper.results if p.score == "A")
            score_b = sum(1 for p in scraper.results if p.score == "B")
            score_c = sum(1 for p in scraper.results if p.score == "C")
            absentee = sum(1 for p in scraper.results if p.is_absentee_owner)
            delinquent = sum(1 for p in scraper.results if p.is_tax_delinquent)
            in_budget = sum(1 for p in scraper.results if p.meets_budget)

            logger.info("=" * 60)
            logger.info("SCRAPING COMPLETE")
            logger.info(f"Total properties:    {total}")
            logger.info(f"  Score A (HOT):     {score_a}")
            logger.info(f"  Score B (WARM):    {score_b}")
            logger.info(f"  Score C (COLD):    {score_c}")
            logger.info(f"  Absentee owners:   {absentee}")
            logger.info(f"  Tax delinquent:    {delinquent}")
            logger.info(f"  In budget range:   {in_budget}")
            logger.info(f"Output CSV: {args.output}")
            if args.dashboard:
                logger.info(f"Dashboard JSON: {args.dashboard}")
            logger.info("=" * 60)
        else:
            logger.warning("No properties found")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        if scraper.results:
            scraper.export_csv(args.output)
            logger.info(f"Saved {len(scraper.results)} partial results")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
