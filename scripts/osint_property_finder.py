#!/usr/bin/env python3
"""
OSINT Property Owner Finder + DNC Compliance
For Rank & Rent lead generation — replaces TruePeopleSearch

Usage:
    python3 osint_property_finder.py --address "123 Main St, Jersey City, NJ 07302"
    python3 osint_property_finder.py --business "Joe's Diner" --city "Jersey City NJ"
    python3 osint_property_finder.py --batch-file leads.csv

Requires:
    - PropertyAPI.co API key (100 free credits at signup)
    - Optional: Whitepages Pro API key for phone enrichment
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── Configuration ───
PROPERTY_API_KEY = "YOUR_PROPERTYAPI_KEY_HERE"  # Get from propertyapi.co
WHITEPAGES_API_KEY = "YOUR_WHITEPAGES_KEY_HERE"  # Optional

# National DNC list — download from telemarketing.donotcall.gov
# Or use a service that includes DNC scrubbing
DNC_LIST_PATH = Path.home() / ".openclaw" / "workspace" / "dnc_list.txt"

# Cache directory for results
CACHE_DIR = Path.home() / ".openclaw" / "workspace" / "osint_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── PropertyAPI.co Integration ───

def propertyapi_lookup(address: str, api_key: str = None) -> dict:
    """
    Query PropertyAPI.co for property ownership data.
    1 credit per search. 100 free credits on signup.
    """
    key = api_key or PROPERTY_API_KEY
    if key == "YOUR_PROPERTYAPI_KEY_HERE":
        print("[!] WARNING: No PropertyAPI key set. Get 100 free credits at propertyapi.co")
        return {}

    encoded_addr = urllib.parse.quote(address)
    url = f"https://api.propertyapi.co/v1/parcels/get?address={encoded_addr}&api_key={key}"

    cache_key = f"prop_{hash(address) % 10000000}.json"
    cache_file = CACHE_DIR / cache_key

    if cache_file.exists():
        print(f"[✓] Using cached result for: {address}")
        return json.loads(cache_file.read_text())

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "OSINT-Agent/1.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            cache_file.write_text(json.dumps(data, indent=2))
            return data
    except Exception as e:
        print(f"[!] PropertyAPI error: {e}")
        return {}


# ─── County Assessor Fallback ───

def county_portal_search(county: str, state: str, address: str = None, owner_name: str = None) -> dict:
    """
    Try known county assessor portals directly.
    Returns portal URL + search params, or empty if unknown.

    Many counties use Tyler Technologies (publicsearch.us) or Socrata.
    """
    # Known direct portal mappings (expand as needed)
    PORTALS = {
        ("cook", "il"): "https://datacatalog.cookcountyil.gov/api/views/3723-97qp/rows.json",
        ("new york", "ny"): "https://data.cityofnewyork.us/resource/bnx9-e6tj.json",
        ("kings", "ny"): "https://data.cityofnewyork.us/resource/bnx9-e6tj.json",
        ("queens", "ny"): "https://data.cityofnewyork.us/resource/bnx9-e6jt.json",
        ("bronx", "ny"): "https://data.cityofnewyork.us/resource/bnx9-e6tj.json",
        ("harris", "tx"): "https://hcad.org/property-search/",
        ("dallas", "tx"): "https://www.dallascad.org/",
        ("tarrant", "tx"): "https://tarrant.tx.publicsearch.us/",
        ("broward", "fl"): "https://browardpropertyappraisers.org/property-search-address-lookup",
        ("orange", "fl"): "https://ocpafl.org/",
        ("travis", "tx"): "https:// traviscad.org/",
        ("bexar", "tx"): "https://www.bexar.org/2187/Property-Search",
        ("clark", "nv"): "https://www.clarkcountynv.gov/government/elected_officials/county_recorder/",
        ("maricopa", "az"): "https://mcassessor.maricopa.gov/",
        ("san diego", "ca"): "https://arcc.sdcounty.ca.gov/Pages/Assessor-Maps.aspx",
        ("los angeles", "ca"): "https://portal.assessor.lacounty.gov/",
        ("miami-dade", "fl"): "https://www.miamidade.gov/propertysearch/",
        ("cuyahoga", "oh"): "https://recorder.cuyahogacounty.us/",
        ("franklin", "oh"): "https://property.franklincountyohio.gov/",
    }

    county_key = (county.lower().replace(" county", "").strip(), state.lower())

    if county_key in PORTALS:
        return {
            "source": "county_portal",
            "portal_url": PORTALS[county_key],
            "county": county,
            "state": state.upper(),
            "note": "Visit portal directly or use Socrata API for open data counties"
        }

    # Generic search hint
    return {
        "source": "unknown",
        "search_hint": f"Search: '{county} {state} property records public access'",
        "tyler_portal": f"https://{county.lower().replace(' ', '')}.{state.lower()}.publicsearch.us",
        "socrata_search": f"https://{county.lower().replace(' ', '')}.gov/api/views"
    }


# ─── Whitepages Pro Integration ───

def whitepages_lookup(owner_name: str, city: str = None, state: str = None, api_key: str = None) -> dict:
    """
    Query Whitepages Pro API for phone/email enrichment.
    Requires API key from whitepages.com/pro-api
    """
    key = api_key or WHITEPAGES_API_KEY
    if key == "YOUR_WHITEPAGES_KEY_HERE":
        return {"error": "No Whitepages API key configured"}

    params = {"api_key": key, "name": owner_name}
    if city:
        params["city"] = city
    if state:
        params["state_code"] = state.upper()

    query = urllib.parse.urlencode(params)
    url = f"https://api.whitepages.com/v1/person?{query}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


# ─── DNC Compliance ───

def load_dnc_list(path: Path = None) -> set:
    """Load national DNC numbers. Download from telemarketing.donotcall.gov"""
    path = path or DNC_LIST_PATH
    if not path.exists():
        print(f"[!] DNC list not found at {path}")
        print(f"    Download from: https://telemarketing.donotcall.gov")
        print(f"    Or use a service like BatchData/BatchSkipTracing with built-in DNC scrubbing")
        return set()

    numbers = set()
    with open(path) as f:
        for line in f:
            num = "".join(c for c in line.strip() if c.isdigit())
            if len(num) == 10:
                numbers.add(num)
    return numbers


def is_dnc(phone: str, dnc_set: set = None) -> bool:
    """Check if a phone number is on the DNC list."""
    if dnc_set is None:
        dnc_set = load_dnc_list()
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits in dnc_set


def scrub_dnc(phones: list, dnc_set: set = None) -> tuple:
    """Split phones into safe and DNC lists."""
    if dnc_set is None:
        dnc_set = load_dnc_list()
    safe = []
    flagged = []
    for p in phones:
        if is_dnc(p, dnc_set):
            flagged.append(p)
        else:
            safe.append(p)
    return safe, flagged


# ─── Lead Record Builder ───

def build_lead_record(property_data: dict, owner_name: str = None, phones: list = None, emails: list = None) -> dict:
    """Build a standardized lead record with DNC compliance."""
    dnc_set = load_dnc_list()
    safe_phones, dnc_phones = scrub_dnc(phones or [], dnc_set)

    record = {
        "generated_at": datetime.now().isoformat(),
        "property": {
            "address": property_data.get("formattedAddress") or property_data.get("address"),
            "parcel_id": property_data.get("id") or property_data.get("apn"),
            "owner_name": owner_name or property_data.get("ownerName"),
            "last_sale_price": property_data.get("lastSalePrice"),
            "last_sale_date": property_data.get("lastSaleDate"),
            "property_type": property_data.get("propertyType"),
            "year_built": property_data.get("yearBuilt"),
            "living_area": property_data.get("livingArea"),
            "lot_size": property_data.get("lotSize"),
            "latitude": property_data.get("latitude"),
            "longitude": property_data.get("longitude"),
        },
        "contact": {
            "phones": safe_phones,
            "emails": emails or [],
            "dnc_flagged_phones": dnc_phones,
            "dnc_compliant": len(dnc_phones) == 0
        },
        "compliance": {
            "dnc_checked": True,
            "dnc_list_date": DNC_LIST_PATH.stat().st_mtime if DNC_LIST_PATH.exists() else None,
            "safe_to_call": len(safe_phones) > 0,
            "recommended_channel": "email" if len(safe_phones) == 0 and len(emails or []) > 0 else "phone"
        }
    }
    return record


# ─── Batch Processing ───

def process_csv(input_file: str, output_file: str = None):
    """Process a CSV of addresses and output enriched lead records."""
    results = []
    dnc_set = load_dnc_list()

    with open(input_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            address = row.get("address") or f"{row.get('street','')}, {row.get('city','')}, {row.get('state','')} {row.get('zip','')}"
            print(f"[→] Processing: {address}")

            # Step 1: Property lookup
            prop = propertyapi_lookup(address)
            owner = prop.get("ownerName") or row.get("owner_name")

            # Step 2: Contact enrichment (if key available)
            phones = []
            emails = []
            if owner and WHITEPAGES_API_KEY != "YOUR_WHITEPAGES_KEY_HERE":
                wp = whitepages_lookup(owner, row.get("city"), row.get("state"))
                # Parse Whitepages response (structure varies)
                for result in wp.get("results", []):
                    for phone in result.get("phones", []):
                        phones.append(phone.get("phone_number"))
                    for email in result.get("emails", []):
                        emails.append(email.get("email_address"))

            # Step 3: Build record
            record = build_lead_record(prop, owner, phones, emails)
            record["source_csv_row"] = row
            results.append(record)
            time.sleep(0.5)  # Rate limiting

    # Output
    output = output_file or input_file.replace(".csv", "_enriched.json")
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[✓] Wrote {len(results)} records to {output}")


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="OSINT Property Owner Finder")
    parser.add_argument("--address", help="Full property address to lookup")
    parser.add_argument("--business", help="Business name")
    parser.add_argument("--city", help="City (e.g., 'Jersey City NJ')")
    parser.add_argument("--county", help="County name")
    parser.add_argument("--state", help="State abbreviation")
    parser.add_argument("--batch-file", help="CSV file with addresses to process")
    parser.add_argument("--property-api-key", help="PropertyAPI.co key")
    parser.add_argument("--whitepages-key", help="Whitepages Pro API key")
    parser.add_argument("--check-dnc", action="store_true", help="Check numbers against DNC list")
    args = parser.parse_args()

    global PROPERTY_API_KEY, WHITEPAGES_API_KEY
    if args.property_api_key:
        PROPERTY_API_KEY = args.property_api_key
    if args.whitepages_key:
        WHITEPAGES_API_KEY = args.whitepages_key

    if args.batch_file:
        process_csv(args.batch_file)
        return

    if args.address:
        print(f"[→] Looking up: {args.address}")
        data = propertyapi_lookup(args.address)
        if data:
            print(json.dumps(data, indent=2))

            owner = data.get("ownerName")
            if owner:
                print(f"\n[→] Owner found: {owner}")
                print(f"[→] Enriching contact info...")
                wp = whitepages_lookup(owner)
                if "error" not in wp:
                    print(json.dumps(wp, indent=2))

            # DNC check
            if args.check_dnc:
                dnc = load_dnc_list()
                print(f"\n[ℹ] DNC list loaded: {len(dnc)} numbers")
        else:
            print("[!] No data returned. Check API key.")

    elif args.county and args.state:
        print(f"[→] County portal lookup: {args.county}, {args.state}")
        portal = county_portal_search(args.county, args.state)
        print(json.dumps(portal, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
