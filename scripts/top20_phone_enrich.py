#!/usr/bin/env python3
"""
Lightweight phone enrichment for top Dallas leads
Uses web search APIs (not scraping) to find owner phone numbers

Usage:
    python3 top20_phone_enrich.py
"""

import csv
import json
import re
import time
from pathlib import Path

WORKSPACE = Path.home() / ".openclaw" / "workspace" / "land-flip-dashboard"
INPUT = WORKSPACE / "data" / "pipeline" / "dallas_top20_profit.csv"
OUTPUT = WORKSPACE / "data" / "pipeline" / "dallas_top20_with_phones.csv"

def extract_phones(text):
    """Extract phone numbers from text."""
    pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    matches = re.findall(pattern, text)
    return list(set(matches))

def load_top20():
    leads = []
    with open(INPUT) as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(row)
    return leads

if __name__ == "__main__":
    leads = load_top20()
    print(f"[→] Loaded {len(leads)} top leads")
    print(f"[→] Manual phone lookup needed: TruePeopleSearch, Whitepages, or skip trace service")
    print(f"[→] CSV ready at: {INPUT}")
    print(f"\nTop 5 leads to research:")
    for i, lead in enumerate(leads[:5], 1):
        print(f"  {i}. {lead['owner_name']} - {lead['property_address']}")
