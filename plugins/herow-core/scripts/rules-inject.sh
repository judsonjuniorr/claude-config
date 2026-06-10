#!/usr/bin/env bash
# SessionStart hook: inject herow always-on rules into context.
# Plugins cannot ship CLAUDE.md/rules as components, so this prints
# rules/common/*.md to stdout (SessionStart stdout becomes session context)
# plus a language-rules pointer with the resolved plugin path baked in.
set -u

ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$ROOT" ] && [ -d "$ROOT/rules/common" ] || exit 0

for f in "$ROOT"/rules/common/*.md; do
  [ -f "$f" ] || continue
  # pointer is generated below with resolved paths; skip any legacy copy
  case "$(basename "$f")" in language-rules-pointer.md) continue ;; esac
  cat "$f"
  echo
done

cat <<EOF
## Language-specific rules

Language-specific coding rules ship with the herow-core plugin under
\`$ROOT/rules/<language>/\`. When you start working in a project whose primary
language matches one of the sets below, read the relevant files **before
writing code** and apply them for that session:

- TypeScript / JavaScript → \`$ROOT/rules/typescript/\`
- Python → \`$ROOT/rules/python/\`
- React (web apps) → \`$ROOT/rules/react/\`
- Web (HTML/CSS/a11y/design) → \`$ROOT/rules/web/\`
- Rust → \`$ROOT/rules/rust/\`
- Swift → \`$ROOT/rules/swift/\`
- C# / .NET → \`$ROOT/rules/csharp/\`
- Backend/API work (REST design, layered architecture, caching, background jobs) → \`$ROOT/rules/backend/\`

Detect the primary language from the project (e.g. \`package.json\`/\`tsconfig.json\`
→ TypeScript, \`pyproject.toml\`/\`requirements.txt\` → Python). These rules are
applied per-project by you, the session — they are intentionally not auto-loaded
globally. If no language set matches, skip this rule.
EOF

exit 0
