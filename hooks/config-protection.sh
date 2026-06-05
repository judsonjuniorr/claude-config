#!/usr/bin/env bash
# claude-config PreToolUse/(Edit|Write) guard.
# Surfaces a permission prompt ("ask") before editing a linter/formatter/build config,
# so tooling configs are never changed silently as a side effect of unrelated work.
# Never blocks hard, never errors.

FILE="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',d).get('file_path',''))" 2>/dev/null || true)"
[ -n "$FILE" ] || exit 0

base="$(basename "$FILE")"
case "$base" in
  .eslintrc|.eslintrc.*|eslint.config.*|\
  .prettierrc|.prettierrc.*|prettier.config.*|\
  biome.json|biome.jsonc|\
  .ruff.toml|ruff.toml|\
  .editorconfig|\
  tsconfig.json|tsconfig.*.json|\
  .markdownlint.json|.markdownlint.*|\
  commitlint.config.*|\
  .stylelintrc|.stylelintrc.*) ;;
  *) exit 0 ;;
esac

reason="config protection: editing a linter/formatter/build config ($base). Confirm this change is intended and not an incidental side effect."
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'ask','permissionDecisionReason':sys.argv[1]}}))" "$reason"
exit 0
