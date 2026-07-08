#!/usr/bin/env python3
"""
SpaceX-grade Land Lot Entity Auditor
Removes corporate, trust, LLC, estate, and institutional owners.
Flags individual sellers with sophistication scoring.

Usage:
    python3 entity_auditor.py --input lots.json --output clean_lots.json
    python3 entity_auditor.py --csv large-lot-leads.csv --output clean_leads.csv
"""

import json
import csv
import re
import argparse
from pathlib import Path
from datetime import datetime

# ─── ENTITY CLASSIFICATION PATTERNS ───

CORPORATE_PATTERNS = [
    r'\bLLC\b', r'\bL\.L\.C\.\b', r'\bINC\.?\b', r'\bCORP\.?\b',
    r'\bCORPORATION\b', r'\bLTD\.?\b', r'\bLIMITED\b', r'\bLP\b',
    r'\bL\.P\.\b', r'\bLLP\b', r'\bPARTNERSHIP\b', r'\bHOLDINGS?\b',
    r'\bPROPERTIES?\b', r'\bENTERPRISES?\b', r'\bINVESTMENTS?\b',
    r'\bDEVELOPMENT\b', r'\bBUILDERS?\b', r'\bCONSTRUCTION\b',
    r'\bGROUP\b', r'\bCOMPANY\b', r'\bCO\.\b', r'\bASSOCIATES?\b',
    r'\bMANAGEMENT\b', r'\bREALTY\b', r'\bHOMES?\b', r'\bLAND\s+BANK\b',
    r'\bBANK\b', r'\bCREDIT\s+UNION\b', r'\bMORTGAGE\b',
    r'\bFINANCIAL\b', r'\bINSURANCE\b', r'\bTRUST\s*CO\b',
    r'\bTITLE\s*CO\b', r'\bESCROW\b', r'\bHOA\b',
    r'\bHOMEOWNERS?\b', r'\bASSOCIATION\b', r'\bCHURCH\b',
    r'\bMINISTRY\b', r'\bSCHOOL\b', r'\bUNIVERSITY\b', r'\bCOLLEGE\b',
    r'\bCITY\s+OF\b', r'\bCOUNTY\s+OF\b', r'\bSTATE\s+OF\b',
    r'\bFEDERAL\b', r'\bGOVERNMENT\b', r'\bMUNICIPAL\b',
    r'\bAUTHORITY\b', r'\bDISTRICT\b', r'\bUTILITIES?\b',
    r'\bFOUNDATION\b', r'\bNON-?PROFIT\b', r'\bCHARITABLE\b',
    r'\bHOSPITAL\b', r'\bCLINIC\b', r'\bHEALTH\s+SYSTEM\b',
]

TRUST_PATTERNS = [
    r'\bTRUST\b', r'\bREVOCABLE\b', r'\bIRREVOCABLE\b',
    r'\bLIVING\s+TRUST\b', r'\bFAMILY\s+TRUST\b',
    r'\bTESTAMENTARY\b', r'\bQTIP\b', r'\bGRANTOR\s+TRUST\b',
    r'\bBYPASS\s+TRUST\b', r'\bSPECIAL\s+NEEDS\s+TRUST\b',
    r'\bCHARITABLE\s+TRUST\b', r'\bLAND\s+TRUST\b',
    r'\bNOMINEE\s+TRUST\b', r'\bVOTING\s+TRUST\b',
]

ESTATE_PATTERNS = [
    r'\bESTATE\s+OF\b', r'\bEST\s+OF\b', r'\bEST\.\s+OF\b',
    r'\bSUCCESSION\b', r'\bPROBATE\b', r'\bDECEDENT\b',
    r'\bHEIRS?\s+OF\b', r'\bSUCCESSORS?\b', r'\bASSIGNS?\b',
    r'\bADMINISTRATOR\b', r'\bEXECUTOR\b',
    r'\bPERSONAL\s+REP\b', r'\bPR\b',
]

MULTI_OWNER_PATTERNS = [
    r'\bET\s+AL\b', r'\bET\.?\s+AL\.?\b', r'\bAND\s+OTHERS?\b',
]

# Compile
CORP_REGEX = re.compile('|'.join(CORPORATE_PATTERNS), re.IGNORECASE)
TRUST_REGEX = re.compile('|'.join(TRUST_PATTERNS), re.IGNORECASE)
ESTATE_REGEX = re.compile('|'.join(ESTATE_PATTERNS), re.IGNORECASE)
MULTI_REGEX = re.compile('|'.join(MULTI_OWNER_PATTERNS), re.IGNORECASE)


def classify_owner(owner_name: str) -> dict:
    if not owner_name or not isinstance(owner_name, str):
        return {
            'owner_name': owner_name or '',
            'is_corporate': False, 'is_trust': False, 'is_estate': False,
            'is_multi_owner': False, 'entity_type': 'unknown',
            'recommendation': 'review', 'confidence': 'low',
            'flags': ['no_owner_name']
        }
    
    name_upper = owner_name.upper().strip()
    flags = []
    
    is_corp = bool(CORP_REGEX.search(name_upper))
    if is_corp: flags.append('corporate_entity')
    
    is_trust = bool(TRUST_REGEX.search(name_upper))
    if is_trust: flags.append('trust_entity')
    
    is_estate = bool(ESTATE_REGEX.search(name_upper))
    if is_estate: flags.append('estate_probate')
    
    is_multi = bool(MULTI_REGEX.search(name_upper))
    if is_multi: flags.append('multiple_owners')
    
    if is_corp: entity_type = 'corporate'
    elif is_trust: entity_type = 'trust'
    elif is_estate: entity_type = 'estate'
    elif is_multi: entity_type = 'multiple_individuals'
    else: entity_type = 'individual'
    
    if is_corp or is_trust:
        recommendation, confidence = 'remove', 'high'
    elif is_estate:
        recommendation, confidence = 'flag_review', 'high'
    elif is_multi:
        recommendation, confidence = 'review', 'medium'
    else:
        recommendation, confidence = 'keep', 'high'
    
    return {
        'owner_name': owner_name,
        'is_corporate': is_corp, 'is_trust': is_trust,
        'is_estate': is_estate, 'is_multi_owner': is_multi,
        'entity_type': entity_type,
        'recommendation': recommendation,
        'confidence': confidence,
        'flags': flags
    }


def audit_json_lots(lots: list) -> dict:
    results = {
        'audit_timestamp': datetime.now().isoformat(),
        'total_lots': len(lots),
        'clean_lots': [], 'removed_lots': [], 'flagged_lots': [],
        'stats': {'by_entity_type': {}, 'by_recommendation': {},
                  'by_state': {}, 'removed_count': 0,
                  'flagged_count': 0, 'kept_count': 0}
    }
    
    for lot in lots:
        owner_name = lot.get('ownerName', '') or lot.get('ownerNames', '') or lot.get('owners', '')
        classification = classify_owner(owner_name)
        lot['_audit'] = classification
        
        et = classification['entity_type']
        rec = classification['recommendation']
        state = str(lot.get('state', 'unknown')).lower()
        
        results['stats']['by_entity_type'][et] = results['stats']['by_entity_type'].get(et, 0) + 1
        results['stats']['by_recommendation'][rec] = results['stats']['by_recommendation'].get(rec, 0) + 1
        results['stats']['by_state'][state] = results['stats']['by_state'].get(state, 0) + 1
        
        if rec == 'remove':
            results['removed_lots'].append(lot)
            results['stats']['removed_count'] += 1
        elif rec in ('flag_review', 'review'):
            results['flagged_lots'].append(lot)
            results['stats']['flagged_count'] += 1
            results['clean_lots'].append(lot)
        else:
            results['clean_lots'].append(lot)
            results['stats']['kept_count'] += 1
    
    return results


def audit_csv_rows(rows: list) -> dict:
    results = {
        'audit_timestamp': datetime.now().isoformat(),
        'total_rows': len(rows),
        'clean_rows': [], 'removed_rows': [], 'flagged_rows': [],
        'stats': {'by_entity_type': {}, 'by_recommendation': {},
                  'removed_count': 0, 'flagged_count': 0, 'kept_count': 0}
    }
    
    for row in rows:
        owner_name = row.get('owner_name', '')
        classification = classify_owner(owner_name)
        row['_audit'] = classification
        
        et = classification['entity_type']
        rec = classification['recommendation']
        
        results['stats']['by_entity_type'][et] = results['stats']['by_entity_type'].get(et, 0) + 1
        results['stats']['by_recommendation'][rec] = results['stats']['by_recommendation'].get(rec, 0) + 1
        
        if rec == 'remove':
            results['removed_rows'].append(row)
            results['stats']['removed_count'] += 1
        elif rec in ('flag_review', 'review'):
            results['flagged_rows'].append(row)
            results['stats']['flagged_count'] += 1
            results['clean_rows'].append(row)
        else:
            results['clean_rows'].append(row)
            results['stats']['kept_count'] += 1
    
    return results


def generate_report(results: dict, data_type='json') -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("LAND LOT ENTITY AUDIT REPORT")
    lines.append(f"Generated: {results['audit_timestamp']}")
    lines.append("=" * 70)
    lines.append("")
    
    total = results.get('total_lots', results.get('total_rows', 0))
    lines.append(f"TOTAL RECORDS AUDITED: {total}")
    lines.append(f"KEPT (Individual owners):   {results['stats']['kept_count']}")
    lines.append(f"FLAGGED (Review needed):    {results['stats']['flagged_count']}")
    lines.append(f"REMOVED (Corp/Trust):       {results['stats']['removed_count']}")
    lines.append("")
    
    lines.append("-" * 70)
    lines.append("BY ENTITY TYPE:")
    for etype, count in sorted(results['stats']['by_entity_type'].items()):
        pct = count / total * 100 if total else 0
        lines.append(f"  {etype:25s}: {count:3d} ({pct:5.1f}%)")
    lines.append("")
    
    removed = results.get('removed_lots', results.get('removed_rows', []))
    if removed:
        lines.append("-" * 70)
        lines.append("REMOVED RECORDS (Corporate / Trust / Institutional):")
        for item in removed:
            audit = item.get('_audit', {})
            addr = item.get('address', item.get('property_address', 'N/A'))
            owner = audit.get('owner_name', 'N/A')
            flags = ', '.join(audit.get('flags', []))
            lines.append(f"  {addr:45s} | {owner:35s} | {flags}")
        lines.append("")
    
    flagged = results.get('flagged_lots', results.get('flagged_rows', []))
    if flagged:
        lines.append("-" * 70)
        lines.append("FLAGGED RECORDS (Estates / Multi-owner / Review):")
        for item in flagged:
            audit = item.get('_audit', {})
            addr = item.get('address', item.get('property_address', 'N/A'))
            owner = audit.get('owner_name', 'N/A')
            flags = ', '.join(audit.get('flags', []))
            lines.append(f"  {addr:45s} | {owner:35s} | {flags}")
        lines.append("")
    
    lines.append("=" * 70)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Audit land lots for entity types')
    parser.add_argument('--input', '-i', help='Input JSON file')
    parser.add_argument('--csv', '-c', help='Input CSV file')
    parser.add_argument('--output', '-o', default='clean_output.json', help='Output file')
    parser.add_argument('--report', '-r', default='audit_report.txt', help='Output report file')
    parser.add_argument('--keep-flagged', action='store_true', help='Keep flagged records')
    args = parser.parse_args()
    
    if args.csv:
        with open(args.csv, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"[→] Loaded {len(rows)} rows from {args.csv}")
        results = audit_csv_rows(rows)
        
        clean = [r for r in rows if r.get('_audit', {}).get('recommendation') != 'remove']
        if not args.keep_flagged:
            clean = [r for r in clean if r.get('_audit', {}).get('recommendation') == 'keep']
        
        # Strip audit metadata
        for r in clean:
            if '_audit' in r:
                r['owner_entity_type'] = r['_audit'].get('entity_type', 'unknown')
                r['owner_flags'] = '|'.join(r['_audit'].get('flags', []))
                del r['_audit']
        
        with open(args.output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=clean[0].keys() if clean else [])
            writer.writeheader()
            writer.writerows(clean)
        
        print(f"[✓] Clean CSV saved to {args.output} ({len(clean)} rows)")
    
    elif args.input:
        with open(args.input) as f:
            lots = json.load(f)
        
        print(f"[→] Loaded {len(lots)} lots from {args.input}")
        results = audit_json_lots(lots)
        
        clean = [l for l in lots if l.get('_audit', {}).get('recommendation') != 'remove']
        if not args.keep_flagged:
            clean = [l for l in clean if l.get('_audit', {}).get('recommendation') == 'keep']
        
        for lot in clean:
            if '_audit' in lot:
                lot['owner_entity_type'] = lot['_audit'].get('entity_type', 'unknown')
                lot['owner_flags'] = lot['_audit'].get('flags', [])
                del lot['_audit']
        
        with open(args.output, 'w') as f:
            json.dump(clean, f, indent=2)
        
        print(f"[✓] Clean JSON saved to {args.output} ({len(clean)} lots)")
    
    else:
        print("Error: Provide --input (JSON) or --csv (CSV)")
        return
    
    report = generate_report(results, 'csv' if args.csv else 'json')
    with open(args.report, 'w') as f:
        f.write(report)
    
    print(f"[✓] Report saved to {args.report}")
    print(f"")
    print(f"SUMMARY:")
    print(f"  Total:   {results.get('total_lots', results.get('total_rows', 0))}")
    print(f"  Kept:    {results['stats']['kept_count']}")
    print(f"  Flagged: {results['stats']['flagged_count']}")
    print(f"  Removed: {results['stats']['removed_count']}")


if __name__ == '__main__':
    main()
