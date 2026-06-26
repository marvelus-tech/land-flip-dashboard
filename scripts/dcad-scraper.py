#!/usr/bin/env python3
"""
DCAD Scraper — Dallas County Central Appraisal District
Automates property lookups to find pre-1980 teardown candidates for land flipping.

Target buyer box:
  - ZIPs: 75230, 75229, 75220, 75218, 75214, 75206, 75225, 75212
  - Lot size: 8,000+ sq ft
  - Built: before 1980
  - Improvement value < 20% of land value (teardown indicator)
  - Bonus: absentee owner, tax delinquent

Output: CSV of qualified leads ready for skip tracing and direct mail.

Usage:
  python dcad-scraper.py --zip 75230 --street "Maple" --output leads.csv
  python dcad-scraper.py --batch addresses.txt --output leads.csv
  python dcad-scraper.py --zip 75230 --auto-streets --max-pages 5 --output leads.csv
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
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
DCAD_SEARCH_URL = "https://www.dcad.org/PropertySearch"
DCAD_BASE_URL = "https://www.dcad.org"

TARGET_ZIPS = ["75230", "75229", "75220", "75218", "75214", "75206", "75225", "75212"]
MIN_LOT_SIZE = 8000  # sq ft
MAX_YEAR_BUILT = 1980
MAX_IMPROVEMENT_RATIO = 0.20  # improvement value / land value

# Common street names in Dallas — used for auto-street mode
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
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────
@dataclass
class DCADProperty:
    """Single property record from DCAD."""
    account_number: str = ""
    property_address: str = ""           # Full street address
    zip_code: str = ""                   # From property address
    owner_name: str = ""
    mailing_address: str = ""              # Owner's mailing address
    mailing_city_state_zip: str = ""     # City, ST ZIP
    is_absentee_owner: bool = False      # Mailing address != property address
    lot_size_sqft: int = 0               # Total sq ft
    year_built: int = 0
    land_value: int = 0                  # Appraised land value
    improvement_value: int = 0           # Appraised building value
    total_value: int = 0
    improvement_ratio: float = 0.0       # improvement / land
    tax_status: str = ""                 # Current, Delinquent, Exempt, etc.
    property_type: str = ""              # Residential, Commercial, etc.
    legal_description: str = ""
    # Scoring
    score: str = "C"                     # A, B, C
    score_reasons: List[str] = field(default_factory=list)
    # Source tracking
    search_zip: str = ""                 # Which ZIP we searched
    search_street: str = ""              # Which street we searched
    scraped_at: str = ""                 # ISO timestamp
    dcad_url: str = ""                   # Direct link to DCAD record

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["score_reasons"] = "; ".join(d["score_reasons"])
        return d


# ──────────────────────────────────────────────
# WebDriver setup
# ──────────────────────────────────────────────
def create_driver(headless: bool = True, proxy: Optional[str] = None) -> webdriver.Chrome:
    """Create a Chrome WebDriver with anti-detection settings."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    if proxy:
        opts.add_argument(f"--proxy-server={proxy}")

    driver = webdriver.Chrome(options=opts)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ──────────────────────────────────────────────
# DCAD Search
# ──────────────────────────────────────────────
class DCADScraper:
    """Scrape DCAD property search for teardown candidates."""

    def __init__(self, headless: bool = True, delay: float = 2.0, proxy: Optional[str] = None):
        self.driver = create_driver(headless, proxy)
        self.wait = WebDriverWait(self.driver, 15)
        self.delay = delay
        self.logger = logging.getLogger("DCAD")
        self.results: List[DCADProperty] = []
        self.seen_accounts: set = set()  # dedupe

    def _sleep(self, multiplier: float = 1.0):
        """Human-like delay between requests."""
        time.sleep(self.delay * multiplier + random.uniform(0.5, 1.5))

    def _safe_click(self, xpath: str, timeout: int = 10):
        """Click element with wait and retry."""
        try:
            el = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            el.click()
            return True
        except TimeoutException:
            self.logger.warning(f"Click timeout: {xpath}")
            return False

    def _safe_text(self, xpath: str, default: str = "") -> str:
        """Extract text from element, return default if missing."""
        try:
            el = self.driver.find_element(By.XPATH, xpath)
            return el.text.strip()
        except NoSuchElementException:
            return default

    def search_by_address(self, address_query: str) -> List[DCADProperty]:
        """
        Search DCAD by address (e.g. 'Maple 75230' or '4521 Elm').
        Returns list of property detail pages to parse.
        """
        self.logger.info(f"Searching DCAD: {address_query}")
        try:
            self.driver.get(DCAD_SEARCH_URL)
            self._sleep(1.5)

            # DCAD search form — usually has an address input
            # Try multiple common selectors
            address_input = None
            selectors = [
                "//input[@placeholder[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address')]]",
                "//input[contains(@id, 'address') or contains(@name, 'address') or contains(@class, 'address')]",
                "//input[@type='text' and not(@id='')]",  # fallback: first text input
            ]
            for sel in selectors:
                try:
                    address_input = self.wait.until(EC.presence_of_element_located((By.XPATH, sel)))
                    break
                except TimeoutException:
                    continue

            if not address_input:
                self.logger.error("Could not find DCAD address input field")
                return []

            address_input.clear()
            address_input.send_keys(address_query)
            self._sleep(0.5)
            address_input.send_keys(Keys.RETURN)
            self._sleep(2.0)

            # Check for results table or "no results" message
            return self._parse_search_results(address_query)

        except WebDriverException as e:
            self.logger.error(f"WebDriver error during search: {e}")
            return []

    def _parse_search_results(self, query: str) -> List[DCADProperty]:
        """Parse the search results page and extract property links."""
        properties = []
        # Common result row selectors
        row_selectors = [
            "//table//tr[contains(@class, 'result') or contains(@class, 'data')]",
            "//table/tbody/tr",
            "//div[contains(@class, 'result')]",
            "//a[contains(@href, 'Account') or contains(@href, 'account')]",
        ]

        rows = []
        for sel in row_selectors:
            rows = self.driver.find_elements(By.XPATH, sel)
            if rows:
                break

        self.logger.info(f"Found {len(rows)} result rows for query: {query}")

        for row in rows:
            try:
                # Try to find account link
                links = row.find_elements(By.XPATH, ".//a[contains(@href, 'Account') or contains(@href, 'account')]")
                if not links:
                    links = row.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href")
                    if href and ("account" in href.lower() or "property" in href.lower()):
                        # Get account number from text or href
                        account_text = link.text.strip()
                        account_num = re.search(r'\d+', account_text)
                        if account_num:
                            account_num = account_num.group()
                        else:
                            account_num = href.split("=")[-1] if "=" in href else ""

                        if account_num and account_num not in self.seen_accounts:
                            self.seen_accounts.add(account_num)
                            prop = self._parse_detail_page(href, query)
                            if prop:
                                properties.append(prop)
                                self._sleep(1.0)  # polite delay between detail pages
            except Exception as e:
                self.logger.debug(f"Error parsing row: {e}")
                continue

        return properties

    def _parse_detail_page(self, url: str, query: str) -> Optional[DCADProperty]:
        """Navigate to a property detail page and extract all fields."""
        try:
            self.driver.get(url)
            self._sleep(1.5)

            prop = DCADProperty()
            prop.account_number = re.search(r'\d+', url.split("=")[-1]).group() if "=" in url else ""
            prop.dcad_url = url
            prop.search_zip = query.split()[-1] if query.split()[-1].isdigit() else ""
            prop.search_street = " ".join(query.split()[:-1]) if prop.search_zip else query
            prop.scraped_at = datetime.now().isoformat()

            # ── Extract fields using common DCAD detail page selectors ──
            # Owner name
            prop.owner_name = self._extract_field([
                "//span[contains(text(), 'Owner') or contains(@id, 'Owner') or contains(@class, 'owner')]",
                "//td[contains(text(), 'Owner')]/following-sibling::td",
                "//div[contains(text(), 'Owner')]",
            ])

            # Property address
            prop.property_address = self._extract_field([
                "//span[contains(text(), 'Property Address') or contains(@id, 'PropertyAddress')]",
                "//td[contains(text(), 'Property Address')]/following-sibling::td",
                "//div[contains(text(), 'Property Address')]",
                "//span[contains(text(), 'Situs') or contains(@id, 'Situs')]",
            ])

            # Extract ZIP from property address
            zip_match = re.search(r'(\d{5})', prop.property_address)
            if zip_match:
                prop.zip_code = zip_match.group(1)

            # Mailing address
            prop.mailing_address = self._extract_field([
                "//span[contains(text(), 'Mailing Address') or contains(@id, 'MailingAddress')]",
                "//td[contains(text(), 'Mailing Address')]/following-sibling::td",
                "//div[contains(text(), 'Mailing Address')]",
            ])

            # Mailing city/state/zip
            prop.mailing_city_state_zip = self._extract_field([
                "//span[contains(text(), 'Mailing City') or contains(@id, 'MailingCity')]",
                "//td[contains(text(), 'Mailing City')]/following-sibling::td",
            ])

            # Lot size
            lot_text = self._extract_field([
                "//span[contains(text(), 'Lot Size') or contains(text(), 'Total Sq Ft') or contains(@id, 'LotSize')]",
                "//td[contains(text(), 'Lot Size')]/following-sibling::td",
                "//td[contains(text(), 'Total Sq Ft')]/following-sibling::td",
            ])
            prop.lot_size_sqft = self._parse_number(lot_text)

            # Year built
            year_text = self._extract_field([
                "//span[contains(text(), 'Year Built') or contains(text(), 'Yr Blt') or contains(@id, 'YearBuilt')]",
                "//td[contains(text(), 'Year Built')]/following-sibling::td",
                "//td[contains(text(), 'Yr Blt')]/following-sibling::td",
            ])
            prop.year_built = self._parse_number(year_text)

            # Land value
            land_text = self._extract_field([
                "//span[contains(text(), 'Land Value') or contains(text(), 'Land') or contains(@id, 'LandValue')]",
                "//td[contains(text(), 'Land Value')]/following-sibling::td",
                "//td[contains(text(), 'Land')]/following-sibling::td",
            ])
            prop.land_value = self._parse_number(land_text)

            # Improvement value
            imp_text = self._extract_field([
                "//span[contains(text(), 'Improvement') or contains(text(), 'Building') or contains(@id, 'Improvement')]",
                "//td[contains(text(), 'Improvement')]/following-sibling::td",
                "//td[contains(text(), 'Building')]/following-sibling::td",
            ])
            prop.improvement_value = self._parse_number(imp_text)

            # Total value
            total_text = self._extract_field([
                "//span[contains(text(), 'Total Value') or contains(text(), 'Total Appraised') or contains(@id, 'TotalValue')]",
                "//td[contains(text(), 'Total Value')]/following-sibling::td",
            ])
            prop.total_value = self._parse_number(total_text)

            # Tax status
            prop.tax_status = self._extract_field([
                "//span[contains(text(), 'Tax Status') or contains(text(), 'Delinquent') or contains(@id, 'TaxStatus')]",
                "//td[contains(text(), 'Tax Status')]/following-sibling::td",
            ])

            # Property type
            prop.property_type = self._extract_field([
                "//span[contains(text(), 'Property Type') or contains(text(), 'Type') or contains(@id, 'PropertyType')]",
                "//td[contains(text(), 'Property Type')]/following-sibling::td",
            ])

            # Legal description
            prop.legal_description = self._extract_field([
                "//span[contains(text(), 'Legal Description') or contains(@id, 'LegalDescription')]",
                "//td[contains(text(), 'Legal Description')]/following-sibling::td",
            ])

            # ── Calculate metrics ──
            if prop.land_value > 0:
                prop.improvement_ratio = prop.improvement_value / prop.land_value

            # Absentee owner check
            if prop.mailing_address and prop.property_address:
                # Simple check: if mailing address doesn't contain the street number
                street_num = re.search(r'^(\d+)', prop.property_address)
                if street_num and street_num.group() not in prop.mailing_address:
                    prop.is_absentee_owner = True

            # ── Score the lead ──
            prop.score, prop.score_reasons = self._score_property(prop)

            self.logger.info(
                f"Parsed: {prop.property_address} | Owner: {prop.owner_name} | "
                f"Lot: {prop.lot_size_sqft} | Year: {prop.year_built} | Score: {prop.score}"
            )
            return prop

        except Exception as e:
            self.logger.error(f"Error parsing detail page {url}: {e}")
            return None

    def _extract_field(self, xpaths: List[str]) -> str:
        """Try multiple XPaths and return the first match."""
        for xpath in xpaths:
            text = self._safe_text(xpath)
            if text:
                return text
        return ""

    @staticmethod
    def _parse_number(text: str) -> int:
        """Extract numeric value from text like '$125,000' or '8,500 sq ft'."""
        if not text:
            return 0
        # Remove $, commas, spaces, units
        cleaned = re.sub(r'[$,\s\w/\.]+', '', text)
        try:
            return int(cleaned) if cleaned else 0
        except ValueError:
            return 0

    def _score_property(self, prop: DCADProperty) -> (str, List[str]):
        """
        Score a property A/B/C based on buyer box fit.
        A = Tax delinquent + absentee owner = HOT lead
        B = Absentee owner or good fit = mail campaign
        C = Local owner or doesn't fully match = lower priority
        """
        reasons = []
        score = "C"

        # Check buyer box fit
        fits_lot = prop.lot_size_sqft >= MIN_LOT_SIZE
        fits_year = 0 < prop.year_built <= MAX_YEAR_BUILT
        fits_ratio = prop.improvement_ratio <= MAX_IMPROVEMENT_RATIO or prop.improvement_value == 0
        in_target_zip = prop.zip_code in TARGET_ZIPS

        if fits_lot:
            reasons.append(f"Lot {prop.lot_size_sqft} sq ft")
        if fits_year:
            reasons.append(f"Built {prop.year_built}")
        if fits_ratio:
            reasons.append(f"Imp ratio {prop.improvement_ratio:.0%}")
        if in_target_zip:
            reasons.append(f"ZIP {prop.zip_code}")

        # Score logic
        if prop.tax_status and "delinquent" in prop.tax_status.lower():
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

    def search_zip_auto(self, zip_code: str, max_pages: int = 5) -> List[DCADProperty]:
        """
        Auto-search a ZIP by cycling through common street names.
        This is the heavy-lifter mode — generates lots of leads.
        """
        self.logger.info(f"Starting auto-search for ZIP {zip_code}")
        all_props = []
        for street in DALLAS_STREETS:
            query = f"{street} {zip_code}"
            props = self.search_by_address(query)
            all_props.extend(props)
            self.logger.info(f"  {street}: {len(props)} properties found (total: {len(all_props)})")
            if len(all_props) >= 100:  # safety limit per ZIP
                break
        return all_props

    def search_batch(self, address_file: str) -> List[DCADProperty]:
        """Read addresses from a file and look up each one."""
        props = []
        with open(address_file, "r") as f:
            addresses = [line.strip() for line in f if line.strip()]

        for addr in addresses:
            results = self.search_by_address(addr)
            props.extend(results)
            self.logger.info(f"Batch lookup: {addr} -> {len(results)} results")
        return props

    def close(self):
        self.driver.quit()

    def export_csv(self, filepath: str):
        """Export all collected properties to CSV."""
        if not self.results:
            self.logger.warning("No results to export")
            return

        # Determine fieldnames from dataclass
        fieldnames = list(DCADProperty.__dataclass_fields__.keys())
        # Remove internal list field, handled in to_dict
        fieldnames = [f for f in fieldnames if f != "score_reasons"]
        fieldnames.append("score_reasons")  # string version

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for prop in self.results:
                writer.writerow(prop.to_dict())

        self.logger.info(f"Exported {len(self.results)} properties to {filepath}")

    def export_json(self, filepath: str):
        """Export all collected properties to JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([prop.to_dict() for prop in self.results], f, indent=2)
        self.logger.info(f"Exported {len(self.results)} properties to {filepath}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="DCAD Scraper — Find pre-1980 teardown candidates in Dallas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search a specific street in a ZIP
  python dcad-scraper.py --zip 75230 --street "Maple" --output leads.csv

  # Auto-search all common streets in a ZIP (generates 50-200 leads)
  python dcad-scraper.py --zip 75230 --auto-streets --output leads.csv

  # Batch process addresses from a file
  python dcad-scraper.py --batch addresses.txt --output leads.csv

  # Multiple ZIPs with auto-streets
  python dcad-scraper.py --zip 75230 75229 75220 --auto-streets --output leads.csv

  # Visible browser (for debugging)
  python dcad-scraper.py --zip 75230 --street "Elm" --no-headless --output leads.csv
        """
    )
    parser.add_argument("--zip", nargs="+", default=TARGET_ZIPS,
                        help="Target ZIP code(s) to search (default: all 8)")
    parser.add_argument("--street", type=str,
                        help="Street name to search (e.g. 'Maple', 'Elm')")
    parser.add_argument("--auto-streets", action="store_true",
                        help="Auto-search all common street names in ZIP(s)")
    parser.add_argument("--batch", type=str, metavar="FILE",
                        help="File with one address per line to look up")
    parser.add_argument("--output", "-o", type=str, default="dcad-leads.csv",
                        help="Output CSV filename (default: dcad-leads.csv)")
    parser.add_argument("--json", type=str, metavar="FILE",
                        help="Also export to JSON")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Max result pages per search (default: 5)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between requests in seconds (default: 2.0)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show browser window (for debugging)")
    parser.add_argument("--proxy", type=str,
                        help="HTTP proxy (e.g. http://user:pass@host:port)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    logger = logging.getLogger("DCAD")

    # Validate output path
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scraper = DCADScraper(
        headless=not args.no_headless,
        delay=args.delay,
        proxy=args.proxy
    )

    try:
        if args.batch:
            logger.info(f"Batch mode: reading {args.batch}")
            props = scraper.search_batch(args.batch)
            scraper.results.extend(props)

        elif args.auto_streets:
            for zip_code in args.zip:
                logger.info(f"Auto-streets mode for ZIP {zip_code}")
                props = scraper.search_zip_auto(zip_code, max_pages=args.max_pages)
                scraper.results.extend(props)

        elif args.street:
            for zip_code in args.zip:
                query = f"{args.street} {zip_code}"
                props = scraper.search_by_address(query)
                scraper.results.extend(props)

        else:
            parser.print_help()
            sys.exit(1)

        # Export
        scraper.export_csv(args.output)
        if args.json:
            scraper.export_json(args.json)

        # Summary
        total = len(scraper.results)
        score_a = sum(1 for p in scraper.results if p.score == "A")
        score_b = sum(1 for p in scraper.results if p.score == "B")
        score_c = sum(1 for p in scraper.results if p.score == "C")

        logger.info("=" * 50)
        logger.info(f"SCRAPING COMPLETE")
        logger.info(f"Total properties: {total}")
        logger.info(f"  Score A (HOT):     {score_a}")
        logger.info(f"  Score B (WARM):    {score_b}")
        logger.info(f"  Score C (COLD):    {score_c}")
        logger.info(f"Output: {args.output}")
        logger.info("=" * 50)

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
