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
 *   - terminal-only: ignores assistant text that is followed by tool activity.
 *     When the Stop hook runs, the turn's final assistant message may not be
 *     flushed to the transcript yet, so a naive "last text block" read returns
 *     the PREVIOUS turn's pre-tool lead-in (e.g. "Cleaning up the worktree:") —
 *     which always ends in a colon/lead-in and accounted for ~90% of historical
 *     false positives. We only evaluate text that is the last meaningful event
 *     (no tool_use / tool_result after it).
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

// The assistant text of the turn that just ended — but only if it is the last
// meaningful event in the transcript. If a tool_use (assistant) or tool_result
// (user) appears after the most recent assistant text, that text was a pre-tool
// lead-in and the turn continued past it; we return '' so the stop is allowed.
// This is what makes the guard robust to the transcript-flush race (see header).
function terminalAssistantText(transcriptPath) {
  let raw;
  try { raw = fs.readFileSync(transcriptPath, 'utf8'); } catch { return ''; }
  let lastText = '';
  let lastEventIsText = false;
  for (const line of raw.split('\n')) {
    let obj;
    try { obj = JSON.parse(line); } catch { continue; }
    const msg = obj.message || obj;
    const role = msg.role || obj.type;
    const content = msg.content;
    let hasTool = false;
    let txt = '';
    if (Array.isArray(content)) {
      for (const p of content) {
        if (!p || typeof p !== 'object') continue;
        if (p.type === 'tool_use' || p.type === 'tool_result') hasTool = true;
        else if (p.type === 'text') txt += p.text || '';
      }
    } else if (typeof content === 'string' && role === 'assistant') {
      txt = content;
    }
    // Update text first, then let tool activity override: a single message
    // carrying [text, tool_use] is a pre-tool lead-in, not a terminal stop.
    if (role === 'assistant' && txt.trim()) {
      lastText = txt.trim();
      lastEventIsText = true;
    }
    if (hasTool) lastEventIsText = false;
  }
  return lastEventIsText ? lastText : '';
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

  const last = d.transcript_path ? terminalAssistantText(d.transcript_path) : '';
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
