#!/usr/bin/env python3
"""
Phone Enrichment via Google Dorking — Free OSINT for Phone Numbers
Finds phone numbers for property owners using Google search operators.

Usage:
    python phone_enrich_dork.py --name "John Smith" --city "Denton" --state "TX" --max-results 20
    python phone_enrich_dork.py --batch owners.csv --output phones.csv
    python phone_enrich_dork.py --name "John Smith" --city "Denton" --state "TX" --json

Input CSV (batch mode):
    name,city,state
    "John Smith","Denton","TX"
    "Jane Doe","Dallas","TX"

Output CSV:
    name,city,state,phone_number,source_url,dnc_status

DNC check: cross-references dnc_list.txt (one number per line, digits only)
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Set

import requests
from bs4 import BeautifulSoup

# ──────────────────── CONFIG ────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

PHONE_RE = re.compile(
    r'(?:(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4})',
    re.IGNORECASE
)

DORK_TEMPLATES = [
    # General phone searches
    '{name} "{city} {state}" phone',
    '{name} "{city} {state}" "contact"',
    '{name} "{city} {state}" "phone number"',
    '{name} "{city} {state}" directory',
    # Site-specific dorks
    'site:whitepages.com "{name}" "{city} {state}"',
    'site:yellowpages.com "{name}" "{city} {state}"',
    'site:411.com "{name}" "{city} {state}"',
    'site:beenverified.com "{name}" "{city} {state}"',
    'site:spokeo.com "{name}" "{city} {state}"',
    'site:peoplefinders.com "{name}" "{city} {state}"',
    'site:intelius.com "{name}" "{city} {state}"',
    'site:facebook.com "{name}" "{city} {state}"',
    'site:linkedin.com "{name}" "{city} {state}"',
    'site:yelp.com "{name}" "{city} {state}"',
    # Local business / property
    '{name} "{city} {state}" property owner',
    '{name} "{city} {state}" real estate',
    '{name} "{city} {state}" LLC',
    # Address-based (if we have address)
    '{name} "{city}" "{state}" address',
]

RETRY_COUNT = 3
RETRY_DELAY = 2.0


# ──────────────────── DATA CLASSES ────────────────────

@dataclass
class PhoneResult:
    name: str
    city: str
    state: str
    phone_number: Optional[str] = None
    source_url: Optional[str] = None
    dnc_status: str = "pending"
    error: Optional[str] = None

    def to_dict(self):
        return {
            "name": self.name,
            "city": self.city,
            "state": self.state,
            "phone_number": self.phone_number or "",
            "source_url": self.source_url or "",
            "dnc_status": self.dnc_status,
            "error": self.error or "",
        }


# ──────────────────── HELPERS ────────────────────

class DNCChecker:
    def __init__(self, dnc_path: str = "dnc_list.txt"):
        self.dnc_set: Set[str] = set()
        self.dnc_path = Path(dnc_path)
        self._load()

    def _load(self):
        if self.dnc_path.exists():
            with open(self.dnc_path, "r") as f:
                for line in f:
                    num = re.sub(r'\D', '', line.strip())
                    if num and len(num) >= 10:
                        self.dnc_set.add(num)

    def check(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if not digits or len(digits) < 10:
            return "pending"
        # Normalize to 10 digits (drop leading 1)
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        return "flag_dnc" if digits in self.dnc_set else "safe"


class PhoneEnricher:
    def __init__(self, max_results: int = 20, dnc_path: str = "dnc_list.txt"):
        self.max_results = max_results
        self.dnc = DNCChecker(dnc_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
        })

    def _normalize_phone(self, raw: str) -> Optional[str]:
        """Extract and normalize phone number from raw text."""
        digits = re.sub(r'\D', '', raw)
        if not digits or len(digits) < 10:
            return None
        # Handle US numbers
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits.startswith('1'):
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return None

    def _extract_phones(self, text: str) -> List[str]:
        """Extract all phone numbers from text."""
        found = set()
        for match in PHONE_RE.finditer(text):
            phone = self._normalize_phone(match.group())
            if phone:
                found.add(phone)
        return sorted(found)

    def _search_google(self, query: str, ua_index: int = 0) -> List[dict]:
        """Execute Google search and return results."""
        results = []
        url = "https://www.google.com/search"
        params = {"q": query, "num": min(self.max_results, 10), "hl": "en", "safe": "off"}

        for attempt in range(RETRY_COUNT):
            try:
                self.session.headers["User-Agent"] = USER_AGENTS[ua_index % len(USER_AGENTS)]
                time.sleep(0.5 + attempt * 1.0)  # Rate limiting
                resp = self.session.get(url, params=params, timeout=15)

                if resp.status_code == 429:
                    print(f"[warn] Google rate limit (429), retrying...")
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    print(f"[warn] Google returned {resp.status_code}")
                    return results

                # Check for CAPTCHA
                if "captcha" in resp.text.lower() or "unusual traffic" in resp.text.lower():
                    print(f"[warn] CAPTCHA detected, skipping")
                    return results

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract result blocks
                for g in soup.find_all("div", class_=["g", "yuRUbf", "ZINbbc", "xpd"]):
                    title_el = g.find("h3") or g.find("a")
                    title = title_el.get_text(strip=True) if title_el else ""
                    link_el = g.find("a", href=True)
                    link = link_el["href"] if link_el else ""
                    if link.startswith("/url?q="):
                        link = urllib.parse.unquote(link.split("/url?q=")[1].split("&")[0])
                    snippet_el = g.find("div", class_=["VwiC3b", "s3v94d", "dD8iuc", "IsZvec"]) or g
                    snippet = snippet_el.get_text(separator=" ", strip=True) if snippet_el else ""

                    results.append({
                        "title": title,
                        "url": link,
                        "snippet": snippet,
                    })

                return results

            except Exception as e:
                if attempt == RETRY_COUNT - 1:
                    print(f"[error] Search failed: {e}")
                    return results
                time.sleep(RETRY_DELAY * (attempt + 1))

        return results

    def enrich(self, name: str, city: str, state: str) -> PhoneResult:
        """Find phone numbers for a person using Google dorking."""
        result = PhoneResult(name=name, city=city, state=state)
        all_phones = []

        for template in DORK_TEMPLATES:
            query = template.format(name=name, city=city, state=state)
            print(f"[dork] {query}")
            search_results = self._search_google(query)

            for sr in search_results:
                text = f"{sr['title']} {sr['snippet']}"
                phones = self._extract_phones(text)
                for phone in phones:
                    all_phones.append({
                        "phone": phone,
                        "source": sr["url"],
                    })

        # Deduplicate by phone number (keep first source)
        seen = set()
        unique_phones = []
        for p in all_phones:
            digits = re.sub(r'\D', '', p["phone"])
            if digits not in seen and len(digits) >= 10:
                seen.add(digits)
                unique_phones.append(p)

        if not unique_phones:
            result.error = "No phone numbers found via dorking"
            return result

        # Use the first (most reliable) phone
        best = unique_phones[0]
        result.phone_number = best["phone"]
        result.source_url = best["source"]
        result.dnc_status = self.dnc.check(best["phone"])

        return result

    def enrich_batch(self, input_path: str, output_path: str) -> int:
        """Process batch of owners from CSV."""
        records = []
        with open(input_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                city = row.get("city", "").strip()
                state = row.get("state", "").strip()
                if not all([name, city, state]):
                    continue
                result = self.enrich(name, city, state)
                records.append(result)
                print(f"[{result.dnc_status}] {name} → {result.phone_number or 'N/A'}")

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "city", "state", "phone_number", "source_url", "dnc_status", "error"])
            writer.writeheader()
            for r in records:
                writer.writerow(r.to_dict())

        print(f"[done] Wrote {len(records)} records to {output_path}")
        return len(records)


def main():
    parser = argparse.ArgumentParser(description="Phone Enrichment via Google Dorking")
    parser.add_argument("--name", help="Owner full name (e.g., 'John Smith')")
    parser.add_argument("--city", help="City name")
    parser.add_argument("--state", help="State abbreviation (e.g., TX, CA)")
    parser.add_argument("--max-results", type=int, default=20, help="Max Google results per dork")
    parser.add_argument("--batch", help="CSV file with columns: name, city, state")
    parser.add_argument("--output", default="phones_enriched.csv", help="Output CSV file")
    parser.add_argument("--dnc-list", default="dnc_list.txt", help="DNC list file path")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of CSV")
    args = parser.parse_args()

    enricher = PhoneEnricher(max_results=args.max_results, dnc_path=args.dnc_list)

    if args.batch:
        enricher.enrich_batch(args.batch, args.output)
        return

    if not all([args.name, args.city, args.state]):
        print("Error: --name, --city, and --state are required (or use --batch)")
        parser.print_help()
        sys.exit(1)

    result = enricher.enrich(args.name, args.city, args.state)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Name: {result.name}")
        print(f"Location: {result.city}, {result.state}")
        print(f"Phone: {result.phone_number or 'N/A'}")
        print(f"Source: {result.source_url or 'N/A'}")
        print(f"DNC Status: {result.dnc_status}")
        if result.error:
            print(f"Error: {result.error}")


if __name__ == "__main__":
    main()
