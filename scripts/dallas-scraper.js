#!/usr/bin/env node
/**
 * Dallas Land Acquisition Tracker
 * Scrape and track vacant land in target ZIPs
 */

const fs = require('fs');
const path = require('path');

const TARGET_ZIPS = ['75230', '75229', '75220', '75218', '75214', '75206', '75225', '75212'];
const MIN_LOT_SIZE = 8000; // sq ft
const BUDGET_MIN = 350000;
const BUDGET_MAX = 450000;

// DCAD search URLs
const DCAD_URLS = {
  byAddress: 'https://www.dallascad.org/searchaddr.aspx',
  byOwner: 'https://www.dallascad.org/searchowner.aspx',
  gisMap: 'https://maps.dcad.org/prd/dpm'
};

// Listing sites to monitor
const LISTING_SITES = [
  { name: 'Redfin', url: 'https://www.redfin.com/city/30794/TX/Dallas/land' },
  { name: 'Zillow', url: 'https://www.zillow.com/dallas-tx/land_type/' },
  { name: 'Trulia', url: 'https://www.trulia.com/for_sale/Dallas,TX/LOT%7CLAND_type/' },
  { name: 'LandSearch', url: 'https://www.landsearch.com/properties' }
];

function generateSearchUrls() {
  console.log('=== Dallas Land Flip - Search URLs ===\n');
  
  console.log('DCAD Public Records:');
  console.log(`  Address Search: ${DCAD_URLS.byAddress}`);
  console.log(`  Owner Search: ${DCAD_URLS.byOwner}`);
  console.log(`  GIS Map: ${DCAD_URLS.gisMap}\n`);
  
  console.log('Target ZIP Codes:');
  TARGET_ZIPS.forEach(zip => {
    console.log(`  ${zip}`);
  });
  
  console.log('\nListing Sites:');
  LISTING_SITES.forEach(site => {
    console.log(`  ${site.name}: ${site.url}`);
  });
  
  console.log('\n=== Search Strategy ===');
  console.log('1. Search DCAD by each ZIP for vacant residential lots');
  console.log('2. Filter by lot size >= 8000 sq ft');
  console.log('3. Check if land value fits $350K-$450K range');
  console.log('4. Verify utilities and flood zone status');
  console.log('5. Skip trace owners for off-market properties');
}

function createPropertyTracker() {
  const tracker = {
    dateCreated: new Date().toISOString(),
    properties: [],
    stats: {
      totalFound: 0,
      byZip: {},
      bySource: {}
    }
  };
  
  TARGET_ZIPS.forEach(zip => {
    tracker.stats.byZip[zip] = 0;
  });
  
  return tracker;
}

function addProperty(tracker, property) {
  tracker.properties.push({
    ...property,
    id: Date.now() + Math.random().toString(36).substr(2, 9),
    dateAdded: new Date().toISOString(),
    status: 'new', // new, contacted, offer_made, under_contract, closed
    notes: ''
  });
  
  tracker.stats.totalFound++;
  tracker.stats.byZip[property.zip] = (tracker.stats.byZip[property.zip] || 0) + 1;
  tracker.stats.bySource[property.source] = (tracker.stats.bySource[property.source] || 0) + 1;
}

function saveTracker(tracker, filename = 'dallas-tracker.json') {
  const filepath = path.join(__dirname, '..', 'data', filename);
  fs.writeFileSync(filepath, JSON.stringify(tracker, null, 2));
  console.log(`Tracker saved to: ${filepath}`);
}

function loadTracker(filename = 'dallas-tracker.json') {
  const filepath = path.join(__dirname, '..', 'data', filename);
  if (fs.existsSync(filepath)) {
    return JSON.parse(fs.readFileSync(filepath, 'utf8'));
  }
  return createPropertyTracker();
}

// Main execution
if (require.main === module) {
  const command = process.argv[2];
  
  switch (command) {
    case 'urls':
      generateSearchUrls();
      break;
    case 'init':
      const tracker = createPropertyTracker();
      saveTracker(tracker);
      console.log('New tracker initialized');
      break;
    case 'add':
      // Example: node dallas-scraper.js add "123 Main St" "75230" 10000 400000 "Redfin"
      const [address, zip, lotSize, price, source] = process.argv.slice(3);
      if (!address || !zip) {
        console.log('Usage: node dallas-scraper.js add "ADDRESS" "ZIP" LOT_SIZE PRICE SOURCE');
        process.exit(1);
      }
      const existing = loadTracker();
      addProperty(existing, {
        address,
        zip,
        lotSize: parseInt(lotSize) || 0,
        price: parseInt(price) || 0,
        source: source || 'manual'
      });
      saveTracker(existing);
      console.log(`Added: ${address}`);
      break;
    default:
      console.log('Dallas Land Acquisition Tracker');
      console.log('Commands:');
      console.log('  urls  - Show search URLs and strategy');
      console.log('  init  - Create new tracker');
      console.log('  add   - Add a property');
  }
}

module.exports = { createPropertyTracker, addProperty, saveTracker, loadTracker };
