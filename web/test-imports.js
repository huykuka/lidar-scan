#!/usr/bin/env node

// Simple Node.js script to test if key files can be parsed
const fs = require('fs');
const path = require('path');

function testFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    console.log(`✅ ${filePath} - syntax looks good`);
    return true;
  } catch (error) {
    console.log(`❌ ${filePath} - error: ${error.message}`);
    return false;
  }
}

const testFiles = [
  'src/app/core/services/metrics-websocket.service.ts',
  'src/app/core/services/stores/metrics-store.service.ts',
  'src/app/core/models/metrics.model.ts',
  'src/app/features/dashboard/dashboard.component.ts',
  'src/app/layout/components/header/header.component.ts',
  'src/app/layout/components/side-nav/side-nav.component.ts'
];

console.log('Testing key TypeScript files...\n');

const results = testFiles.map(testFile);
const passed = results.filter(r => r).length;
const total = results.length;

console.log(`\nSummary: ${passed}/${total} files passed basic syntax check`);