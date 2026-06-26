# DCAD Scraper v4

Dallas County Central Appraisal District scraper for land flip lead generation.

## What It Does

Automates property lookups on DCAD to find pre-1980 teardown candidates:
- Targets 8 Dallas ZIPs: 75230, 75229, 75220, 75218, 75214, 75206, 75225, 75212
- Filters for residential properties with 8,000+ sq ft lots
- Scores leads A/B/C based on buyer box fit
- Exports CSV + dashboard-compatible JSON

## Prerequisites

```bash
# Playwright must be installed
npx playwright install chromium
```

## Usage

### Search a specific street
```bash
node scripts/dcad-scraper.js --street "Greenville" --zip 75206 --output data/leads.csv
```

### Auto-search common streets in a ZIP
```bash
node scripts/dcad-scraper.js --auto-streets --zip 75214 --output data/leads.csv
```

### Multiple ZIPs with dashboard export
```bash
node scripts/dcad-scraper.js --auto-streets --zip 75206 75214 75218 --dashboard data/dcad-leads.json
```

### Batch process addresses from file
```bash
node scripts/dcad-scraper.js --batch data/addresses.txt --output data/leads.csv
```

### Debug mode (visible browser)
```bash
node scripts/dcad-scraper.js --street "Lovers" --zip 75225 --no-headless --output data/leads.csv
```

## Output Format

### CSV Columns
- `account_number` — DCAD account ID
- `property_address` — Full street address
- `zip_code` — Property ZIP
- `owner_name` — Property owner
- `mailing_address` — Owner's mailing address
- `lot_size_sqft` — Total square footage
- `year_built` — Year built
- `land_value` — Appraised land value
- `improvement_value` — Appraised building value
- `total_value` — Total appraised value
- `improvement_ratio` — Building value / Land value
- `is_absentee_owner` — Mailing address ≠ property address
- `score` — A (HOT), B (WARM), C (COLD)
- `score_reasons` — Why it scored this way
- `meets_budget` — Land value in $350K-$450K range

### Scoring
- **A (HOT)** — Tax delinquent + absentee owner
- **B (WARM)** — Absentee owner OR matches buyer box (lot ≥8K, built ≤1980, in target ZIP)
- **C (COLD)** — Local owner, doesn't fully match criteria

## Tips

1. **Search residential side streets, not major arterials**
   - Good: "Greenville", "Skillman", "Abrams" (residential sections)
   - Bad: "Preston", "Northwest" (mostly commercial)

2. **Add address numbers to narrow results**
   ```bash
   node scripts/dcad-scraper.js --street "Greenville" --zip 75206 --output data/leads.csv
   ```

3. **Start with one ZIP, expand after validating**
   - 75206 (Lower Greenville) and 75214 (Lakewood) have good teardown inventory
   - 75230 (Preston Hollow) is very expensive, mostly newer builds

4. **Check legal_description column for "IMP ONLY"**
   - These are condos/townhomes without individual land ownership
   - The scraper auto-skips these

## Files

- `scripts/dcad-scraper.js` — Main scraper (Node.js + Playwright)
- `data/dcad-leads.json` — Dashboard-compatible export
- `data/*.csv` — Raw lead exports
