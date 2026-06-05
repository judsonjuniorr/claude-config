#!/usr/bin/env node

/**
 * Stop Hook: Check for console.log statements in modified files
 *
 * Cross-platform (Windows, macOS, Linux)
 *
 * Runs after each response and checks if any modified JavaScript/TypeScript
 * files contain console.log statements. Provides warnings to help developers
 * remember to remove debug statements before committing.
 *
 * Exclusions: test files, config files, and scripts/ directory (where
 * console.log is often intentional).
 */

'use strict';

const fs = require('fs');
const { execSync, spawnSync } = require('child_process');

// Files where console.log is expected and should not trigger warnings
const EXCLUDED_PATTERNS = [
  /\.test\.[jt]sx?$/,
  /\.spec\.[jt]sx?$/,
  /\.config\.[jt]s$/,
  /scripts\//,
  /__tests__\//,
  /__mocks__\//,
];

function isGitRepo() {
  try {
    const result = spawnSync('git', ['rev-parse', '--git-dir'], { stdio: 'pipe', encoding: 'utf8' });
    return result.status === 0;
  } catch { return false; }
}

function getGitModifiedFiles() {
  try {
    const result = spawnSync('git', ['diff', '--name-only', 'HEAD'], { stdio: 'pipe', encoding: 'utf8' });
    if (result.status !== 0) return [];
    return result.stdout.split('\n').filter(Boolean).filter(f => /\.(tsx?|jsx?)$/.test(f));
  } catch { return []; }
}

const MAX_STDIN = 1024 * 1024; // 1MB limit
let data = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', chunk => {
  if (data.length < MAX_STDIN) {
    const remaining = MAX_STDIN - data.length;
    data += chunk.substring(0, remaining);
  }
});

process.stdin.on('end', () => {
  try {
    if (!isGitRepo()) {
      process.stdout.write(data);
      process.exit(0);
    }

    const files = getGitModifiedFiles()
      .filter(f => fs.existsSync(f))
      .filter(f => !EXCLUDED_PATTERNS.some(pattern => pattern.test(f)));

    let hasConsole = false;

    for (const file of files) {
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { content = null; }
      if (content && content.includes('console.log')) {
        process.stderr.write(`[Hook] WARNING: console.log found in ${file}\n`);
        hasConsole = true;
      }
    }

    if (hasConsole) {
      process.stderr.write('[Hook] Remove console.log statements before committing\n');
    }
  } catch (err) {
    process.stderr.write(`[Hook] check-console-log error: ${err.message}\n`);
  }

  // Always output the original data
  process.stdout.write(data);
  process.exit(0);
});
