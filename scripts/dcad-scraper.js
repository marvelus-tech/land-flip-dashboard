#!/usr/bin/env node
/**
 * DCAD Scraper v4 - Dallas County Central Appraisal District
 * Uses Puppeteer for browser automation
 * 
 * Target buyer box:
 *   - ZIPs: 75230, 75229, 75220, 75218, 75214, 75206, 75225, 75212
 *   - Lot size: 8,000+ sq ft
 *   - Built: before 1980
 *   - Improvement value < 20% of land value (teardown indicator)
 *   - Budget: $350K-$450K land value
 * 
 * Usage:
 *   node dcad-scraper.js --street "Preston" --zip 75230 --output leads.csv
 *   node dcad-scraper.js --auto-streets --zip 75230 --output leads.csv
 *   node dcad-scraper.js --batch addresses.txt --output leads.csv
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ──────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────
const DCAD_BASE = 'https://www.dallascad.org';
const DCAD_SEARCH_ADDR = `${DCAD_BASE}/SearchAddr.aspx`;

const TARGET_ZIPS = ['75230', '75229', '75220', '75218', '75214', '75206', '75225', '75212'];
const MIN_LOT_SIZE = 8000;
const MAX_YEAR_BUILT = 1980;
const MAX_IMPROVEMENT_RATIO = 0.20;
const BUDGET_MIN = 350000;
const BUDGET_MAX = 450000;

const DALLAS_STREETS = [
  'Preston', 'Royal', 'Lovers', 'Mockingbird', 'Skillman', 'Abrams',
  'Garland', 'Ross', 'Fitzhugh', 'Peak', 'McKinney', 'Knox', 'Henderson',
  'Greenville', 'Bishop', 'Travis', 'Live Oak', 'Harwood', 'Cole',
  'Reunion', 'Lemmon', 'Inwood', 'Northwest', 'Munger', 'Sylvan',
  'Fort Worth', 'Davis', 'Jefferson', 'Cadiz', 'Colorado', 'Beckley',
  'Polk', 'Clinton', 'Edgefield', 'Montclair', 'Kessler', 'Stevens',
  'Hampton', 'Westmoreland', 'Pioneer', 'Commerce', 'Pacific', 'Jackson',
  'Young', 'Record', 'Akard', 'Ervay', 'Field', 'Howell', 'Julius',
  'Oak', 'Maple', 'Elm', 'Pine', 'Cedar', 'Birch', 'Willow', 'Magnolia',
  'Peachtree', 'Dogwood', 'Hickory', 'Ash', 'Cherry', 'Walnut', 'Chestnut',
  'Main', 'Broadway', 'Park', 'Lake', 'Forest', 'Highland', 'Meadow',
  'Ridge', 'Valley', 'Hill', 'Grove', 'Court', 'Place', 'Circle',
  'Drive', 'Lane', 'Road', 'Street', 'Avenue', 'Boulevard', 'Way',
  'Trail', 'Path', 'Terrace', 'Heights', 'View', 'Crest', 'Gardens',
  'Knoll', 'Point', 'Shores', 'Springs', 'Glen', 'Woods', 'Fields',
  'Hollow', 'Run', 'Creek', 'Brook', 'Bridge', 'Crossing', 'Landing',
  'Parkway', 'Expressway', 'Freeway', 'Highway', 'Turnpike', 'Tollway',
];

// ──────────────────────────────────────────────
// Logger
// ──────────────────────────────────────────────
const logger = {
  info: (msg) => console.log(`${new Date().toISOString()} | INFO | ${msg}`),
  warn: (msg) => console.log(`${new Date().toISOString()} | WARN | ${msg}`),
  error: (msg) => console.error(`${new Date().toISOString()} | ERROR | ${msg}`),
  debug: (msg) => process.env.DEBUG && console.log(`${new Date().toISOString()} | DEBUG | ${msg}`),
};

// ──────────────────────────────────────────────
// Scraper
// ──────────────────────────────────────────────
class DCADScraper {
  constructor(options = {}) {
    this.headless = options.headless !== false;
    this.delay = options.delay || 2000;
    this.results = [];
    this.seenAccounts = new Set();
    this.browser = null;
    this.page = null;
  }

  async init() {
    this.browser = await chromium.launch({
      headless: this.headless,
    });
    this.page = await this.browser.newPage();
    await this.page.setViewportSize({ width: 1920, height: 1080 });
  }

  async sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms + Math.random() * 1000));
  }

  async searchByAddress(streetName, zipCode = null, addressNum = null, maxResults = 20) {
    const query = `${streetName} ${zipCode || ''}`.trim();
    logger.info(`Searching: ${query}`);

    try {
      await this.page.goto(DCAD_SEARCH_ADDR, { waitUntil: 'networkidle' });
      await this.sleep(500);

      // Fill form
      await this.page.fill('#txtStName', streetName);
      await this.sleep(200);

      if (zipCode) {
        await this.page.selectOption('#listCity', 'DALLAS');
        await this.sleep(200);
      }

      if (addressNum) {
        await this.page.fill('#txtAddrNum', addressNum);
        await this.sleep(200);
      }

      // Uncheck COMMERCIAL and BPP
      await this.page.uncheck('#AcctTypeCheckList1_chkAcctType_1');
      await this.sleep(100);
      await this.page.uncheck('#AcctTypeCheckList1_chkAcctType_2');
      await this.sleep(100);

      // Submit and wait for navigation
      await Promise.all([
        this.page.click('#cmdSubmit'),
        this.page.waitForLoadState('networkidle'),
      ]);
      await this.sleep(1500);

      return await this.parseSearchResults(query, maxResults);
    } catch (err) {
      logger.error(`Search failed for ${query}: ${err.message}`);
      return [];
    }
  }

  async parseSearchResults(query, maxResults = 20) {
    const hasResults = await this.page.$('table[id*="dgResults"]');
    if (!hasResults) {
      logger.info(`No results for: ${query}`);
      return [];
    }

    const tooMany = await this.page.evaluate(() => 
      document.body.innerText.includes('Maximum number of records returned')
    );
    if (tooMany) {
      logger.warn(`Too many results for: ${query} — limiting to first page`);
    }

    // Collect links first
    const links = await this.page.evaluate(() => {
      const rows = document.querySelectorAll('table[id*="dgResults"] tr');
      const results = [];
      for (let i = 2; i < rows.length && i < 22; i++) {
        const link = rows[i].querySelector('a[href*="AcctDetail"]');
        if (!link) continue;
        const href = link.getAttribute('href') || '';
        if (href.includes('AcctDetailBPP')) continue;
        
        const match = href.match(/ID=([0-9A-Za-z]+)/);
        if (!match) continue;
        
        const cells = rows[i].querySelectorAll('td');
        const typeText = cells[5] ? cells[5].innerText.trim() : '';
        results.push({ accountNum: match[1], href, typeText });
      }
      return results;
    });

    logger.info(`Found ${links.length} valid property links`);

    const properties = [];
    for (const { accountNum, href, typeText } of links) {
      if (this.seenAccounts.has(accountNum)) continue;
      this.seenAccounts.add(accountNum);

      const detailUrl = href.startsWith('http') ? href : `${DCAD_BASE}/${href}`;
      const prop = await this.parseDetailPage(detailUrl, accountNum, query, typeText);
      if (prop) {
        properties.push(prop);
      }
      await this.sleep(800);
    }

    return properties;
  }

  async parseDetailPage(url, accountNum, query, propType) {
    try {
      await this.page.goto(url, { waitUntil: 'networkidle' });
      await this.sleep(1000);

      const text = await this.page.evaluate(() => document.body.innerText);

      const prop = {
        account_number: accountNum,
        dcad_url: url,
        property_type: propType,
        scraped_at: new Date().toISOString(),
        property_address: '',
        zip_code: '',
        owner_name: '',
        mailing_address: '',
        mailing_city: '',
        mailing_state: '',
        mailing_zip: '',
        is_absentee_owner: false,
        lot_size_sqft: 0,
        year_built: 0,
        land_value: 0,
        improvement_value: 0,
        total_value: 0,
        improvement_ratio: 0,
        tax_status: '',
        is_tax_delinquent: false,
        legal_description: '',
        neighborhood: '',
        score: 'C',
        score_reasons: [],
        search_zip: '',
        search_street: '',
        land_value_estimate: 0,
        potential_profit: 0,
        meets_budget: false,
      };

      // Parse query
      const parts = query.split(' ');
      if (parts.length > 1 && /^\d{5}$/.test(parts[parts.length - 1])) {
        prop.search_zip = parts.pop();
        prop.search_street = parts.join(' ');
      } else {
        prop.search_street = query;
      }

      // Extract fields
      const addrMatch = text.match(/Address:\s*([^\n]+)/);
      if (addrMatch) prop.property_address = addrMatch[1].trim();

      const zipMatch = prop.property_address.match(/(\d{5}(?:-\d{4})?)/);
      if (zipMatch) prop.zip_code = zipMatch[1].substring(0, 5);

      const ownerMatch = text.match(/Owner \(Current \d{4}\)\s*\n\s*([^\n]+)/);
      if (ownerMatch) prop.owner_name = ownerMatch[1].trim();

      const mailMatch = text.match(/Owner \(Current \d{4}\)[\s\S]*?\n\s*([^\n,]+(?:,\s*[^\n]+)?)\n\s*([^\n,]+),\s*(\w{2})\s*(\d{5}(?:-\d{4})?)/);
      if (mailMatch) {
        prop.mailing_address = mailMatch[1].trim();
        prop.mailing_city = mailMatch[2].trim();
        prop.mailing_state = mailMatch[3].trim();
        prop.mailing_zip = mailMatch[4].trim();
      }

      const legalMatch = text.match(/Legal Desc \(Current \d{4}\)([\s\S]*?)(?:Deed Transfer Date:|Value)/);
      if (legalMatch) {
        const legalLines = legalMatch[1].match(/\d+:\s*([^\n]+)/g);
        if (legalLines) {
          prop.legal_description = legalLines.map(l => l.replace(/^\d+:\s*/, '')).join('; ');
        }
      }

      const valueMatch = text.match(/Improvement:\s*Land:\s*Market Value:\s*\$?([\d,]+)\s*\+\s*\$?([\d,]+)\s*=\s*\$?([\d,]+)/);
      if (valueMatch) {
        prop.improvement_value = parseInt(valueMatch[1].replace(/,/g, ''));
        prop.land_value = parseInt(valueMatch[2].replace(/,/g, ''));
        prop.total_value = parseInt(valueMatch[3].replace(/,/g, ''));
      } else {
        const landMatch = text.match(/Land\s*[:\$]*\s*\$?([\d,]+)/);
        if (landMatch) prop.land_value = parseInt(landMatch[1].replace(/,/g, ''));
        const impMatch = text.match(/Improvement\s*[:\$]*\s*\$?([\d,]+)/);
        if (impMatch) prop.improvement_value = parseInt(impMatch[1].replace(/,/g, ''));
        const totalMatch = text.match(/Total\s*[:\$]*\s*\$?([\d,]+)/);
        if (totalMatch) prop.total_value = parseInt(totalMatch[1].replace(/,/g, ''));
      }

      const yearMatch = text.match(/Year\s*Built[:\s]*(\d{4})/i);
      if (yearMatch) prop.year_built = parseInt(yearMatch[1]);
      
      // Fallback: look for year in improvement section
      if (prop.year_built === 0) {
        const yrBltMatch = text.match(/Yr\s*Blt[:\s]*(\d{4})/i);
        if (yrBltMatch) prop.year_built = parseInt(yrBltMatch[1]);
      }
      
      // Another fallback: look for 4-digit year near "Built" or "Construction"
      if (prop.year_built === 0) {
        const builtMatch = text.match(/(?:Built|Construction|Constructed)[:\s]*(\d{4})/i);
        if (builtMatch) prop.year_built = parseInt(builtMatch[1]);
      }

      const lotMatch = text.match(/(\d[\d,]*\.?\d*)\s*(?:acres?|ac)\b/i);
      if (lotMatch) {
        prop.lot_size_sqft = Math.round(parseFloat(lotMatch[1].replace(/,/g, '')) * 43560);
      } else {
        const sqftMatch = text.match(/(\d[\d,]*)\s*(?:sq\.?\s*ft\.?|sf|square feet)/i);
        if (sqftMatch) prop.lot_size_sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
      }

      // Skip condos/IMP_ONLY (no land value)
      if (prop.legal_description.includes('IMP ONLY')) {
        logger.debug(`Skipping IMP_ONLY property: ${prop.property_address}`);
        return null;
      }

      // Calculate metrics
      if (prop.land_value > 0) {
        prop.improvement_ratio = prop.improvement_value / prop.land_value;
      }
      prop.meets_budget = BUDGET_MIN <= prop.land_value && prop.land_value <= BUDGET_MAX;
      if (prop.land_value > 0) {
        prop.land_value_estimate = Math.round(prop.total_value * 0.85);
        prop.potential_profit = prop.land_value_estimate - prop.land_value;
      }

      // Absentee owner
      if (prop.mailing_address && prop.property_address) {
        const streetNum = prop.property_address.match(/^(\d+)/);
        if (streetNum && !prop.mailing_address.includes(streetNum[1])) {
          prop.is_absentee_owner = true;
        } else if (prop.zip_code && prop.mailing_zip && prop.zip_code !== prop.mailing_zip.substring(0, 5)) {
          prop.is_absentee_owner = true;
        }
      }

      // Score
      const result = this.scoreProperty(prop);
      prop.score = result.score;
      prop.score_reasons = result.reasons;

      logger.info(
        `Parsed: ${prop.property_address || accountNum} | ` +
        `Owner: ${prop.owner_name ? prop.owner_name.substring(0, 30) : 'N/A'} | ` +
        `Lot: ${prop.lot_size_sqft.toLocaleString()} | Year: ${prop.year_built} | ` +
        `Land: $${prop.land_value.toLocaleString()} | Score: ${prop.score}`
      );
      return prop;
    } catch (err) {
      logger.error(`Error parsing detail page ${url}: ${err.message}`);
      return null;
    }
  }

  scoreProperty(prop) {
    const reasons = [];
    let score = 'C';

    const fitsLot = prop.lot_size_sqft >= MIN_LOT_SIZE;
    const fitsYear = prop.year_built > 0 && prop.year_built <= MAX_YEAR_BUILT;
    const fitsRatio = prop.improvement_ratio <= MAX_IMPROVEMENT_RATIO || prop.improvement_value === 0;
    const inTargetZip = TARGET_ZIPS.includes(prop.zip_code);
    const fitsBudget = prop.meets_budget;

    if (fitsLot) reasons.push(`Lot ${prop.lot_size_sqft.toLocaleString()} sq ft`);
    if (fitsYear) reasons.push(`Built ${prop.year_built}`);
    if (fitsRatio) reasons.push(`Imp ratio ${Math.round(prop.improvement_ratio * 100)}%`);
    if (inTargetZip) reasons.push(`ZIP ${prop.zip_code}`);
    if (fitsBudget) reasons.push(`Land $${prop.land_value.toLocaleString()} (in budget)`);

    if (prop.is_tax_delinquent) {
      reasons.push('Tax delinquent');
      score = 'A';
    } else if (prop.is_absentee_owner) {
      score = 'B';
      reasons.push('Absentee owner');
    } else if (fitsLot && fitsYear && fitsRatio && inTargetZip) {
      score = 'B';
      reasons.push('Buyer box fit');
    }

    return { score, reasons };
  }

  async searchZipAuto(zipCode, maxStreets = 20) {
    logger.info(`Starting auto-search for ZIP ${zipCode}`);
    const allProps = [];
    const streets = DALLAS_STREETS.slice(0, maxStreets);

    for (const street of streets) {
      const props = await this.searchByAddress(street, zipCode, null, 15);
      allProps.push(...props);
      logger.info(`  ${street}: ${props.length} props (total: ${allProps.length})`);
      if (allProps.length >= 200) break;
    }
    return allProps;
  }

  async searchBatch(filepath) {
    const props = [];
    const lines = fs.readFileSync(filepath, 'utf8').split('\n');
    for (const line of lines) {
      const addr = line.trim();
      if (!addr || addr.startsWith('#')) continue;
      
      // Parse street and ZIP from line like "Greenville 75206"
      const parts = addr.split(' ');
      let zipCode = null;
      let streetName = addr;
      
      if (parts.length > 1 && /^\d{5}$/.test(parts[parts.length - 1])) {
        zipCode = parts.pop();
        streetName = parts.join(' ');
      }
      
      const results = await this.searchByAddress(streetName, zipCode, null, 10);
      props.push(...results);
      logger.info(`Batch: ${addr} -> ${results.length} results`);
    }
    return props;
  }

  exportCsv(filepath) {
    if (this.results.length === 0) {
      logger.warn('No results to export');
      return;
    }

    const columns = [
      'account_number', 'property_address', 'zip_code',
      'owner_name', 'mailing_address', 'mailing_city',
      'mailing_state', 'mailing_zip', 'is_absentee_owner',
      'lot_size_sqft', 'year_built', 'land_value',
      'improvement_value', 'total_value', 'improvement_ratio',
      'tax_status', 'is_tax_delinquent', 'property_type',
      'legal_description', 'neighborhood',
      'score', 'score_reasons',
      'land_value_estimate', 'potential_profit', 'meets_budget',
      'search_zip', 'search_street', 'scraped_at', 'dcad_url',
    ];

    const header = columns.join(',');
    const rows = this.results.map(p => {
      const values = columns.map(col => {
        let val = p[col];
        if (Array.isArray(val)) val = val.join('; ');
        if (val === null || val === undefined) val = '';
        if (typeof val === 'string' && (val.includes(',') || val.includes('"') || val.includes('\n'))) {
          val = '"' + val.replace(/"/g, '""') + '"';
        }
        return val;
      });
      return values.join(',');
    });

    const csv = [header, ...rows].join('\n');
    fs.mkdirSync(path.dirname(filepath), { recursive: true });
    fs.writeFileSync(filepath, csv);
    logger.info(`Exported ${this.results.length} properties to ${filepath}`);
  }

  exportJson(filepath) {
    fs.mkdirSync(path.dirname(filepath), { recursive: true });
    fs.writeFileSync(filepath, JSON.stringify(this.results, null, 2));
    logger.info(`Exported ${this.results.length} properties to ${filepath}`);
  }

  exportDashboardJson(filepath) {
    const data = {
      generated_at: new Date().toISOString(),
      total_leads: this.results.length,
      score_breakdown: {
        A: this.results.filter(p => p.score === 'A').length,
        B: this.results.filter(p => p.score === 'B').length,
        C: this.results.filter(p => p.score === 'C').length,
      },
      by_zip: {},
      properties: this.results.map(p => ({
        ...p,
        score_reasons: Array.isArray(p.score_reasons) ? p.score_reasons.join('; ') : p.score_reasons,
      })),
    };

    for (const prop of this.results) {
      const z = prop.zip_code || 'unknown';
      data.by_zip[z] = (data.by_zip[z] || 0) + 1;
    }

    fs.mkdirSync(path.dirname(filepath), { recursive: true });
    fs.writeFileSync(filepath, JSON.stringify(data, null, 2));
    logger.info(`Exported dashboard data to ${filepath}`);
  }

  async close() {
    if (this.browser) {
      await this.browser.close();
    }
  }
}

// ──────────────────────────────────────────────
// CLI
// ──────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  const options = {
    zip: TARGET_ZIPS,
    street: null,
    autoStreets: false,
    batch: null,
    output: 'dcad-leads.csv',
    json: null,
    dashboard: null,
    maxStreets: 20,
    delay: 2000,
    headless: true,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    switch (arg) {
      case '--zip':
        options.zip = [];
        i++;
        while (i < args.length && !args[i].startsWith('--')) {
          options.zip.push(args[i++]);
        }
        i--;
        break;
      case '--street':
        options.street = args[++i];
        break;
      case '--auto-streets':
        options.autoStreets = true;
        break;
      case '--batch':
        options.batch = args[++i];
        break;
      case '--output':
      case '-o':
        options.output = args[++i];
        break;
      case '--json':
        options.json = args[++i];
        break;
      case '--dashboard':
        options.dashboard = args[++i];
        break;
      case '--max-streets':
        options.maxStreets = parseInt(args[++i]);
        break;
      case '--delay':
        options.delay = parseInt(args[++i]);
        break;
      case '--no-headless':
        options.headless = false;
        break;
    }
  }

  const scraper = new DCADScraper({ headless: options.headless, delay: options.delay });
  await scraper.init();

  try {
    if (options.batch) {
      const props = await scraper.searchBatch(options.batch);
      scraper.results.push(...props);
    } else if (options.autoStreets) {
      for (const zipCode of options.zip) {
        logger.info(`Auto-streets mode for ZIP ${zipCode}`);
        const props = await scraper.searchZipAuto(zipCode, options.maxStreets);
        scraper.results.push(...props);
      }
    } else if (options.street) {
      for (const zipCode of options.zip) {
        const props = await scraper.searchByAddress(options.street, zipCode);
        scraper.results.push(...props);
      }
    } else {
      console.log(`
DCAD Scraper v4 — Dallas County Central Appraisal District

Usage:
  node dcad-scraper.js --street "Preston" --zip 75230 --output leads.csv
  node dcad-scraper.js --auto-streets --zip 75230 --output leads.csv
  node dcad-scraper.js --batch addresses.txt --output leads.csv
  node dcad-scraper.js --auto-streets --zip 75230 75229 --dashboard data/dcad-leads.json

Options:
  --street <name>       Street name to search
  --zip <zip> ...       Target ZIP codes (default: all 8)
  --auto-streets        Auto-search common street names
  --batch <file>        File with one address per line
  --output, -o <file>   Output CSV filename (default: dcad-leads.csv)
  --json <file>         Also export to JSON
  --dashboard <file>    Export dashboard-compatible JSON
  --max-streets <n>     Max streets in auto mode (default: 20)
  --delay <ms>          Delay between requests (default: 2000)
  --no-headless         Show browser window (for debugging)
      `);
      process.exit(1);
    }

    if (scraper.results.length > 0) {
      scraper.exportCsv(options.output);
      if (options.json) scraper.exportJson(options.json);
      if (options.dashboard) scraper.exportDashboardJson(options.dashboard);

      const total = scraper.results.length;
      const scoreA = scraper.results.filter(p => p.score === 'A').length;
      const scoreB = scraper.results.filter(p => p.score === 'B').length;
      const scoreC = scraper.results.filter(p => p.score === 'C').length;
      const absentee = scraper.results.filter(p => p.is_absentee_owner).length;
      const inBudget = scraper.results.filter(p => p.meets_budget).length;

      logger.info('='.repeat(60));
      logger.info('SCRAPING COMPLETE');
      logger.info(`Total properties:    ${total}`);
      logger.info(`  Score A (HOT):     ${scoreA}`);
      logger.info(`  Score B (WARM):    ${scoreB}`);
      logger.info(`  Score C (COLD):    ${scoreC}`);
      logger.info(`  Absentee owners:   ${absentee}`);
      logger.info(`  In budget range:   ${inBudget}`);
      logger.info(`Output CSV: ${options.output}`);
      if (options.dashboard) logger.info(`Dashboard JSON: ${options.dashboard}`);
      logger.info('='.repeat(60));
    } else {
      logger.warn('No properties found');
    }
  } catch (err) {
    logger.error(`Fatal error: ${err.message}`);
  } finally {
    await scraper.close();
  }
}

main().catch(err => {
  logger.error(`Unhandled error: ${err.message}`);
  process.exit(1);
});
