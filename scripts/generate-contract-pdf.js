#!/usr/bin/env node
/**
 * Generate contract PDFs from HTML sources (Puppeteer / headless Chrome).
 * Usage: node scripts/generate-contract-pdf.js [html-path] [pdf-path]
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const root = path.resolve(__dirname, '..');
const htmlPath = path.resolve(root, process.argv[2] || 'docs/contracts/vacant-land-contract-page-01.html');
const pdfPath = path.resolve(root, process.argv[3] || 'docs/contracts/vacant-land-contract-page-01.pdf');

async function main() {
  if (!fs.existsSync(htmlPath)) {
    console.error('HTML not found:', htmlPath);
    process.exit(1);
  }

  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle0' });
  await page.pdf({
    path: pdfPath,
    format: 'Letter',
    printBackground: true,
    margin: { top: '0.45in', right: '0.55in', bottom: '0.5in', left: '0.55in' },
  });
  await browser.close();
  console.log('Wrote', pdfPath);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
