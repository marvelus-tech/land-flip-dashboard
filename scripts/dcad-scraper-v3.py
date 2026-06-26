#!/usr/bin/env python3
"""
DCAD Scraper v3 — Dallas County Central Appraisal District
Uses Playwright for reliable browser automation of ASP.NET forms.

Target buyer box:
  - ZIPs: 75230, 75229, 75220, 75218, 75214, 75206, 75225, 75212
  - Lot size: 8,000+ sq ft
  - Built: before 1980
  - Improvement value < 20% of land value (teardown indicator)
  - Budget: $350K-$450K land value

Usage:
  python dcad-scraper-v3.py --zip 75230 --street "Maple" --output leads.csv
  python dcad-scraper-v3.py --auto-streets --zip 75230 --output leads.csv
  python dcad-scraper-v3.py --batch addresses.txt --output leads.csv
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

from playwright.sync_api import sync_playwright, Page, Browser

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
DCAD_BASE = "https://www.dallascad.org"
DCAD_SEARCH_ADDR = f"{DCAD_BASE}/SearchAddr.aspx"
DCAD_SEARCH_OWNER = f"{DCAD_BASE}/SearchOwner.aspx"
DCAD_SEARCH_ACCT = f"{DCAD_BASE}/SearchAcct.aspx"

TARGET_ZIPS = ["75230", "75229", "75220", "75218", "75214", "75206", "75225", "75212"]
MIN_LOT_SIZE = 8000  # sq ft
MAX_YEAR_BUILT = 1980
MAX_IMPROVEMENT_RATIO = 0.20
BUDGET_MIN = 350000
BUDGET_MAX = 450000

DALLAS_STREETS = [
    "Preston", "Royal", "Lovers", "Mockingbird", "Skillman", "Abrams",
    "Garland", "Ross", "Fitzhugh", "Peak", "McKinney", "Knox", "Henderson",
    "Greenville", "Bishop", "Travis", "Live Oak", "Harwood", "Cole",
    "Reunion", "Lemmon", "Inwood", "Northwest", "Munger", "Sylvan",
    "Fort Worth", "Davis", "Jefferson", "Cadiz", "Colorado", "Beckley",
    "Polk", "Clinton", "Edgefield", "Montclair", "Kessler", "Stevens",
    "Hampton", "Westmoreland", "Pioneer", "Commerce", "Pacific", "Jackson",
    "Young", "Record", "Akard", "Ervay", "Field", "Howell", "Julius",
    "Oak", "Maple", "Elm", "Pine", "Cedar", "Birch", "Willow", "Magnolia",
    "Peachtree", "Dogwood", "Hickory", "Ash", "Cherry", "Walnut", "Chestnut",
    "Main", "Broadway", "Park", "Lake", "Forest", "Highland", "Meadow",
    "Ridge", "Valley", "Hill", "Grove", "Court", "Place", "Circle",
    "Drive", "Lane", "Road", "Street", "Avenue", "Boulevard", "Way",
    "Trail", "Path", "Terrace", "Heights", "View", "Crest", "Gardens",
    "Knoll", "Point", "Shores", "Springs", "Glen", "Woods", "Fields",
    "Hollow", "Run", "Creek", "Brook", "Bridge", "Crossing", "Landing",
    "Parkway", "Expressway", "Freeway", "Highway", "Turnpike", "Tollway",
]

# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────
@dataclass
class DCADProperty:
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
    land_value_estimate: int = 0
    potential_profit: int = 0
    meets_budget: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["score_reasons"] = "; ".join(d["score_reasons"])
        return d


# ──────────────────────────────────────────────
# Scraper
# ──────────────────────────────────────────────
class DCADScraper:
    def __init__(self, headless: bool = True, delay: float = 2.0):
        self.headless = headless
        self.delay = delay
        self.logger = logging.getLogger("DCAD")
        self.results: List[DCADProperty] = []
        self.seen_accounts: set = set()
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._init_browser()

    def _init_browser(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        self.page = context.new_page()

    def _sleep(self, multiplier: float = 1.0):
        time.sleep(self.delay * multiplier + random.uniform(0.5, 1.5))

    def search_by_address(
        self,
        street_name: str,
        zip_code: Optional[str] = None,
        address_num: Optional[str] = None,
        max_results: int = 50
    ) -> List[DCADProperty]:
        """Search DCAD by street name and optional ZIP/city."""
        query = f"{street_name} {zip_code or ''}".strip()
        self.logger.info(f"Searching: {query}")

        try:
            self.page.goto(DCAD_SEARCH_ADDR, wait_until="networkidle")
            self._sleep(1)

            # Fill street name
            self.page.fill("input#txtStName", street_name)
            self._sleep(0.3)

            # Fill city (ZIP works here too)
            if zip_code:
                # Select Dallas from city dropdown if searching Dallas ZIPs
                self.page.select_option("select#listCity", "DALLAS")
                self._sleep(0.3)

            # Optionally fill address number
            if address_num:
                self.page.fill("input#txtAddrNum", address_num)
                self._sleep(0.3)

            # Uncheck COMMERCIAL and BPP, keep only RESIDENTIAL
            self.page.uncheck("input#AcctTypeCheckList1_chkAcctType_1")  # COMMERCIAL
            self._sleep(0.2)
            self.page.uncheck("input#AcctTypeCheckList1_chkAcctType_2")  # BPP
            self._sleep(0.2)

            # Click search
            self.page.click("input#cmdSubmit")
            self.page.wait_for_load_state("networkidle")
            self._sleep(1.5)

            return self._parse_search_results(query, max_results)

        except Exception as e:
            self.logger.error(f"Search failed for {query}: {e}")
            return []

    def _parse_search_results(self, query: str, max_results: int = 50) -> List[DCADProperty]:
        """Parse search results page and extract property links."""
        properties = []

        # Check for "no results" or "too many results" messages
        content = self.page.content()
        has_results_table = bool(self.page.query_selector("table[id*='dgResults']"))
        
        if not has_results_table:
            self.logger.info(f"No results for: {query}")
            return []

        if "Maximum number of records returned" in content:
            self.logger.warning(f"Too many results for: {query} — limiting to first page")

        # Find results table — DCAD uses SearchResults1$dgResults
        rows = self.page.query_selector_all("table[id*='dgResults'] tr")
        if not rows:
            rows = self.page.query_selector_all("table tr")

        self.logger.info(f"Found {len(rows)} result rows for: {query}")

        # Collect all property links first before navigating away
        property_links = []
        for row in rows[2:max_results+2]:  # Skip pagination and header rows
            try:
                link = row.query_selector("a[href*='AcctDetail']")
                if not link:
                    continue

                href = link.get_attribute("href") or ""
                if not href:
                    continue

                # Skip BPP (business personal property) and non-residential
                if "AcctDetailBPP" in href:
                    continue

                account_match = re.search(r'ID=([0-9A-Za-z]+)', href)
                if not account_match:
                    continue
                account_num = account_match.group(1)

                if account_num in self.seen_accounts:
                    continue

                # Get type from row
                cells = row.query_selector_all("td")
                type_text = cells[5].inner_text().strip() if len(cells) > 5 else ""
                
                property_links.append((account_num, href, type_text))
            except Exception as e:
                self.logger.debug(f"Error collecting row: {e}")
                continue

        self.logger.info(f"Found {len(property_links)} valid property links")

        # Now navigate to each detail page
        for account_num, href, type_text in property_links:
            if account_num in self.seen_accounts:
                continue
            self.seen_accounts.add(account_num)

            detail_url = href if href.startswith("http") else f"{DCAD_BASE}/{href}"
            prop = self._parse_detail_page(detail_url, account_num, query, type_text)
            if prop:
                properties.append(prop)
                self._sleep(0.8)

        return properties

    def _parse_detail_page(
        self,
        url: str,
        account_num: str,
        query: str,
        prop_type: str = ""
    ) -> Optional[DCADProperty]:
        """Navigate to property detail page and extract all fields."""
        try:
            self.page.goto(url, wait_until="networkidle")
            self._sleep(1.5)

            prop = DCADProperty()
            prop.account_number = account_num
            prop.dcad_url = url
            prop.property_type = prop_type
            prop.scraped_at = datetime.now().isoformat()

            # Parse query
            parts = query.split()
            if parts and parts[-1].isdigit() and len(parts[-1]) == 5:
                prop.search_zip = parts[-1]
                prop.search_street = " ".join(parts[:-1])
            else:
                prop.search_street = query

            # ── Extract text content ──
            content = self.page.content()
            text = self.page.inner_text("body")

            # Property Address
            addr_match = re.search(r'Address:\s*([^\n]+)', text)
            if addr_match:
                prop.property_address = addr_match.group(1).strip()

            # ZIP from property address
            zip_match = re.search(r'(\d{5}(?:-\d{4})?)', prop.property_address)
            if zip_match:
                prop.zip_code = zip_match.group(1)[:5]

            # Owner name
            owner_match = re.search(r'Owner \(Current \d{4}\)\s*\n\s*([^\n]+)', text)
            if owner_match:
                prop.owner_name = owner_match.group(1).strip()

            # Mailing address
            mail_match = re.search(r'Owner \(Current \d{4}\)[\s\S]*?\n\s*([^\n,]+(?:,\s*[^\n]+)?)\n\s*([^\n,]+),\s*(\w{2})\s*(\d{5}(?:-\d{4})?)', text)
            if mail_match:
                prop.mailing_address = mail_match.group(1).strip()
                prop.mailing_city = mail_match.group(2).strip()
                prop.mailing_state = mail_match.group(3).strip()
                prop.mailing_zip = mail_match.group(4).strip()

            # Legal description
            legal_match = re.search(r'Legal Desc \(Current \d{4}\)([\s\S]*?)(?:Deed Transfer Date:|Value)', text)
            if legal_match:
                legal_text = legal_match.group(1)
                # Extract numbered lines
                legal_lines = re.findall(r'\d+:\s*([^\n]+)', legal_text)
                prop.legal_description = "; ".join(legal_lines)

            # Values - look for pattern like "Improvement: Land: Market Value: $X + $Y =$Z"
            value_match = re.search(r'Improvement:\s*Land:\s*Market Value:\s*\$?([\d,]+)\s*\+\s*\$?([\d,]+)\s*=\s*\$?([\d,]+)', text)
            if value_match:
                prop.improvement_value = int(value_match.group(1).replace(',', ''))
                prop.land_value = int(value_match.group(2).replace(',', ''))
                prop.total_value = int(value_match.group(3).replace(',', ''))
            else:
                # Fallback: look for individual values
                land_match = re.search(r'Land\s*[:\$]*\s*\$?([\d,]+)', text)
                if land_match:
                    prop.land_value = int(land_match.group(1).replace(',', ''))
                imp_match = re.search(r'Improvement\s*[:\$]*\s*\$?([\d,]+)', text)
                if imp_match:
                    prop.improvement_value = int(imp_match.group(1).replace(',', ''))
                total_match = re.search(r'Total\s*[:\$]*\s*\$?([\d,]+)', text)
                if total_match:
                    prop.total_value = int(total_match.group(1).replace(',', ''))

            # Year built from improvements section
            year_match = re.search(r'Year Built:\s*(\d{4})', text)
            if year_match:
                prop.year_built = int(year_match.group(1))

            # Lot size - look for acres or sqft in land section
            lot_match = re.search(r'(\d[\d,]*\.?\d*)\s*(?:acres?|ac)\b', text, re.I)
            if lot_match:
                prop.lot_size_sqft = int(float(lot_match.group(1).replace(',', '')) * 43560)
            else:
                sqft_match = re.search(r'(\d[\d,]*)\s*(?:sq\.?\s*ft\.?|sf|square feet)', text, re.I)
                if sqft_match:
                    prop.lot_size_sqft = int(sqft_match.group(1).replace(',', ''))

            # ── Calculate metrics ──
            if prop.land_value > 0:
                prop.improvement_ratio = prop.improvement_value / prop.land_value

            prop.meets_budget = BUDGET_MIN <= prop.land_value <= BUDGET_MAX

            if prop.land_value > 0:
                prop.land_value_estimate = int(prop.total_value * 0.85)
                prop.potential_profit = prop.land_value_estimate - prop.land_value

            # Absentee owner check
            if prop.mailing_address and prop.property_address:
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

        except Exception as e:
            self.logger.error(f"Error parsing detail page {url}: {e}")
            return None

    def _score_property(self, prop: DCADProperty) -> Tuple[str, List[str]]:
        """Score property A/B/C based on buyer box fit."""
        reasons = []
        score = "C"

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

        if prop.is_tax_delinquent:
            reasons.append("Tax delinquent")
            score = "A"
        elif prop.is_absentee_owner:
            score = "B"
            reasons.append("Absentee owner")
        elif fits_lot and fits_year and fits_ratio and in_target_zip:
            score = "B"
            reasons.append("Buyer box fit")

        return score, reasons

    def search_zip_auto(self, zip_code: str, max_streets: int = 20) -> List[DCADProperty]:
        """Auto-search a ZIP by cycling through common street names."""
        self.logger.info(f"Starting auto-search for ZIP {zip_code}")
        all_props = []
        streets = random.sample(DALLAS_STREETS, min(max_streets, len(DALLAS_STREETS)))

        for street in streets:
            props = self.search_by_address(street, zip_code=zip_code, max_results=20)
            all_props.extend(props)
            self.logger.info(f"  {street}: {len(props)} props (total: {len(all_props)})")
            if len(all_props) >= 200:  # safety limit
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
                results = self.search_by_address(addr, max_results=10)
                props.extend(results)
                self.logger.info(f"Batch: {addr} -> {len(results)} results")
        return props

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

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="DCAD Scraper v3 — Find teardown candidates in Dallas (Playwright)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search a specific street in a ZIP
  python dcad-scraper-v3.py --street "Preston" --zip 75230 --output leads.csv

  # Auto-search common streets in a ZIP
  python dcad-scraper-v3.py --auto-streets --zip 75230 --output leads.csv

  # Multiple ZIPs
  python dcad-scraper-v3.py --auto-streets --zip 75230 75229 75225 --output leads.csv

  # Batch from file
  python dcad-scraper-v3.py --batch addresses.txt --output leads.csv

  # Dashboard export
  python dcad-scraper-v3.py --auto-streets --zip 75230 --dashboard data/dcad-leads.json

  # Visible browser (for debugging)
  python dcad-scraper-v3.py --street "Preston" --zip 75230 --no-headless --output leads.csv
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
    parser.add_argument("--output", "-o", type=str, default="dcad-leads.csv",
                        help="Output CSV filename")
    parser.add_argument("--json", type=str, metavar="FILE",
                        help="Also export to JSON")
    parser.add_argument("--dashboard", type=str, metavar="FILE",
                        help="Export dashboard-compatible JSON")
    parser.add_argument("--max-streets", type=int, default=20,
                        help="Max streets in auto mode (default: 20)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between requests (default: 2.0s)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show browser window (for debugging)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    logger = logging.getLogger("DCAD")

    scraper = DCADScraper(headless=not args.no_headless, delay=args.delay)

    try:
        if args.batch:
            props = scraper.search_batch(args.batch)
            scraper.results.extend(props)

        elif args.auto_streets:
            for zip_code in args.zip:
                logger.info(f"Auto-streets mode for ZIP {zip_code}")
                props = scraper.search_zip_auto(zip_code, max_streets=args.max_streets)
                scraper.results.extend(props)

        elif args.street:
            for zip_code in args.zip:
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
            in_budget = sum(1 for p in scraper.results if p.meets_budget)

            logger.info("=" * 60)
            logger.info("SCRAPING COMPLETE")
            logger.info(f"Total properties:    {total}")
            logger.info(f"  Score A (HOT):     {score_a}")
            logger.info(f"  Score B (WARM):    {score_b}")
            logger.info(f"  Score C (COLD):    {score_c}")
            logger.info(f"  Absentee owners:   {absentee}")
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
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
