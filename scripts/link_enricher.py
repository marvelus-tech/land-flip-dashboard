#!/usr/bin/env python3
"""
SpaceX-grade Link Enrichment Engine
Generates due-diligence links for every land lot:
- Zillow property search
- Google Maps (street + satellite)
- County Property Appraiser / Tax Records
- FEMA Flood Map
- County GIS Parcel Viewer

Usage:
    python3 link_enricher.py --csv data.csv --output enriched.csv
    python3 link_enricher.py --json lots.json --output enriched.json
"""

import json
import csv
import re
import argparse
import urllib.parse
from pathlib import Path
from datetime import datetime

# ─── COUNTY PORTAL MAPPING ───
COUNTY_PORTALS = {
    ('Dallas County', 'TX'): {
        'appraiser': 'https://www.dallascad.org/AcctDetailRes.aspx?ID={account_number}',
        'gis': 'https://dallascad.org/',
    },
    ('Travis County', 'TX'): {
        'appraiser': 'https://travis.traviscad.org/',
        'gis': 'https://maps.traviscountytx.gov/',
    },
    ('Wake County', 'NC'): {
        'appraiser': 'https://www.wakegov.com/',
        'gis': 'https://maps.wakegov.com/',
    },
    ('Rutherford County', 'TN'): {
        'appraiser': 'https://www.rutherfordcountytn.gov/',
    },
    ('Wilson County', 'TN'): {
        'appraiser': 'https://www.wilsoncountytn.gov/',
    },
    ('Montgomery County', 'TX'): {
        'appraiser': 'https://www.mcad-tx.org/',
    },
    ('Greenville County', 'SC'): {
        'appraiser': 'https://www.greenvillecounty.org/',
    },
    ('Fulton County', 'GA'): {
        'appraiser': 'https://www.fultoncountyga.gov/',
    },
    ('Allegheny County', 'PA'): {
        'appraiser': 'https://www.alleghenycounty.us/',
    },
    ('Westmoreland County', 'PA'): {
        'appraiser': 'https://www.westmorelandcounty.org/',
    },
    ('Maricopa County', 'AZ'): {
        'appraiser': 'https://mcassessor.maricopa.gov/',
    },
    ('Orange County', 'FL'): {
        'appraiser': 'https://www.ocpafl.org/',
    },
    ('Franklin County', 'OH'): {
        'appraiser': 'https://property.franklincountyohio.gov/',
    },
    ('Ada County', 'ID'): {
        'appraiser': 'https://www.adacounty.id.gov/',
    },
    ('Marion County', 'IN'): {
        'appraiser': 'https://www.indy.gov/',
    },
}


def normalize_address(addr: str) -> str:
    """Clean address for URL generation."""
    if not addr:
        return ''
    # Remove extra spaces, normalize
    addr = re.sub(r'\s+', ' ', addr.strip())
    # Remove unit/apt numbers for Zillow search
    addr = re.sub(r'\s+(UNIT|APT|#|SUITE|STE)\s*.*$', '', addr, flags=re.IGNORECASE)
    return addr


def generate_zillow_url(address: str, city: str, state: str, zip_code: str) -> str:
    """Generate Zillow search URL."""
    addr = normalize_address(address)
    if not addr:
        return ''
    
    # Build Zillow URL pattern: /homes/ADDRESS-CITY-STATE-ZIP_rb/
    parts = []
    parts.append(addr.replace(' ', '-'))
    if city:
        parts.append(city.replace(' ', '-'))
    if state:
        parts.append(state.lower().replace(' ', '-'))
    if zip_code:
        parts.append(zip_code)
    
    path = '-'.join(parts)
    # Clean up any double dashes
    path = re.sub(r'-+', '-', path)
    return f'https://www.zillow.com/homes/{path}_rb/'


def generate_google_maps_url(address: str, city: str, state: str, zip_code: str) -> str:
    """Generate Google Maps search URL."""
    addr = normalize_address(address)
    query = ', '.join(filter(None, [addr, city, state, zip_code]))
    if not query:
        return ''
    return f'https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}'


def generate_fema_flood_url(address: str, city: str, state: str, zip_code: str) -> str:
    """Generate FEMA Flood Map URL."""
    addr = normalize_address(address)
    query = ', '.join(filter(None, [addr, city, state, zip_code]))
    if not query:
        return ''
    return f'https://msc.fema.gov/portal/search?address={urllib.parse.quote(query)}'


def get_county_links(county: str, state: str, account_number: str = '') -> dict:
    """Get county-specific portal links."""
    key = (county, state.upper())
    links = {}
    
    if key in COUNTY_PORTALS:
        portal = COUNTY_PORTALS[key]
        if 'appraiser' in portal:
            url = portal['appraiser']
            if '{account_number}' in url and account_number:
                url = url.format(account_number=account_number)
            links['county_appraiser'] = url
        if 'gis' in portal:
            links['county_gis'] = portal['gis']
    
    return links


def infer_county_from_dcad(dcad_url: str) -> tuple:
    """Infer county/state from DCAD URL or other known patterns."""
    if not dcad_url:
        return '', ''
    url_lower = dcad_url.lower()
    if 'dallascad.org' in url_lower:
        return 'Dallas County', 'TX'
    if 'travis' in url_lower:
        return 'Travis County', 'TX'
    if 'wakegov' in url_lower or 'wake' in url_lower:
        return 'Wake County', 'NC'
    return '', ''


def enrich_csv_row(row: dict) -> dict:
    """Enrich a single CSV row with links."""
    address = row.get('property_address', '') or row.get('address', '')
    city = row.get('mailing_city', '') or row.get('city', '')
    state = row.get('mailing_state', '') or row.get('state', '')
    zip_code = row.get('zip_code', '') or row.get('zip', '') or row.get('search_zip', '')
    county = row.get('county', '')
    account_number = row.get('account_number', '')
    dcad_url = row.get('dcad_url', '')
    
    # Normalize state
    if state:
        state = state.upper().strip()
    
    # Infer county from DCAD if missing
    if not county and dcad_url:
        inferred_county, inferred_state = infer_county_from_dcad(dcad_url)
        if inferred_county:
            county = inferred_county
        if inferred_state and not state:
            state = inferred_state
    
    # Generate links
    row['zillow_url'] = generate_zillow_url(address, city, state, zip_code)
    row['google_maps_url'] = generate_google_maps_url(address, city, state, zip_code)
    row['fema_flood_url'] = generate_fema_flood_url(address, city, state, zip_code)
    
    # County-specific links
    if county and state:
        county_links = get_county_links(county, state, account_number)
        row['county_appraiser_url'] = county_links.get('county_appraiser', '')
        row['county_gis_url'] = county_links.get('county_gis', '')
    
    row['links_enriched_at'] = datetime.now().isoformat()
    return row


def enrich_json_lot(lot: dict) -> dict:
    """Enrich a single JSON lot with links."""
    address = lot.get('address', '') or lot.get('propertyAddress', '')
    city = lot.get('city', '')
    state = lot.get('state', '')
    zip_code = lot.get('zip', '') or lot.get('zip_code', '')
    county = lot.get('county', '')
    account_number = lot.get('accountNumber', '') or lot.get('account_number', '')
    
    # Normalize state from full names to abbreviations
    state_map = {
        'texas': 'TX', 'north-carolina': 'NC', 'tennessee': 'TN',
        'south-carolina': 'SC', 'georgia': 'GA', 'pennsylvania': 'PA',
        'arizona': 'AZ', 'florida': 'FL', 'ohio': 'OH', 'idaho': 'ID',
        'indiana': 'IN', 'dallas': 'TX',
    }
    if state and len(state) > 2:
        state = state_map.get(state.lower(), state)
    if state:
        state = state.upper()
    
    lot['zillowUrl'] = generate_zillow_url(address, city, state, zip_code)
    lot['mapUrl'] = generate_google_maps_url(address, city, state, zip_code)
    lot['femaFloodUrl'] = generate_fema_flood_url(address, city, state, zip_code)
    
    if county and state:
        county_links = get_county_links(county, state, account_number)
        lot['countyLinks'] = county_links
    
    lot['linksEnrichedAt'] = datetime.now().isoformat()
    return lot


def main():
    parser = argparse.ArgumentParser(description='Enrich land lots with due-diligence links')
    parser.add_argument('--csv', '-c', help='Input CSV file')
    parser.add_argument('--json', '-j', help='Input JSON file')
    parser.add_argument('--output', '-o', required=True, help='Output file')
    parser.add_argument('--report', '-r', default='link_enrichment_report.txt', help='Report file')
    args = parser.parse_args()
    
    if args.csv:
        with open(args.csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"[→] Loaded {len(rows)} rows from {args.csv}")
        
        enriched = [enrich_csv_row(row) for row in rows]
        
        with open(args.output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=enriched[0].keys())
            writer.writeheader()
            writer.writerows(enriched)
        
        print(f"[✓] Enriched CSV saved to {args.output}")
        
        # Stats
        with_zillow = sum(1 for r in enriched if r.get('zillow_url'))
        with_maps = sum(1 for r in enriched if r.get('google_maps_url'))
        with_fema = sum(1 for r in enriched if r.get('fema_flood_url'))
        with_county = sum(1 for r in enriched if r.get('county_appraiser_url'))
        
        report = f"""Link Enrichment Report
Generated: {datetime.now().isoformat()}
Total Records: {len(enriched)}

Links Generated:
  Zillow URLs:       {with_zillow}/{len(enriched)}
  Google Maps URLs:  {with_maps}/{len(enriched)}
  FEMA Flood URLs:   {with_fema}/{len(enriched)}
  County Appraiser:  {with_county}/{len(enriched)}
"""
    
    elif args.json:
        with open(args.json, 'r', encoding='utf-8') as f:
            lots = json.load(f)
        
        print(f"[→] Loaded {len(lots)} lots from {args.json}")
        
        enriched = [enrich_json_lot(lot) for lot in lots]
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(enriched, f, indent=2)
        
        print(f"[✓] Enriched JSON saved to {args.output}")
        
        # Stats
        with_zillow = sum(1 for l in enriched if l.get('zillowUrl'))
        with_maps = sum(1 for l in enriched if l.get('mapUrl'))
        with_fema = sum(1 for l in enriched if l.get('femaFloodUrl'))
        
        report = f"""Link Enrichment Report
Generated: {datetime.now().isoformat()}
Total Records: {len(enriched)}

Links Generated:
  Zillow URLs:       {with_zillow}/{len(enriched)}
  Google Maps URLs:  {with_maps}/{len(enriched)}
  FEMA Flood URLs:   {with_fema}/{len(enriched)}
"""
    
    else:
        print("Error: Provide --csv or --json")
        return
    
    with open(args.report, 'w') as f:
        f.write(report)
    
    print(f"[✓] Report saved to {args.report}")
    print(report)


if __name__ == '__main__':
    main()
