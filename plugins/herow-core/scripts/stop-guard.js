#!/usr/bin/env node
/**
 * Stop Hook: claude-config stop guard (node port of the former stop-guard.sh,
 * which spawned python3 on every Stop — node is already a dependency of the
 * other hooks, so this saves an interpreter startup per Stop).
 *
 * Catches premature stops — when the model ends its turn mid-task — and asks
 * it to continue, so the user doesn't have to type "continue".
 *
 * Safe by construction:
 *   - respects stop_hook_active (never re-fires inside a continuation it caused)
 *   - hard per-session cap (MAX) so it can never loop forever
 *   - conservative: only fires on clear incompleteness signals (unbalanced code
 *     fence, or a trailing "I'll now…"-style lead-in with nothing after it)
 * Never errors; defaults to allowing the stop.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const MAX = 3;
const MAX_STDIN = 1024 * 1024;

const LEAD_IN_SIGNALS = [
  'i will now', 'next, i', 'continuing', 'one moment', 'stand by',
  'hold on', 'proceeding to', 'let me continue', 'let me now',
];

function lastAssistantText(transcriptPath) {
  let raw;
  try { raw = fs.readFileSync(transcriptPath, 'utf8'); } catch { return ''; }
  let last = '';
  for (const line of raw.split('\n')) {
    let obj;
    try { obj = JSON.parse(line); } catch { continue; }
    const msg = obj.message || obj;
    const role = msg.role || obj.type;
    if (role !== 'assistant') continue;
    let txt = '';
    if (Array.isArray(msg.content)) {
      txt = msg.content
        .filter(p => p && typeof p === 'object' && p.type === 'text')
        .map(p => p.text || '')
        .join('');
    } else if (typeof msg.content === 'string') {
      txt = msg.content;
    }
    if (txt.trim()) last = txt.trim();
  }
  return last;
}

function main(rawInput) {
  let d;
  try { d = JSON.parse(rawInput || '{}'); } catch { return; }

  // Already continuing because of a stop hook → let this stop through.
  if (d.stop_hook_active) return;

  const session = String(d.session_id || 'default');
  const safe = session.replace(/[^a-zA-Z0-9_-]/g, '') || 'default';
  const cntFile = path.join(os.tmpdir(), '.claude-config-stop-guard-' + safe);

  let cnt = 0;
  try { cnt = parseInt(fs.readFileSync(cntFile, 'utf8').trim(), 10) || 0; } catch { cnt = 0; }

  if (cnt >= MAX) {
    try { fs.unlinkSync(cntFile); } catch { /* best-effort */ }
    return;
  }

  const last = d.transcript_path ? lastAssistantText(d.transcript_path) : '';
  if (!last) return;

  let incomplete = false;
  if ((last.match(/```/g) || []).length % 2 === 1) {
    incomplete = true;
  } else {
    const tail = last.slice(-80).toLowerCase();
    const trimmed = last.replace(/\s+$/, '');
    if (LEAD_IN_SIGNALS.some(s => tail.includes(s)) || /[:…]$/.test(trimmed)) {
      incomplete = true;
    }
  }

  if (!incomplete) {
    try { fs.unlinkSync(cntFile); } catch { /* best-effort */ }
    return;
  }

  try { fs.writeFileSync(cntFile, String(cnt + 1), 'utf8'); } catch { /* best-effort */ }

  const reason =
    'You appear to have stopped mid-task (incomplete output, an unbalanced code ' +
    'fence, or a trailing lead-in with nothing after it). Continue and finish the ' +
    'task you were asked to do: complete the remaining reasoning and steps before ' +
    'ending your turn. If you are genuinely blocked, say so explicitly and state ' +
    'what you need instead of stopping silently.';
  process.stdout.write(JSON.stringify({ decision: 'block', reason }) + '\n');
}

let data = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  if (data.length < MAX_STDIN) data += chunk.substring(0, MAX_STDIN - data.length);
});
process.stdin.on('end', () => {
  try { main(data); } catch { /* never block the stop on errors */ }
  process.exit(0);
});
