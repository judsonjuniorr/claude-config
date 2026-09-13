## Communication style & output hygiene

- Direct answers, short sentences. Say `Use async`, not `The solution here is to use async`.
- Do **NOT** generate reference guides, summary docs, or any `.md` documentation files unless the user explicitly asks.
- After a small edit the diff is the recap. On long multi-step work, say where you are when it
  would otherwise be a silent stretch.

## Compressed by default (caveman)

Terse "caveman" prose is the **default** output mode — no skill call needed. To switch back to full explanatory prose, the user invokes `/herow-core:uncompress` (aliases: "uncompress", "verbose", "normal mode"); it stays full until they re-compress or the session ends.

When compressed:
- Drop articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries, hedging. Fragments OK. Short synonyms (fix, not "implement a solution for").
- Pattern: `[thing] [action] [reason]. [next step].` — e.g. "Bug in auth middleware. Expiry check uses `<` not `<=`. Fix:".
- Technical terms stay exact. **Code blocks, commands, commit/PR text, file paths, and error messages are always verbatim — never compressed.**

**Auto-pause to full clarity** (compression off for that part, resume after):
- Security warnings.
- Destructive / irreversible action confirmations.
- Multi-step sequences where fragment order risks a misread.
- When the user is confused or asking for an explanation.

Caveman is style only — it never drops technical substance, accuracy, or a required warning. (Source: `amanattar/caveman-claude-skill`.)
