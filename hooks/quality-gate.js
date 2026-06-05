#!/usr/bin/env node
/**
 * Quality Gate Hook
 *
 * Runs lightweight quality checks after file edits.
 * - Targets one file when file_path is provided
 * - Falls back to no-op when language/tooling is unavailable
 *
 * For JS/TS files with Biome, skips because post-edit-format (if present)
 * already handles those. Still handles .json/.md and Go/Python files.
 * Self-contained — no external lib dependencies.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MAX_STDIN = 1024 * 1024;

// ── Inlined formatter detection ─────────────────────────────────────

const BIOME_CONFIGS = ['biome.json', 'biome.jsonc'];
const PRETTIER_CONFIGS = [
  '.prettierrc', '.prettierrc.json', '.prettierrc.js', '.prettierrc.cjs',
  '.prettierrc.mjs', '.prettierrc.yml', '.prettierrc.yaml', '.prettierrc.toml',
  'prettier.config.js', 'prettier.config.cjs', 'prettier.config.mjs'
];
const PROJECT_ROOT_MARKERS = ['package.json', ...BIOME_CONFIGS, ...PRETTIER_CONFIGS];

function findProjectRoot(startDir) {
  let dir = startDir;
  while (dir !== path.dirname(dir)) {
    for (const marker of PROJECT_ROOT_MARKERS) {
      if (fs.existsSync(path.join(dir, marker))) return dir;
    }
    dir = path.dirname(dir);
  }
  return startDir;
}

function detectFormatter(projectRoot) {
  for (const cfg of BIOME_CONFIGS) {
    if (fs.existsSync(path.join(projectRoot, cfg))) return 'biome';
  }
  try {
    const pkgPath = path.join(projectRoot, 'package.json');
    if (fs.existsSync(pkgPath)) {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
      if ('prettier' in pkg) return 'prettier';
    }
  } catch { /* continue */ }
  for (const cfg of PRETTIER_CONFIGS) {
    if (fs.existsSync(path.join(projectRoot, cfg))) return 'prettier';
  }
  return null;
}

function resolveFormatterBin(projectRoot, formatter) {
  const isWin = process.platform === 'win32';
  const binName = formatter === 'biome' ? 'biome' : 'prettier';
  const localBin = path.join(projectRoot, 'node_modules', '.bin', isWin ? `${binName}.cmd` : binName);
  if (fs.existsSync(localBin)) return { bin: localBin, prefix: [] };
  // Fall back to npx
  const npx = isWin ? 'npx.cmd' : 'npx';
  const pkgName = formatter === 'biome' ? '@biomejs/biome' : 'prettier';
  return { bin: npx, prefix: [pkgName] };
}

// ── Main logic ───────────────────────────────────────────────────────

function exec(command, args, cwd) {
  return spawnSync(command, args, {
    cwd: cwd || process.cwd(),
    encoding: 'utf8',
    env: process.env,
    timeout: 15000
  });
}

function log(msg) {
  process.stderr.write(`${msg}\n`);
}

function maybeRunQualityGate(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return;

  filePath = path.resolve(filePath);
  const ext = path.extname(filePath).toLowerCase();
  const fix = String(process.env.HEROW_QUALITY_GATE_FIX || '').toLowerCase() === 'true';
  const strict = String(process.env.HEROW_QUALITY_GATE_STRICT || '').toLowerCase() === 'true';

  if (['.ts', '.tsx', '.js', '.jsx', '.json', '.md'].includes(ext)) {
    const projectRoot = findProjectRoot(path.dirname(filePath));
    const formatter = detectFormatter(projectRoot);

    if (formatter === 'biome') {
      // JS/TS already handled by post-edit-format if present; only process .json/.md here
      if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) return;
      const resolved = resolveFormatterBin(projectRoot, 'biome');
      const args = [...resolved.prefix, 'check', filePath];
      if (fix) args.push('--write');
      const result = exec(resolved.bin, args, projectRoot);
      if (result.status !== 0 && strict) log(`[QualityGate] Biome check failed for ${filePath}`);
      return;
    }

    if (formatter === 'prettier') {
      const resolved = resolveFormatterBin(projectRoot, 'prettier');
      const args = [...resolved.prefix, fix ? '--write' : '--check', filePath];
      const result = exec(resolved.bin, args, projectRoot);
      if (result.status !== 0 && strict) log(`[QualityGate] Prettier check failed for ${filePath}`);
      return;
    }

    return; // No formatter configured
  }

  if (ext === '.go') {
    if (fix) {
      const r = exec('gofmt', ['-w', filePath]);
      if (r.status !== 0 && strict) log(`[QualityGate] gofmt failed for ${filePath}`);
    } else if (strict) {
      const r = exec('gofmt', ['-l', filePath]);
      if (r.status !== 0 || (r.stdout && r.stdout.trim())) {
        log(`[QualityGate] gofmt check failed for ${filePath}`);
      }
    }
    return;
  }

  if (ext === '.py') {
    const args = ['format'];
    if (!fix) args.push('--check');
    args.push(filePath);
    const r = exec('ruff', args);
    if (r.status !== 0 && strict) log(`[QualityGate] Ruff check failed for ${filePath}`);
  }
}

function run(rawInput) {
  try {
    const input = JSON.parse(rawInput);
    const filePath = String(input.tool_input?.file_path || '');
    maybeRunQualityGate(filePath);
  } catch {
    // Ignore parse errors
  }
  return rawInput;
}

// ── stdin entry point ────────────────────────────────────────────────
if (require.main === module) {
  let raw = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    if (raw.length < MAX_STDIN) raw += chunk.substring(0, MAX_STDIN - raw.length);
  });
  process.stdin.on('end', () => {
    const result = run(raw);
    process.stdout.write(result);
  });
}

module.exports = { run };
