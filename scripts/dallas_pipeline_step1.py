#!/usr/bin/env python3
"""
Dallas County Lot Pipeline — Step 1: Import & Format
Takes the 240 scraped DCAD leads and formats them for the land-flip dashboard.
Adds status tracking, prepares for phone enrichment, exports clean CSVs.

Usage:
    python3 dallas_pipeline_step1.py
"""

import json
import csv
from pathlib import Path
from datetime import datetime
from collections import Counter

WORKSPACE = Path.home() / ".openclaw" / "workspace" / "land-flip-dashboard"
INPUT_JSON = WORKSPACE / "data" / "large-lot-dashboard.json"
OUTPUT_DIR = WORKSPACE / "data" / "pipeline"
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── Load raw DCAD data ───
with open(INPUT_JSON) as f:
    raw_data = json.load(f)
raw_properties = raw_data.get("properties", [])

print(f"[→] Loaded {len(raw_properties)} raw DCAD properties")

# ─── Normalize to pipeline format ───
pipeline_lots = []

for p in raw_properties:
    # Parse owner name into first/last for outreach scripts
    owner_raw = p.get("owner_name", "")
    
    # Skip LLCs, trusts, estates for now (harder to find direct phones)
    # But keep them in data — we'll flag them
    owner_type = "individual"
    if any(x in owner_raw.upper() for x in ["LLC", "TRUST", "ESTATE", "INC", "LP", "TR"]):
        owner_type = "entity"
    
    # Extract street name from property address for neighborhood grouping
    prop_addr = p.get("property_address", "")
    street_name = ""
    if prop_addr:
        parts = prop_addr.split()
        if len(parts) >= 2:
            # Skip house number, take street name
            street_name = parts[1] if not parts[1].isdigit() else (parts[2] if len(parts) > 2 else "")
    
    lot = {
        # Core identifiers
        "id": p.get("account_number", ""),
        "property_address": prop_addr,
        "city": "Dallas",
        "state": "TX",
        "county": "Dallas",
        "zip": p.get("search_zip", ""),
        
        # Owner info
        "owner_name": owner_raw,
        "owner_type": owner_type,
        
        # Property details
        "lot_size_sqft": p.get("lot_size_sqft", 0),
        "year_built": p.get("year_built", 0),
        "land_value": p.get("land_value", 0),
        "improvement_value": p.get("improvement_value", 0),
        "total_value": p.get("total_value", 0),
        "improvement_ratio": p.get("improvement_ratio", 0),
        "property_type": p.get("property_type", ""),
        
        # Pipeline status
        "status": "new",
        "priority": "B" if owner_type == "individual" else "C",
        
        # Scoring
        "score": p.get("score", "C"),
        "score_reasons": p.get("score_reasons", ""),
        "meets_budget": p.get("meets_budget", False),
        "potential_profit": p.get("potential_profit", 0),
        
        # Enrichment (empty — ready to fill)
        "phone": "",
        "phone_source": "",
        "mailing_address": "",
        "mailing_city": "",
        "mailing_state": "",
        
        # Underwriting (empty — manual or future auto)
        "infill_status": None,
        "utilities": None,
        "road_access": None,
        "flood_zone": "",
        "zoning": "",
        
        # Source tracking
        "source": "DCAD_scrape",
        "source_url": p.get("dcad_url", ""),
        "scraped_at": p.get("scraped_at", ""),
        "imported_at": datetime.now().isoformat(),
        
        # Notes
        "notes": "",
        "outreach_attempts": 0,
        "last_contact": "",
    }
    pipeline_lots.append(lot)

# ─── Sort by priority + profit potential ───
pipeline_lots.sort(key=lambda x: (
    0 if x["priority"] == "A" else 1 if x["priority"] == "B" else 2,
    -x["potential_profit"]
))

# ─── Save pipeline JSON ───
pipeline_json = OUTPUT_DIR / "dallas_lots_pipeline.json"
with open(pipeline_json, "w") as f:
    json.dump(pipeline_lots, f, indent=2)

print(f"[✓] Saved {len(pipeline_lots)} lots to pipeline JSON")

# ─── Export CSVs for different uses ───

# 1. Full pipeline CSV (for dashboard import)
full_csv = OUTPUT_DIR / "dallas_lots_full.csv"
if pipeline_lots:
    with open(full_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=pipeline_lots[0].keys())
        writer.writeheader()
        writer.writerows(pipeline_lots)
    print(f"[✓] Full pipeline CSV: {full_csv}")

# 2. Phone enrichment ready CSV (name + city + state for dorking)
phone_csv = OUTPUT_DIR / "dallas_phone_enrichment_ready.csv"
with open(phone_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "owner_name", "city", "state", "property_address", "owner_type"])
    writer.writeheader()
    for lot in pipeline_lots:
        if lot["owner_type"] == "individual":
            writer.writerow({
                "id": lot["id"],
                "owner_name": lot["owner_name"],
                "city": lot["city"],
                "state": lot["state"],
                "property_address": lot["property_address"],
                "owner_type": lot["owner_type"]
            })

individual_count = sum(1 for l in pipeline_lots if l["owner_type"] == "individual")
print(f"[✓] Phone enrichment CSV: {phone_csv} ({individual_count} individual owners)")

# 3. Quick-view summary CSV (top 20 by profit)
top_csv = OUTPUT_DIR / "dallas_top20_profit.csv"
top20 = [l for l in pipeline_lots if l["meets_budget"]][:20]
with open(top_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "property_address", "owner_name", "owner_type", "lot_size_sqft", 
        "land_value", "potential_profit", "score", "status", "dcad_url"
    ])
    writer.writeheader()
    for lot in top20:
        writer.writerow({
            "property_address": lot["property_address"],
            "owner_name": lot["owner_name"],
            "owner_type": lot["owner_type"],
            "lot_size_sqft": lot["lot_size_sqft"],
            "land_value": lot["land_value"],
            "potential_profit": lot["potential_profit"],
            "score": lot["score"],
            "status": lot["status"],
            "dcad_url": lot["source_url"]
        })

print(f"[✓] Top 20 profit CSV: {top_csv} ({len(top20)} lots meet budget)")

# ─── Stats ───
print(f"\n{'='*50}")
print("DALLAS COUNTY PIPELINE — STEP 1 COMPLETE")
print(f"{'='*50}")
print(f"Total lots:           {len(pipeline_lots)}")
print(f"Individual owners:      {individual_count} (ready for phone enrichment)")
print(f"Entity owners:        {len(pipeline_lots) - individual_count} (LLCs, trusts, etc.)")
print(f"Meet budget filter:   {sum(1 for l in pipeline_lots if l['meets_budget'])}")

zip_dist = Counter(l["zip"] for l in pipeline_lots)
print(f"\nZIP distribution:")
for zip_code, count in zip_dist.most_common():
    print(f"  {zip_code}: {count}")

print(f"\nNext step:")
print(f"  Run phone enrichment on: {phone_csv}")
print(f"  Or manually research top 20: {top_csv}")
print(f"\nAll files in: {OUTPUT_DIR}")
