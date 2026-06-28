#!/usr/bin/env python3
"""
County Assessor Portal Scraper — Free OSINT for Property Ownership
Scrapes owner name and mailing address from US county assessor websites.

Supports:
- Tyler Technologies portals (e.g., dentoncad.com, taylorcad.org, johsoncountytx.org)
- BS&A / Beacon (e.g., Michigan, Wisconsin)
- Custom ASP.NET portals (e.g., McHenry County IL)
- Treasurers/Collectors with property search

Usage:
    python portal_scraper.py --address "123 Main St" --city "Denton" --state "TX"
    python portal_scraper.py --test --portal dentoncad.com
    python portal_scraper.py --batch addresses.csv --output results.csv

Output columns:
    input_address, owner_name, mailing_address, parcel_id, property_value, scraped_from_url, status, error
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup

# ──────────────────── CONFIG ────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

RETRY_COUNT = 3
RETRY_DELAY = 2.0


# ──────────────────── KNOWN PORTAL PATTERNS ────────────────────

PORTAL_PATTERNS = {
    "tyler": {
        "domains": ["dentoncad.com", "taylorcad.org", "deltacad.org", "co.hood.tx.us", "smithcad.org"],
        "search_path": "/search",
        "form_action": "/search",
        "owner_selector": "div.owner-name, .owner, .taxpayer-name",
        "address_selector": "div.mailing-address, .owner-address, .taxpayer-address",
        "parcel_selector": ".parcel-id, .account-number, .geo-id",
        "value_selector": ".appraised-value, .market-value, .total-value",
        "method": "post",
        "search_field": "search",
        "form_data": lambda addr: {"search": addr, "searchType": "property", "action": "search"},
    },
    "beacon": {
        "domains": ["beacon.schneidercorp.com", "bsaonline.com"],
        "search_path": "/",
        "owner_selector": ".owner-name, #ownerName, .taxpayer",
        "address_selector": ".owner-address, #mailingAddress, .taxpayer-address",
        "parcel_selector": ".parcel-id, #parcelNumber, .pin",
        "value_selector": ".total-value, #assessedValue, .market-value",
        "method": "get",
        "search_field": "q",
        "form_data": lambda addr: {"q": addr, "type": "property"},
    },
    "qpublic": {
        "domains": ["qpublic.net", "qpublic.schneidercorp.com", "qpublic4.qpublic.net"],
        "search_path": "/search",
        "owner_selector": "span.owner, .owner-name, .taxpayer-name",
        "address_selector": ".owner-address, .taxpayer-address, .mailing-address",
        "parcel_selector": ".parcel, .parcel-id, .account",
        "value_selector": ".value, .total-value, .appraised-value",
        "method": "post",
        "search_field": "parcel",
        "form_data": lambda addr: {"parcel": addr, "search": "Search"},
    },
    "custom_asp": {
        "domains": ["mchenrycountyil.gov", "lakecountyil.gov", "dupagecounty.gov", "collincad.org"],
        "search_path": "/PropertySearch",
        "owner_selector": "#lblOwner, .owner-name, .taxpayer-name",
        "address_selector": "#lblAddress, .owner-address, .taxpayer-address",
        "parcel_selector": "#lblParcel, .parcel-id, .pin",
        "value_selector": "#lblValue, .total-value, .assessed-value",
        "method": "post",
        "search_field": "txtSearch",
        "form_data": lambda addr: {"txtSearch": addr, "btnSearch": "Search"},
    },
    "texas_window": {
        "domains": ["texaswindow.com", "tcad.org", "bexar.org", "hccad.org"],
        "search_path": "/PropertySearch",
        "owner_selector": ".owner-name, .taxpayer, #OwnerName",
        "address_selector": ".owner-address, #MailingAddress, .taxpayer-address",
        "parcel_selector": ".parcel-id, #AccountID, .geo-id",
        "value_selector": ".market-value, #AppraisedValue, .total-value",
        "method": "post",
        "search_field": "PropertySearch",
        "form_data": lambda addr: {"PropertySearch": addr, "Submit": "Search"},
    },
}


# ──────────────────── HELPERS ────────────────────

@dataclass
class PropertyRecord:
    input_address: str
    owner_name: Optional[str] = None
    mailing_address: Optional[str] = None
    parcel_id: Optional[str] = None
    property_value: Optional[str] = None
    scraped_from_url: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None

    def to_dict(self):
        return {
            "input_address": self.input_address,
            "owner_name": self.owner_name or "",
            "mailing_address": self.mailing_address or "",
            "parcel_id": self.parcel_id or "",
            "property_value": self.property_value or "",
            "scraped_from_url": self.scraped_from_url or "",
            "status": self.status,
            "error": self.error or "",
        }


class PortalScraper:
    def __init__(self, portal_type: str = "auto", portal_url: Optional[str] = None):
        self.portal_type = portal_type
        self.portal_url = portal_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENTS[0]})

    def _guess_portal(self, city: str, state: str) -> Optional[str]:
        """Try to find the portal URL from city + state."""
        search_query = f"{city} {state} county assessor property search"
        try:
            resp = self._fetch_with_retry(
                "https://www.google.com/search",
                params={"q": search_query, "num": 5},
                headers={"User-Agent": USER_AGENTS[0]},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=re.compile(r"/url\?q=")):
                href = urllib.parse.unquote(a.get("href", ""))
                match = re.search(r'/url\?q=(https?://[^&]+)', href)
                if match:
                    url = match.group(1)
                    if any(k in url.lower() for k in ["assessor", "cad", "tax", "property", "parcel"]):
                        return url
        except Exception as e:
            print(f"[warn] Portal guess failed: {e}")
        return None

    def _detect_portal_type(self, url: str) -> Optional[str]:
        """Detect portal type from URL or page content."""
        url_lower = url.lower()
        for ptype, config in PORTAL_PATTERNS.items():
            for domain in config["domains"]:
                if domain in url_lower:
                    return ptype
        # Try to detect from page content
        try:
            resp = self._fetch_with_retry(url, timeout=10)
            text = resp.text.lower()
            if "tyler" in text or "technologies" in text:
                return "tyler"
            if "beacon" in text or "bsa" in text:
                return "beacon"
            if "qpublic" in text:
                return "qpublic"
            if any(x in text for x in ["asp.net", "__viewstate", "__eventvalidation"]):
                return "custom_asp"
        except Exception:
            pass
        return None

    def _fetch_with_retry(self, url: str, method: str = "get", **kwargs) -> requests.Response:
        """Fetch with retry, user-agent rotation, and rate limiting."""
        for attempt in range(RETRY_COUNT):
            try:
                self.session.headers["User-Agent"] = USER_AGENTS[attempt % len(USER_AGENTS)]
                time.sleep(0.5 + attempt * 0.5)  # gentle rate limit
                if method == "post":
                    resp = self.session.post(url, timeout=kwargs.pop("timeout", 15), **kwargs)
                else:
                    resp = self.session.get(url, timeout=kwargs.pop("timeout", 15), **kwargs)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (403, 429, 503):
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return resp
            except Exception as e:
                if attempt == RETRY_COUNT - 1:
                    raise
                time.sleep(RETRY_DELAY * (attempt + 1))
        return requests.Response()

    def _extract_text(self, soup: BeautifulSoup, selectors: str) -> Optional[str]:
        """Extract text from first matching selector."""
        for sel in selectors.split(","):
            el = soup.select_one(sel.strip())
            if el:
                return " ".join(el.get_text(strip=True).split())
        return None

    def _parse_record(self, soup: BeautifulSoup, config: dict, url: str) -> PropertyRecord:
        """Parse property record from page soup."""
        record = PropertyRecord(
            input_address="",
            owner_name=self._extract_text(soup, config["owner_selector"]),
            mailing_address=self._extract_text(soup, config["address_selector"]),
            parcel_id=self._extract_text(soup, config["parcel_selector"]),
            property_value=self._extract_text(soup, config["value_selector"]),
            scraped_from_url=url,
            status="success" if any([self._extract_text(soup, config["owner_selector"])]) else "no_results",
        )
        return record

    def scrape(self, address: str, city: str, state: str) -> PropertyRecord:
        """Scrape property record for given address."""
        record = PropertyRecord(input_address=f"{address}, {city}, {state}")
        
        # Determine portal URL
        if self.portal_url:
            portal_url = self.portal_url
        else:
            portal_url = self._guess_portal(city, state)
        
        if not portal_url:
            record.status = "no_portal_found"
            record.error = f"Could not find portal for {city}, {state}"
            return record

        # Detect portal type
        portal_type = self.portal_type if self.portal_type != "auto" else self._detect_portal_type(portal_url)
        if not portal_type:
            record.status = "unsupported_portal"
            record.error = f"Could not detect portal type for {portal_url}"
            return record

        config = PORTAL_PATTERNS[portal_type]
        
        try:
            # Build search URL with fallback paths
            search_path = config.get("search_path", "")
            alternative_paths = ["/search", "/PropertySearch", "/property-search", "/search.aspx", "/Search"]
            
            # Prepare form data once
            form_data = config["form_data"](address)
            
            resp = None
            search_url = None
            for path in [search_path] + [p for p in alternative_paths if p != search_path]:
                try_url = portal_url.rstrip("/") + path
                try:
                    if config["method"] == "post":
                        resp = self._fetch_with_retry(try_url, data=form_data, method="post")
                    else:
                        resp = self._fetch_with_retry(try_url, params=form_data, method="get")
                    if resp and resp.status_code == 200:
                        search_url = try_url
                        break
                except Exception:
                    continue
            
            if not resp or resp.status_code != 200:
                record.status = "search_failed"
                record.error = f"Could not reach search endpoint for {portal_url}"
                return record
            
            if resp.status_code != 200:
                record.status = "search_failed"
                record.error = f"HTTP {resp.status_code} from {search_url}"
                return record

            # Parse results
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Check for "no results" message
            no_results_text = ["no results", "no records", "not found", "0 results", "no matches"]
            page_text = soup.get_text().lower()
            if any(nr in page_text for nr in no_results_text):
                record.status = "no_results"
                record.error = "No results found for address"
                return record

            # Look for result links
            result_links = soup.find_all("a", href=re.compile(r"(parcel|account|property|detail|pid|gid|id=)"))
            if not result_links:
                # Maybe we're already on the detail page
                record = self._parse_record(soup, config, resp.url)
                record.input_address = f"{address}, {city}, {state}"
                return record

            # Visit first result link
            detail_url = result_links[0].get("href")
            if detail_url and not detail_url.startswith("http"):
                detail_url = urllib.parse.urljoin(resp.url, detail_url)
            
            detail_resp = self._fetch_with_retry(detail_url)
            detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
            record = self._parse_record(detail_soup, config, detail_url)
            record.input_address = f"{address}, {city}, {state}"
            return record

        except Exception as e:
            record.status = "error"
            record.error = str(e)
            return record

    def test_portal(self, portal_url: str) -> dict:
        """Test a specific portal with a known address."""
        print(f"[test] Testing portal: {portal_url}")
        self.portal_url = portal_url
        portal_type = self._detect_portal_type(portal_url)
        if not portal_type:
            return {"portal_url": portal_url, "status": "unknown_type", "message": "Could not detect portal type"}
        
        # Use a test address based on portal domain
        domain_lower = portal_url.lower()
        if "denton" in domain_lower or "tx" in domain_lower or "texas" in domain_lower:
            test_address, test_city, test_state = "123 Main", "Denton", "TX"
        elif "collin" in domain_lower or "mckinney" in domain_lower:
            test_address, test_city, test_state = "123 Main", "McKinney", "TX"
        elif "ca" in domain_lower or "california" in domain_lower:
            test_address, test_city, test_state = "123 Main", "Sacramento", "CA"
        else:
            test_address, test_city, test_state = "123 Main", "Test City", "TX"
        
        record = self.scrape(test_address, test_city, test_state)
        return {
            "portal_url": portal_url,
            "portal_type": portal_type,
            "test_address": f"{test_address}, {test_city}, {test_state}",
            "status": record.status,
            "owner_found": bool(record.owner_name),
            "sample_owner": record.owner_name,
            "sample_parcel": record.parcel_id,
            "error": record.error,
        }


def main():
    parser = argparse.ArgumentParser(description="County Assessor Portal Scraper")
    parser.add_argument("--address", help="Street address (e.g., '123 Main St')")
    parser.add_argument("--city", help="City name")
    parser.add_argument("--state", help="State abbreviation (e.g., TX, CA)")
    parser.add_argument("--portal", help="Direct portal URL (optional)")
    parser.add_argument("--portal-type", default="auto", choices=list(PORTAL_PATTERNS.keys()) + ["auto"])
    parser.add_argument("--batch", help="CSV file with columns: address, city, state")
    parser.add_argument("--output", default="scraped_results.csv", help="Output CSV file")
    parser.add_argument("--test", action="store_true", help="Test mode — verify portal works")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of CSV")
    args = parser.parse_args()

    scraper = PortalScraper(portal_type=args.portal_type, portal_url=args.portal)

    if args.test:
        if not args.portal:
            print("Error: --test requires --portal URL")
            sys.exit(1)
        result = scraper.test_portal(args.portal)
        print(json.dumps(result, indent=2))
        return

    if args.batch:
        records = []
        with open(args.batch, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                record = scraper.scrape(row["address"], row["city"], row["state"])
                records.append(record)
                print(f"[{record.status}] {row['address']}, {row['city']} {row['state']}")
        
        if args.json:
            print(json.dumps([r.to_dict() for r in records], indent=2))
        else:
            with open(args.output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["input_address", "owner_name", "mailing_address", "parcel_id", "property_value", "scraped_from_url", "status", "error"])
                writer.writeheader()
                for r in records:
                    writer.writerow(r.to_dict())
            print(f"[done] Wrote {len(records)} records to {args.output}")
        return

    if not all([args.address, args.city, args.state]):
        print("Error: --address, --city, and --state are required (or use --batch)")
        parser.print_help()
        sys.exit(1)

    record = scraper.scrape(args.address, args.city, args.state)
    if args.json:
        print(json.dumps(record.to_dict(), indent=2))
    else:
        print(f"Status: {record.status}")
        print(f"Owner: {record.owner_name or 'N/A'}")
        print(f"Mailing Address: {record.mailing_address or 'N/A'}")
        print(f"Parcel ID: {record.parcel_id or 'N/A'}")
        print(f"Value: {record.property_value or 'N/A'}")
        print(f"URL: {record.scraped_from_url or 'N/A'}")
        if record.error:
            print(f"Error: {record.error}")


if __name__ == "__main__":
    main()
