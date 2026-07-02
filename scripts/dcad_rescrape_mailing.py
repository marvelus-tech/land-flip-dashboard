#!/usr/bin/env python3
"""
DCAD Mailing Address Re-Scraper
Takes the existing 240 leads and re-scrapes DCAD detail pages
to extract mailing addresses, which the original scrape missed.

Usage:
    python3 dcad_rescrape_mailing.py
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, Page

WORKSPACE = Path.home() / ".openclaw" / "workspace" / "land-flip-dashboard"
INPUT_JSON = WORKSPACE / "data" / "large-lot-dashboard.json"
OUTPUT_JSON = WORKSPACE / "data" / "large-lot-dashboard.json"  # overwrite in place

DCAD_BASE = "https://www.dallascad.org"

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("DCAD_Mailing")


def init_browser(headless: bool = True):
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    return pw, browser, page


def extract_mailing_address(page: Page, account_number: str) -> dict:
    """Navigate to DCAD detail page and extract mailing address from single-line format."""
    url = f"{DCAD_BASE}/AcctDetail.aspx?ID={account_number}"
    result = {
        "mailing_address": "",
        "mailing_city": "",
        "mailing_state": "",
        "mailing_zip": "",
        "is_absentee_owner": False,
    }

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(1.5)

        text = page.inner_text("body")

        # DCAD format (multi-line):
        # Owner (Current 2026)
        #   OWNER NAME
        #   6359 VANDERBILT AVE
        #   DALLAS, TEXAS 752143337
        
        owner_match = re.search(
            r'Owner\s*\(Current\s*\d{4}\)\s*\n\s*([^\n]+)\n\s*([^\n]+)\n\s*([^\n,]+),\s*([A-Z]{2,})\s*(\d{5}(?:\d{4})?)',
            text,
            re.IGNORECASE
        )
        
        if owner_match:
            owner_name = owner_match.group(1).strip()
            street_addr = owner_match.group(2).strip()
            city = owner_match.group(3).strip()
            state = owner_match.group(4).strip()
            zip_code = owner_match.group(5).strip()
            
            result["mailing_address"] = street_addr
            result["mailing_city"] = city
            result["mailing_state"] = state
            result["mailing_zip"] = zip_code
            
            logger.info(f"  {account_number}: owner={owner_name[:30]} | addr={street_addr[:40]} | {city}, {state} {zip_code}")
        else:
            # Fallback: try single-line format (some pages may vary)
            owner_match = re.search(
                r'Owner\s*\(Current\s*\d{4}\)\s*(.+)',
                text,
                re.IGNORECASE
            )
            if owner_match:
                full_line = owner_match.group(1).strip()
                state_zip_match = re.search(r',\s*([A-Z]{2,})\s*(\d{5}(?:\d{4})?)\s*$', full_line)
                if state_zip_match:
                    state = state_zip_match.group(1).strip()
                    zip_code = state_zip_match.group(2).strip()
                    before_comma = full_line[:state_zip_match.start()].strip()
                    addr_start_match = re.search(r'\d', before_comma)
                    if addr_start_match:
                        owner_name = before_comma[:addr_start_match.start()].strip()
                        addr_and_city = before_comma[addr_start_match.start():].strip()
                        words = addr_and_city.split()
                        if len(words) >= 2:
                            city = words[-1]
                            street_addr = ' '.join(words[:-1])
                        else:
                            street_addr = addr_and_city
                            city = 'DALLAS'
                        
                        result["mailing_address"] = street_addr
                        result["mailing_city"] = city
                        result["mailing_state"] = state
                        result["mailing_zip"] = zip_code
                        logger.info(f"  {account_number}: single-line fallback: owner={owner_name[:30]} | addr={street_addr[:40]} | {city}, {state} {zip_code}")
            
            if not result["mailing_address"]:
                logger.info(f"  {account_number}: No mailing address found")

        return result

    except Exception as e:
        logger.error(f"  {account_number}: error - {e}")
        return result


def update_property_with_mailing(prop: dict, mailing: dict) -> dict:
    """Update property dict with mailing address info and recalculate absentee."""
    prop["mailing_address"] = mailing["mailing_address"]
    prop["mailing_city"] = mailing["mailing_city"]
    prop["mailing_state"] = mailing["mailing_state"]
    prop["mailing_zip"] = mailing["mailing_zip"]

    # Recalculate absentee owner
    property_addr = prop.get("property_address", "")
    mailing_addr = mailing["mailing_address"]
    mailing_zip = mailing["mailing_zip"]
    property_zip = prop.get("zip_code", "")

    if mailing_addr and property_addr:
        # Check if street number differs
        street_num = re.search(r'^(\d+)', property_addr)
        if street_num and street_num.group() not in mailing_addr:
            prop["is_absentee_owner"] = True
        elif property_zip and mailing_zip and property_zip != mailing_zip[:5]:
            prop["is_absentee_owner"] = True
        else:
            prop["is_absentee_owner"] = False

    return prop


def main():
    # Load existing data
    with open(INPUT_JSON) as f:
        data = json.load(f)

    properties = data.get("properties", [])
    logger.info(f"Loaded {len(properties)} existing properties")

    # Count how many already have mailing addresses
    have_mailing = sum(1 for p in properties if p.get("mailing_address"))
    logger.info(f"Currently {have_mailing} have mailing addresses, {len(properties) - have_mailing} missing")

    # Filter to those missing mailing addresses
    missing = [p for p in properties if not p.get("mailing_address")]
    logger.info(f"Will re-scrape {len(missing)} properties for mailing addresses")

    if not missing:
        logger.info("All properties already have mailing addresses. Nothing to do.")
        return

    # Initialize browser
    pw, browser, page = init_browser(headless=True)

    try:
        updated_count = 0
        for i, prop in enumerate(missing, 1):
            account = prop.get("account_number", "")
            if not account:
                logger.warning(f"Skipping property {i}: no account number")
                continue

            logger.info(f"[{i}/{len(missing)}] Scraping {account}...")
            mailing = extract_mailing_address(page, account)

            # Update the property in the original data
            for p in properties:
                if p.get("account_number") == account:
                    update_property_with_mailing(p, mailing)
                    updated_count += 1
                    break

            # Periodic save (every 10)
            if i % 10 == 0:
                with open(OUTPUT_JSON, "w") as f:
                    json.dump(data, f, indent=2)
                logger.info(f"  Saved checkpoint after {i} properties")

            time.sleep(1.5 + (i % 3) * 0.5)  # Variable delay to avoid bot detection

    finally:
        browser.close()
        pw.stop()

    # Final save
    with open(OUTPUT_JSON, "w") as f:
        json.dump(data, f, indent=2)

    # Stats
    have_mailing_after = sum(1 for p in properties if p.get("mailing_address"))
    absentee_count = sum(1 for p in properties if p.get("is_absentee_owner"))

    logger.info(f"\n{'='*50}")
    logger.info(f"RE-SCRAPE COMPLETE")
    logger.info(f"{'='*50}")
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Have mailing address: {have_mailing_after} / {len(properties)}")
    logger.info(f"Absentee owners: {absentee_count}")
    logger.info(f"Saved to: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
