#!/usr/bin/env python3
"""
SpaceX-grade Dashboard Updater
Updates the land-flip-dashboard index.html with enriched, comped data.

Usage:
    python3 update_dashboard.py --lots data/dashboard-lots-comped.json --html index.html --output index.html
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime


def json_to_js_value(value):
    """Convert Python value to JavaScript literal."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Escape quotes and backslashes
        escaped = value.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
        return f"'{escaped}'"
    if isinstance(value, list):
        return '[' + ', '.join(json_to_js_value(v) for v in value) + ']'
    if isinstance(value, dict):
        pairs = [f"{json_to_js_value(k)}: {json_to_js_value(v)}" for k, v in value.items()]
        return '{' + ', '.join(pairs) + '}'
    return str(value)


def lot_to_js_literal(lot: dict) -> str:
    """Convert a lot dict to a JS object literal string."""
    fields = {}
    
    # Core fields
    fields['id'] = lot.get('id')
    fields['address'] = lot.get('address', '')
    fields['county'] = lot.get('county', '')
    fields['state'] = lot.get('state', '')
    fields['city'] = lot.get('city', '')
    fields['zip'] = lot.get('zip', '')
    fields['acres'] = lot.get('acres')
    fields['price'] = lot.get('price')
    fields['status'] = lot.get('status', 'identified')
    fields['notes'] = lot.get('notes', '')
    fields['source'] = lot.get('source', '')
    fields['date'] = lot.get('date', '')
    
    # URLs
    fields['zillowUrl'] = lot.get('zillowUrl', '')
    fields['mapUrl'] = lot.get('mapUrl', '')
    fields['femaFloodUrl'] = lot.get('femaFloodUrl', '')
    if 'countyLinks' in lot:
        fields['countyLinks'] = lot['countyLinks']
    
    # Owner info
    fields['ownerName'] = lot.get('ownerName', '')
    fields['ownerPhone'] = lot.get('ownerPhone', '')
    fields['ownerEmail'] = lot.get('ownerEmail', '')
    fields['ownerMailingAddress'] = lot.get('ownerMailingAddress', '')
    fields['ownerType'] = lot.get('ownerType', '')
    fields['taxStatus'] = lot.get('taxStatus', '')
    fields['yearsOwned'] = lot.get('yearsOwned', '')
    
    # Comp data
    if 'suggested_offer' in lot:
        so = lot['suggested_offer']
        fields['offerTarget'] = so.get('offer_target')
        fields['offerLow'] = so.get('offer_low')
        fields['offerHigh'] = so.get('offer_high')
        fields['marketValue'] = so.get('market_value')
        fields['potentialProfit'] = so.get('potential_profit_target')
        fields['offerStrategy'] = so.get('strategy_label', '')
    
    if 'deal_score' in lot:
        ds = lot['deal_score']
        fields['dealGrade'] = ds.get('grade', '')
        fields['dealMargin'] = ds.get('margin_pct')
        fields['dealNotes'] = ds.get('notes', '')
    
    if 'market_metrics' in lot:
        mm = lot['market_metrics']
        fields['medianPricePerAcre'] = mm.get('median_price_per_acre')
        fields['compCount'] = mm.get('comp_count', 0)
    
    # Source URL
    fields['sourceUrl'] = lot.get('sourceUrl', '')
    
    # Build JS object
    pairs = []
    for k, v in fields.items():
        if v is not None and v != '':
            pairs.append(f"{k}: {json_to_js_value(v)}")
    
    return '{' + ', '.join(pairs) + '}'


def generate_default_lots(lots: list) -> str:
    """Generate the DEFAULT_LOTS JavaScript array."""
    js_lots = [lot_to_js_literal(lot) for lot in lots]
    return 'const DEFAULT_LOTS = [\n            ' + ',\n            '.join(js_lots) + '\n        ];'


def update_html(html: str, lots: list) -> str:
    """Update the HTML with new lot data and enhanced rendering."""
    
    # 1. Replace DEFAULT_LOTS array
    new_lots_js = generate_default_lots(lots)
    
    # Find and replace the DEFAULT_LOTS block
    pattern = r'const DEFAULT_LOTS = \[.*?\];'
    html = re.sub(pattern, new_lots_js, html, flags=re.DOTALL)
    
    # 2. Update the lot-meta section to show offer info
    # Find the lot-meta div pattern and enhance it
    old_meta = '''<div class="lot-meta">
                        <span>${acresStr}</span>
                        <span>${priceStr}</span>
                        <span class="lot-tag ${statusClass}">${escHtml(lot.status || '—')}</span>
                        <span>${escHtml(lot.city || '—')}${lot.zip ? ', ' + escHtml(lot.zip) : ''}</span>
                    </div>'''
    
    new_meta = '''<div class="lot-meta">
                        <span>${acresStr}</span>
                        <span>${priceStr}</span>
                        <span class="lot-tag ${statusClass}">${escHtml(lot.status || '—')}</span>
                        <span>${escHtml(lot.city || '—')}${lot.zip ? ', ' + escHtml(lot.zip) : ''}</span>
                        ${lot.offerTarget ? `<span style="color:var(--gold); font-weight:600;">Offer: $${Number(lot.offerTarget).toLocaleString()}</span>` : ''}
                        ${lot.dealGrade ? `<span class="lot-tag" style="background:${lot.dealGrade === 'A' ? '#34C759' : lot.dealGrade === 'B' ? '#FF9F0A' : '#FF3B30'}; color:#fff;">${lot.dealGrade}</span>` : ''}
                    </div>'''
    
    html = html.replace(old_meta, new_meta)
    
    # 3. Add links section after notes
    old_links = '''<div style="font-size:10px; color:var(--text-tertiary); margin-top:4px; display:flex; gap:12px;">
                                                    <span>Source: ${escHtml(lot.source || '—')}</span>
                                                    <span>${escHtml(lot.date || '—')}</span>
                                                </div>'''
    
    new_links = '''<div style="margin-top:8px; display:flex; flex-wrap:wrap; gap:8px;">
                        ${lot.zillowUrl ? `<a href="${escHtml(lot.zillowUrl)}" target="_blank" style="font-size:11px; color:#006AFF; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> Zillow</a>` : ''}
                        ${lot.mapUrl ? `<a href="${escHtml(lot.mapUrl)}" target="_blank" style="font-size:11px; color:#34A853; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg> Maps</a>` : ''}
                        ${lot.femaFloodUrl ? `<a href="${escHtml(lot.femaFloodUrl)}" target="_blank" style="font-size:11px; color:#0066CC; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg> Flood</a>` : ''}
                        ${lot.countyLinks && lot.countyLinks.county_appraiser ? `<a href="${escHtml(lot.countyLinks.county_appraiser)}" target="_blank" style="font-size:11px; color:#666; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg> County</a>` : ''}
                    </div>
                    <div style="font-size:10px; color:var(--text-tertiary); margin-top:4px; display:flex; gap:12px;">
                        <span>Source: ${escHtml(lot.source || '—')}</span>
                        <span>${escHtml(lot.date || '—')}</span>
                        ${lot.compCount ? `<span>${lot.compCount} comps</span>` : ''}
                    </div>'''
    
    html = html.replace(old_links, new_links)
    
    # 4. Add comp metrics display if available
    old_notes = '''<div class="lot-notes">${lot.notes ? escHtml(lot.notes) : '<span class="detail-empty">No notes</span>'}</div>'''
    
    new_notes = '''<div class="lot-notes">${lot.notes ? escHtml(lot.notes) : '<span class="detail-empty">No notes</span>'}</div>
                    ${lot.medianPricePerAcre ? `<div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">Market: $${Number(lot.medianPricePerAcre).toLocaleString()}/acre · Est. Value: $${Number(lot.marketValue || 0).toLocaleString()}</div>` : ''}'''
    
    html = html.replace(old_notes, new_notes)
    
    return html


def main():
    parser = argparse.ArgumentParser(description='Update dashboard HTML with enriched data')
    parser.add_argument('--lots', '-l', required=True, help='Input JSON lots file')
    parser.add_argument('--html', required=True, help='Input HTML file')
    parser.add_argument('--output', '-o', required=True, help='Output HTML file')
    args = parser.parse_args()
    
    # Load lots
    with open(args.lots, 'r', encoding='utf-8') as f:
        lots = json.load(f)
    
    print(f"[→] Loaded {len(lots)} lots from {args.lots}")
    
    # Load HTML
    with open(args.html, 'r', encoding='utf-8') as f:
        html = f.read()
    
    print(f"[→] Loaded HTML ({len(html):,} chars)")
    
    # Update
    updated_html = update_html(html, lots)
    
    # Save
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(updated_html)
    
    print(f"[✓] Updated dashboard saved to {args.output}")
    print(f"    Size: {len(updated_html):,} chars")
    
    # Summary
    with_offers = sum(1 for l in lots if 'suggested_offer' in l)
    with_links = sum(1 for l in lots if l.get('zillowUrl') or l.get('mapUrl'))
    a_grades = sum(1 for l in lots if l.get('deal_score', {}).get('grade') == 'A')
    
    print(f"\nSUMMARY:")
    print(f"  Total lots: {len(lots)}")
    print(f"  With offers: {with_offers}")
    print(f"  With links: {with_links}")
    print(f"  A-grade deals: {a_grades}")


if __name__ == '__main__':
    main()
