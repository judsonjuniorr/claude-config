---
name: uncompress
description: (herow) Restore full, verbose, explanatory prose for the rest of the session. Inverse of the default terse "caveman" output mode. Use when the user says "uncompress", "verbose", "normal mode", "talk normally", "stop caveman", "explain in full", or wants detailed walk-throughs instead of terse fragments.
model: haiku
effort: low
---

# Uncompress (full prose mode)

This config compresses output **by default** (terse "caveman" style, defined in the always-on `communication-style` rule). This skill is the **inverse toggle**: it turns compression OFF.

When invoked:

1. **Switch to full explanatory prose** for the rest of the session:
   - Complete sentences with normal grammar — articles, connectives, transitions.
   - Explain the *why*, not just the *what*. Walk through reasoning step by step.
   - Still no empty filler or pleasantries ("Great question!", "Certainly!") — verbose ≠ padded. Substance stays; only the terseness relaxes.
2. **State the switch in one line**, e.g. "Full-prose mode on — say `compress` or `caveman` to go back to terse."
3. **Persist** until the user re-compresses ("compress", "caveman", "be brief", "less tokens") or the session ends.

Unchanged regardless of mode: code blocks, commands, commit/PR text, and error messages are always reproduced verbatim; security warnings and destructive-action confirmations are always stated in full.
