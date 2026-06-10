#!/usr/bin/env node
/**
 * Stop Hook: Batch format and typecheck all JS/TS files edited this response
 *
 * Cross-platform (Windows, macOS, Linux)
 *
 * Reads the accumulator written by post-edit-accumulator (if present) and
 * processes all edited files in one pass: groups files by project root for
 * a single formatter invocation per root, and groups .ts/.tsx files by
 * tsconfig dir for a single tsc --noEmit per tsconfig.
 *
 * Self-contained — no external lib dependencies.
 */

'use strict';

const crypto = require('crypto');
const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MAX_STDIN = 1024 * 1024;
// Must finish inside the hook's 120s timeout (hooks.json) with headroom.
const TOTAL_BUDGET_MS = 100_000;

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
  const npx = isWin ? 'npx.cmd' : 'npx';
  const pkgName = formatter === 'biome' ? '@biomejs/biome' : 'prettier';
  return { bin: npx, prefix: [pkgName] };
}

// ── Accumulator file path ────────────────────────────────────────────

function getAccumFile() {
  const raw =
    process.env.CLAUDE_SESSION_ID ||
    crypto.createHash('sha1').update(process.cwd()).digest('hex').slice(0, 12);
  const sessionId = raw.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 64);
  return path.join(os.tmpdir(), `herow-edited-${sessionId}.txt`);
}

function parseAccumulator(raw) {
  return [...new Set(raw.split('\n').map(l => l.trim()).filter(Boolean))];
}

// ── Formatting batch ─────────────────────────────────────────────────

const UNSAFE_PATH_CHARS = /[&|<>^%!\s()]/;
// Biome can't format markdown; Prettier handles everything we accumulate.
const BIOME_FORMAT_EXT = /\.(ts|tsx|js|jsx|json|jsonc)$/;
const PRETTIER_FORMAT_EXT = /\.(ts|tsx|js|jsx|json|jsonc|md)$/;

function formatBatch(projectRoot, files, timeoutMs) {
  const formatter = detectFormatter(projectRoot);
  if (!formatter) return;
  const resolved = resolveFormatterBin(projectRoot, formatter);
  const extFilter = formatter === 'biome' ? BIOME_FORMAT_EXT : PRETTIER_FORMAT_EXT;
  const existingFiles = files.filter(f => extFilter.test(f) && fs.existsSync(f));
  if (existingFiles.length === 0) return;

  const fileArgs =
    formatter === 'biome'
      ? [...resolved.prefix, 'check', '--write', ...existingFiles]
      : [...resolved.prefix, '--write', ...existingFiles];

  try {
    if (process.platform === 'win32' && resolved.bin.endsWith('.cmd')) {
      if (existingFiles.some(f => UNSAFE_PATH_CHARS.test(f))) {
        process.stderr.write('[Hook] stop-format-typecheck: skipping batch — unsafe path chars\n');
        return;
      }
      const result = spawnSync(resolved.bin, fileArgs, { cwd: projectRoot, shell: true, stdio: 'pipe', timeout: timeoutMs });
      if (result.error) throw result.error;
    } else {
      execFileSync(resolved.bin, fileArgs, { cwd: projectRoot, stdio: ['pipe', 'pipe', 'pipe'], timeout: timeoutMs });
    }
  } catch {
    // Formatter not installed or failed — non-blocking
  }
}

// ── Python / Go format batches (parity with the removed per-edit gate) ──

function formatPython(files, timeoutMs) {
  const existing = files.filter(f => fs.existsSync(f));
  if (existing.length === 0) return;
  try {
    execFileSync('ruff', ['format', ...existing], { stdio: ['pipe', 'pipe', 'pipe'], timeout: timeoutMs });
  } catch { /* ruff missing or failed — non-blocking */ }
}

function formatGo(files, timeoutMs) {
  const existing = files.filter(f => fs.existsSync(f));
  if (existing.length === 0) return;
  try {
    execFileSync('gofmt', ['-w', ...existing], { stdio: ['pipe', 'pipe', 'pipe'], timeout: timeoutMs });
  } catch { /* gofmt missing or failed — non-blocking */ }
}

// ── Typecheck batch ──────────────────────────────────────────────────

function findTsConfigDir(filePath) {
  let dir = path.dirname(filePath);
  const fsRoot = path.parse(dir).root;
  let depth = 0;
  while (dir !== fsRoot && depth < 20) {
    if (fs.existsSync(path.join(dir, 'tsconfig.json'))) return dir;
    dir = path.dirname(dir);
    depth++;
  }
  return null;
}

function typecheckBatch(tsConfigDir, editedFiles, timeoutMs) {
  const isWin = process.platform === 'win32';
  const npxBin = isWin ? 'npx.cmd' : 'npx';
  const args = ['tsc', '--noEmit', '--pretty', 'false'];
  const opts = { cwd: tsConfigDir, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], timeout: timeoutMs };

  let stdout = '';
  let stderr = '';
  let failed = false;

  try {
    if (isWin) {
      const result = spawnSync(npxBin, args, { ...opts, shell: true });
      if (result.error) return;
      if (result.status !== 0) { stdout = result.stdout || ''; stderr = result.stderr || ''; failed = true; }
    } else {
      execFileSync(npxBin, args, opts);
    }
  } catch (err) {
    stdout = err.stdout || '';
    stderr = err.stderr || '';
    failed = true;
  }

  if (!failed) return;

  const lines = (stdout + stderr).split('\n');
  for (const filePath of editedFiles) {
    const relPath = path.relative(tsConfigDir, filePath);
    const candidates = new Set([filePath, relPath]);
    const relevantLines = lines
      .filter(line => { for (const c of candidates) { if (line.includes(c)) return true; } return false; })
      .slice(0, 10);
    if (relevantLines.length > 0) {
      process.stderr.write(`[Hook] TypeScript errors in ${path.basename(filePath)}:\n`);
      relevantLines.forEach(line => process.stderr.write(line + '\n'));
    }
  }
}

// ── Main ─────────────────────────────────────────────────────────────

function main() {
  const accumFile = getAccumFile();

  let raw;
  try { raw = fs.readFileSync(accumFile, 'utf8'); } catch { return; }
  try { fs.unlinkSync(accumFile); } catch { /* best-effort */ }

  const files = parseAccumulator(raw);
  if (files.length === 0) return;

  const byProjectRoot = new Map();
  const pyFiles = [];
  const goFiles = [];
  for (const filePath of files) {
    const resolved = path.resolve(filePath);
    if (!fs.existsSync(resolved)) continue;
    if (/\.py$/.test(resolved)) { pyFiles.push(resolved); continue; }
    if (/\.go$/.test(resolved)) { goFiles.push(resolved); continue; }
    if (!/\.(ts|tsx|js|jsx|json|jsonc|md)$/.test(resolved)) continue;
    const root = findProjectRoot(path.dirname(resolved));
    if (!byProjectRoot.has(root)) byProjectRoot.set(root, []);
    byProjectRoot.get(root).push(resolved);
  }

  const byTsConfigDir = new Map();
  for (const filePath of files) {
    if (!/\.(ts|tsx)$/.test(filePath)) continue;
    const resolved = path.resolve(filePath);
    if (!fs.existsSync(resolved)) continue;
    const tsDir = findTsConfigDir(resolved);
    if (!tsDir) continue;
    if (!byTsConfigDir.has(tsDir)) byTsConfigDir.set(tsDir, []);
    byTsConfigDir.get(tsDir).push(resolved);
  }

  const totalBatches =
    byProjectRoot.size + byTsConfigDir.size + (pyFiles.length ? 1 : 0) + (goFiles.length ? 1 : 0);
  const perBatchMs = totalBatches > 0 ? Math.floor(TOTAL_BUDGET_MS / totalBatches) : 60_000;

  for (const [root, batch] of byProjectRoot) formatBatch(root, batch, perBatchMs);
  formatPython(pyFiles, perBatchMs);
  formatGo(goFiles, perBatchMs);
  for (const [tsDir, batch] of byTsConfigDir) typecheckBatch(tsDir, batch, perBatchMs);
}

function run(rawInput) {
  try { main(); } catch (err) {
    process.stderr.write(`[Hook] stop-format-typecheck error: ${err.message}\n`);
  }
  return rawInput;
}

if (require.main === module) {
  let stdinData = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    if (stdinData.length < MAX_STDIN) stdinData += chunk.substring(0, MAX_STDIN - stdinData.length);
  });
  process.stdin.on('end', () => {
    process.stdout.write(run(stdinData));
    process.exit(0);
  });
}

module.exports = { run, parseAccumulator };
