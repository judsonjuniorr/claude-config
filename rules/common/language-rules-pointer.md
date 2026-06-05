## Language-specific rules

Language-specific coding rules live in the claude-config repo under `{{REPO_DIR}}/rules/<language>/`.

When you start working in a project whose primary language matches one of the available
sets, read the relevant files **before writing code** and apply them for that session:

- TypeScript / JavaScript → `{{REPO_DIR}}/rules/typescript/*.md`
- Python → `{{REPO_DIR}}/rules/python/*.md`

Detect the primary language from the project (e.g. `package.json`/`tsconfig.json` → TypeScript,
`pyproject.toml`/`requirements.txt` → Python). These rules are applied per-project by you, the
session — they are intentionally not auto-loaded globally, so they never add noise to unrelated
projects. If no language set matches, skip this rule.
