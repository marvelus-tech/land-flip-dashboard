#!/usr/bin/env python3
"""
SpaceX-grade Land Comping Engine
Analyzes comparable land sales and generates suggested offer prices.

Usage:
    python3 land_comping.py --input lots.json --market-data comps.json --output comped.json
    python3 land_comping.py --csv leads.csv --market-data comps.json --output comped.csv

Market Data Format (comps.json):
{
  "market_comps": [
    {
      "zip": "75218",
      "city": "Dallas",
      "state": "TX",
      "county": "Dallas County",
      "comps": [
        {"address": "123 Main St", "acres": 0.25, "sale_price": 450000, "sale_date": "2026-03-15", "source": "MLS"},
        {"address": "456 Oak Ave", "acres": 0.33, "sale_price": 520000, "sale_date": "2026-04-20", "source": "Redfin"}
      ],
      "notes": "Hot market, low inventory"
    }
  ]
}
"""

import json
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from statistics import median, mean


def calculate_zip_metrics(comps: list) -> dict:
    """Calculate market metrics from comparable sales."""
    if not comps:
        return {
            'avg_price_per_acre': None,
            'median_price_per_acre': None,
            'min_price_per_acre': None,
            'max_price_per_acre': None,
            'avg_sale_price': None,
            'median_sale_price': None,
            'comp_count': 0,
            'avg_acres': None,
            'price_range_low': None,
            'price_range_high': None,
        }
    
    prices_per_acre = []
    sale_prices = []
    acres_list = []
    
    for comp in comps:
        acres = comp.get('acres', 0)
        price = comp.get('sale_price', 0)
        if acres and price and acres > 0:
            ppa = price / acres
            prices_per_acre.append(ppa)
            sale_prices.append(price)
            acres_list.append(acres)
    
    if not prices_per_acre:
        return {
            'avg_price_per_acre': None,
            'median_price_per_acre': None,
            'min_price_per_acre': None,
            'max_price_per_acre': None,
            'avg_sale_price': None,
            'median_sale_price': None,
            'comp_count': len(comps),
            'avg_acres': None,
            'price_range_low': None,
            'price_range_high': None,
        }
    
    return {
        'avg_price_per_acre': round(mean(prices_per_acre), 2),
        'median_price_per_acre': round(median(prices_per_acre), 2),
        'min_price_per_acre': round(min(prices_per_acre), 2),
        'max_price_per_acre': round(max(prices_per_acre), 2),
        'avg_sale_price': round(mean(sale_prices), 2) if sale_prices else None,
        'median_sale_price': round(median(sale_prices), 2) if sale_prices else None,
        'comp_count': len(comps),
        'avg_acres': round(mean(acres_list), 3) if acres_list else None,
        'price_range_low': round(min(sale_prices), 2) if sale_prices else None,
        'price_range_high': round(max(sale_prices), 2) if sale_prices else None,
    }


def suggest_offer_price(market_value: float, strategy: str = 'wholesale') -> dict:
    """
    Suggest offer price based on strategy.
    
    Strategies:
    - wholesale: 30-50% of market value (assign to builder)
    - flip: 50-70% of market value (close and resell)
    - hold: 70-85% of market value (long-term land bank)
    """
    strategy_params = {
        'wholesale': {'low_pct': 0.30, 'target_pct': 0.40, 'high_pct': 0.50, 'label': 'Wholesale'},
        'flip': {'low_pct': 0.50, 'target_pct': 0.60, 'high_pct': 0.70, 'label': 'Flip'},
        'hold': {'low_pct': 0.70, 'target_pct': 0.77, 'high_pct': 0.85, 'label': 'Land Bank'},
    }
    
    params = strategy_params.get(strategy, strategy_params['wholesale'])
    
    return {
        'strategy': strategy,
        'strategy_label': params['label'],
        'market_value': round(market_value, 2),
        'offer_low': round(market_value * params['low_pct'], 2),
        'offer_target': round(market_value * params['target_pct'], 2),
        'offer_high': round(market_value * params['high_pct'], 2),
        'potential_profit_low': round(market_value * (1 - params['high_pct']), 2),
        'potential_profit_target': round(market_value * (1 - params['target_pct']), 2),
        'potential_profit_high': round(market_value * (1 - params['low_pct']), 2),
    }


def score_deal(listing_price: float, offer_target: float, market_value: float, acres: float = None) -> dict:
    """
    Score a deal A/B/C/D based on offer vs listing price.
    
    A: Offer is <= 60% of listing (great deal)
    B: Offer is 60-75% of listing (good deal)
    C: Offer is 75-90% of listing (fair deal)
    D: Offer is > 90% of listing (thin margin)
    """
    if not listing_price or listing_price <= 0:
        return {'grade': 'N/A', 'margin_pct': None, 'notes': 'No listing price available'}
    
    margin_pct = (listing_price - offer_target) / listing_price * 100
    
    if margin_pct >= 40:
        grade = 'A'
        notes = 'Excellent margin. Strong wholesale candidate.'
    elif margin_pct >= 25:
        grade = 'B'
        notes = 'Good margin. Viable deal with negotiation.'
    elif margin_pct >= 10:
        grade = 'C'
        notes = 'Thin margin. Only if motivated seller or value-add.'
    else:
        grade = 'D'
        notes = 'Poor margin. Skip unless unique circumstances.'
    
    return {
        'grade': grade,
        'margin_pct': round(margin_pct, 1),
        'margin_dollars': round(listing_price - offer_target, 2),
        'notes': notes,
    }


def comp_lot(lot: dict, market_data: dict, strategy: str = 'wholesale') -> dict:
    """Comp a single lot against market data."""
    zip_code = lot.get('zip', '') or lot.get('zip_code', '') or lot.get('search_zip', '')
    acres = lot.get('acres')
    price = lot.get('price')
    
    # Find market comps for this ZIP
    zip_comps = None
    for market in market_data.get('market_comps', []):
        if market.get('zip') == zip_code:
            zip_comps = market
            break
    
    # If no ZIP match, try city+state
    if not zip_comps:
        city = lot.get('city', '')
        state = lot.get('state', '')
        for market in market_data.get('market_comps', []):
            if market.get('city', '').lower() == city.lower() and market.get('state', '').lower() == state.lower():
                zip_comps = market
                break
    
    # Calculate market metrics
    if zip_comps:
        metrics = calculate_zip_metrics(zip_comps.get('comps', []))
        lot['market_metrics'] = metrics
        
        # Estimate market value
        if acres and metrics.get('median_price_per_acre'):
            estimated_value = acres * metrics['median_price_per_acre']
        elif price:
            estimated_value = price  # Use listing as market proxy
        else:
            estimated_value = None
        
        if estimated_value:
            offer = suggest_offer_price(estimated_value, strategy)
            lot['suggested_offer'] = offer
            
            # Score the deal
            if price:
                deal_score = score_deal(price, offer['offer_target'], estimated_value, acres)
                lot['deal_score'] = deal_score
    else:
        lot['market_metrics'] = {'comp_count': 0, 'notes': 'No comps available for this ZIP'}
        
        # Fallback: use land_value from tax records if available
        land_value = lot.get('land_value') or lot.get('landValue')
        if land_value and acres:
            estimated_value = float(land_value)
            offer = suggest_offer_price(estimated_value, strategy)
            lot['suggested_offer'] = offer
            if price:
                deal_score = score_deal(price, offer['offer_target'], estimated_value, acres)
                lot['deal_score'] = deal_score
    
    lot['comped_at'] = datetime.now().isoformat()
    return lot


def load_market_data(path: str) -> dict:
    """Load market comp data from JSON."""
    with open(path) as f:
        return json.load(f)


def generate_sample_comps() -> dict:
    """Generate sample market comp data for Dallas ZIPs."""
    return {
        "market_comps": [
            {
                "zip": "75218",
                "city": "Dallas",
                "state": "TX",
                "county": "Dallas County",
                "comps": [
                    {"address": "4500 Peavy Rd", "acres": 0.25, "sale_price": 420000, "sale_date": "2026-04-15", "source": "MLS"},
                    {"address": "4623 Peavy Rd", "acres": 0.28, "sale_price": 485000, "sale_date": "2026-05-20", "source": "Redfin"},
                    {"address": "4801 Peavy Rd", "acres": 0.30, "sale_price": 510000, "sale_date": "2026-03-10", "source": "Zillow"},
                ],
                "notes": "Lake Highlands area. Steady demand."
            },
            {
                "zip": "75214",
                "city": "Dallas",
                "state": "TX",
                "county": "Dallas County",
                "comps": [
                    {"address": "1200 Lakewood Blvd", "acres": 0.22, "sale_price": 550000, "sale_date": "2026-04-01", "source": "MLS"},
                    {"address": "1400 Lakewood Blvd", "acres": 0.25, "sale_price": 620000, "sale_date": "2026-05-15", "source": "Redfin"},
                ],
                "notes": "Lakewood premium area. Higher $/acre."
            },
            {
                "zip": "27604",
                "city": "Raleigh",
                "state": "NC",
                "county": "Wake County",
                "comps": [
                    {"address": "1800 Rankin St", "acres": 0.25, "sale_price": 380000, "sale_date": "2026-03-20", "source": "MLS"},
                    {"address": "2000 Skycrest Dr", "acres": 0.24, "sale_price": 365000, "sale_date": "2026-04-10", "source": "Zillow"},
                ],
                "notes": "Inside beltline Raleigh. Strong infill market."
            },
            {
                "zip": "78757",
                "city": "Austin",
                "state": "TX",
                "county": "Travis County",
                "comps": [
                    {"address": "1206 Ruth Ave", "acres": 0.33, "sale_price": 599000, "sale_date": "2026-05-01", "source": "MLS"},
                    {"address": "1400 Ruth Ave", "acres": 0.30, "sale_price": 575000, "sale_date": "2026-04-15", "source": "Redfin"},
                    {"address": "900 Morrow St", "acres": 0.74, "sale_price": 1850000, "sale_date": "2026-03-20", "source": "MLS"},
                ],
                "notes": "Crestview/Allandale. Hot infill market."
            },
            {
                "zip": "78721",
                "city": "Austin",
                "state": "TX",
                "county": "Travis County",
                "comps": [
                    {"address": "1201 Fort Branch Blvd", "acres": 0.23, "sale_price": 200000, "sale_date": "2026-04-01", "source": "FSBO"},
                    {"address": "3600 Oak Springs Dr", "acres": 0.17, "sale_price": 180000, "sale_date": "2026-05-10", "source": "Zillow"},
                ],
                "notes": "East Austin. Gentrifying area. Rising prices."
            },
            {
                "zip": "78734",
                "city": "Austin",
                "state": "TX",
                "county": "Travis County",
                "comps": [
                    {"address": "3109 Geronimo Trail", "acres": 0.93, "sale_price": 350000, "sale_date": "2026-03-15", "source": "FSBO"},
                    {"address": "3707 Highland Dr", "acres": 0.18, "sale_price": 320000, "sale_date": "2026-04-20", "source": "Zillow"},
                ],
                "notes": "Lake Travis area. Waterfront premium."
            },
        ]
    }


def main():
    parser = argparse.ArgumentParser(description='Land comping engine')
    parser.add_argument('--input', '-i', help='Input JSON file')
    parser.add_argument('--csv', '-c', help='Input CSV file')
    parser.add_argument('--market-data', '-m', help='Market comps JSON file')
    parser.add_argument('--strategy', '-s', default='wholesale', choices=['wholesale', 'flip', 'hold'])
    parser.add_argument('--output', '-o', required=True, help='Output file')
    parser.add_argument('--generate-sample-comps', action='store_true', help='Generate sample comps file')
    args = parser.parse_args()
    
    if args.generate_sample_comps:
        sample = generate_sample_comps()
        with open('sample_comps.json', 'w') as f:
            json.dump(sample, f, indent=2)
        print("[✓] Generated sample_comps.json")
        return
    
    # Load market data
    if args.market_data:
        market_data = load_market_data(args.market_data)
    else:
        print("No market data provided. Use --generate-sample-comps to create a template.")
        market_data = {'market_comps': []}
    
    if args.csv:
        with open(args.csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"[→] Loaded {len(rows)} rows from {args.csv}")
        
        # Convert CSV rows to lot format and comp
        enriched = []
        for row in rows:
            lot = {
                'address': row.get('property_address', ''),
                'city': row.get('mailing_city', ''),
                'state': row.get('mailing_state', ''),
                'zip': row.get('zip_code', '') or row.get('search_zip', ''),
                'acres': float(row['lot_size_sqft']) / 43560 if row.get('lot_size_sqft') else None,
                'price': float(row['land_value']) if row.get('land_value') else None,
                'land_value': float(row['land_value']) if row.get('land_value') else None,
                'account_number': row.get('account_number', ''),
            }
            comped = comp_lot(lot, market_data, args.strategy)
            
            # Merge back into CSV row
            if 'market_metrics' in comped:
                mm = comped['market_metrics']
                row['comp_count'] = mm.get('comp_count', 0)
                row['median_price_per_acre'] = mm.get('median_price_per_acre', '')
                row['market_value_estimate'] = mm.get('median_price_per_acre', 0) * (float(row['lot_size_sqft']) / 43560) if mm.get('median_price_per_acre') and row.get('lot_size_sqft') else ''
            
            if 'suggested_offer' in comped:
                so = comped['suggested_offer']
                row['offer_strategy'] = so['strategy_label']
                row['offer_target'] = so['offer_target']
                row['offer_low'] = so['offer_low']
                row['offer_high'] = so['offer_high']
                row['potential_profit'] = so['potential_profit_target']
            
            if 'deal_score' in comped:
                ds = comped['deal_score']
                row['deal_grade'] = ds['grade']
                row['deal_margin_pct'] = ds['margin_pct']
                row['deal_notes'] = ds['notes']
            
            enriched.append(row)
        
        with open(args.output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=enriched[0].keys())
            writer.writeheader()
            writer.writerows(enriched)
        
        print(f"[✓] Comped CSV saved to {args.output}")
    
    elif args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            lots = json.load(f)
        
        print(f"[→] Loaded {len(lots)} lots from {args.input}")
        
        enriched = [comp_lot(lot, market_data, args.strategy) for lot in lots]
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(enriched, f, indent=2)
        
        print(f"[✓] Comped JSON saved to {args.output}")
    
    else:
        print("Error: Provide --input (JSON) or --csv (CSV)")
        return
    
    # Summary
    has_offers = sum(1 for item in enriched if item.get('offer_target') or (isinstance(item, dict) and 'suggested_offer' in item))
    a_grades = sum(1 for item in enriched if item.get('deal_grade') == 'A' or (isinstance(item, dict) and item.get('deal_score', {}).get('grade') == 'A'))
    b_grades = sum(1 for item in enriched if item.get('deal_grade') == 'B' or (isinstance(item, dict) and item.get('deal_score', {}).get('grade') == 'B'))
    
    print(f"\nSUMMARY:")
    print(f"  Total processed: {len(enriched)}")
    print(f"  With offers:     {has_offers}")
    print(f"  A-grade deals:   {a_grades}")
    print(f"  B-grade deals:   {b_grades}")


if __name__ == '__main__':
    main()
