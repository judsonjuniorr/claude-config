---
description: (herow) Generate a user-friendly changelog from commits since the last tag/release.
---

# Release Notes — End-User Changelog

When the user invokes `/release-notes`, follow these steps **exactly**. Do not skip any.

---

## Step 1 — Detect the last language used in this project

1. Find the repo root:
   ```bash
   git rev-parse --show-toplevel
   ```
   If it fails (not a git repo), use the current working directory as the root.
2. Try to read `<repo-root>/.claude/settings.local.json` and parse it as JSON.
3. Look up the path `customCommands.releaseNotes.lang`. Valid values: `pt-br` or `en`.
4. If the file is missing, is not valid JSON, the key is absent, or the value is invalid → **default = `pt-br`**.

Call this value `LAST_LANG`.

**Important:** never read, modify, or remove any other key in `settings.local.json`. Treat the rest of the file as opaque.

## Step 2 — Ask for the language via `AskUserQuestion`

Ask **one** question with two options. The option matching `LAST_LANG` **must come first** and have the suffix `(Recommended)` in its label.

- If `LAST_LANG == "pt-br"`:
  - Option 1: label `Português (Brasil) (Recommended)`, description `Changelog em pt-br`
  - Option 2: label `English`, description `Changelog in English`
- If `LAST_LANG == "en"`:
  - Option 1: label `English (Recommended)`, description `Changelog in English`
  - Option 2: label `Português (Brasil)`, description `Changelog em pt-br`

Question: `Which language should the changelog be in?` · header: `Language`.

Map the answer to a slug: `pt-br` or `en`. Call it `LANG`.

## Step 3 — Persist the choice per project

Write the chosen language to `<repo-root>/.claude/settings.local.json` under the path `customCommands.releaseNotes.lang`, **preserving every other key** already in the file. Steps:

1. Create the directory if needed: `mkdir -p <repo-root>/.claude`.
2. If `settings.local.json` does not exist, create it with `{}`.
3. Update it atomically using a JSON-aware tool (do **not** hand-edit with regex). Prefer:
   ```bash
   tmp=$(mktemp) && jq --arg lang "$LANG" \
     '.customCommands.releaseNotes.lang = $lang' \
     <repo-root>/.claude/settings.local.json > "$tmp" \
     && mv "$tmp" <repo-root>/.claude/settings.local.json
   ```
4. If `jq` is unavailable, fall back to a small Python one-liner that loads the JSON, sets `data.setdefault("customCommands", {}).setdefault("releaseNotes", {})["lang"] = LANG`, and dumps it back with 2-space indent.
5. Never touch other keys (`permissions`, `env`, `hooks`, etc.) — only set the namespaced `customCommands.releaseNotes.lang`.

## Step 4 — Collect commits

1. Identify the **most recent tag by date** (not alphabetical):
   ```bash
   git for-each-ref --sort=-creatordate --format='%(refname:short)' refs/tags | head -n 1
   ```
2. If a tag exists, list commits after it:
   ```bash
   git log <tag>..HEAD --no-merges --pretty=format:'%H%x09%s%x09%b%x1e'
   ```
3. If **no tag exists**, use the last 50 commits:
   ```bash
   git log -50 --no-merges --pretty=format:'%H%x09%s%x09%b%x1e'
   ```
4. Ignore commits whose subject starts with `Merge branch`, `Merge pull request`, `Merge remote-tracking branch`.
5. Cancel out **revert ↔ original** pairs that both appear in the range (look for `Revert "<msg>"` or `This reverts commit <sha>`).

## Step 5 — Classify each commit

Each commit falls into **exactly one** category:

| Category           | Icon  | When to use                                                                |
|--------------------|-------|----------------------------------------------------------------------------|
| New Features       | ✨    | A new capability visible to the user                                       |
| Improvements       | 🛠️    | Enhancement to something existing (performance, UX, visual polish)         |
| Bug Fixes          | 🐛    | A defect was corrected                                                     |
| Internal Changes   | 🔧    | Refactor, deps, config, tooling (no user-visible impact)                   |

Decision rules (apply in order):

- Commit mixes a new feature + a fix → **✨ New Features**.
- Message is ambiguous/unclear → **🔧 Internal Changes**.
- Conventional Commit prefixes `chore`, `ci`, `build`, `deps`, `test` → always **🔧**.
- Prefix `style` (visual/CSS) → **🛠️**.
- Prefix `perf` → **🛠️**.
- Prefix `feat` → **✨**.
- Prefix `fix` → **🐛**.
- Prefix `refactor` → **🔧**.

**Breaking changes:** if the body contains `BREAKING CHANGE:` or the subject uses `!:` (e.g. `feat!:`), prefix the bullet with `⚠️ Breaking:` (or the localized equivalent).

## Step 6 — Write the bullets

- One short, direct sentence in **past tense**, written in `LANG`.
- **No technical jargon.** Translate developer terms into user-facing language:
  - "refactored middleware" → "Internal stability improvements"
  - "fixed race condition in state hook" → "Fixed an issue that occasionally caused data to load incorrectly"
  - "bumped dependency X" → "Updated internal components"
- **Never include:** commit hashes, branch names, PR/issue IDs, or author names.
- **Group related commits** into a single bullet when they describe the same logical change.
- **Omit empty categories.**

## Step 7 — Suggest the next version (SemVer)

- Any `⚠️ Breaking` item → bump **major**.
- Otherwise, any **✨ New Features** → bump **minor**.
- Otherwise, any **🐛 Bug Fixes** or **🛠️ Improvements** → bump **patch**.
- Only **🔧 Internal Changes** → bump **patch** and note that fact.

If no current version is detectable (no tags), suggest `v0.1.0` as the initial version.

## Step 8 — Render in the chat

Output **inline in the chat** (do NOT create a file). Use exactly this structure, **omitting any section without items**. Localize headings/labels/summary to `LANG`, keeping icons and overall structure identical.

**`pt-br` template:**

```markdown
# 📋 Changelog

> Atualização: vX.Y.Z → vX.Y.Z (próxima)
> Data: YYYY-MM-DD

---

## ✨ Novidades
- Descrição da novidade

## 🛠️ Melhorias
- Descrição da melhoria

## 🐛 Correções
- Descrição da correção

## 🔧 Mudanças Internas
- Descrição da mudança interna

---

📊 **Resumo:** X novidade(s) · X melhoria(s) · X correção(ões) · X mudança(s) interna(s)
```

**`en` template:**

```markdown
# 📋 Changelog

> Update: vX.Y.Z → vX.Y.Z (next)
> Date: YYYY-MM-DD

---

## ✨ New Features
- Description

## 🛠️ Improvements
- Description

## 🐛 Bug Fixes
- Description

## 🔧 Internal Changes
- Description

---

📊 **Summary:** X new feature(s) · X improvement(s) · X fix(es) · X internal change(s)
```

Use today's date in the `Data`/`Date` field.

## Step 9 — Validation checklist (before sending)

- [ ] Every sentence is in `LANG`.
- [ ] No technical jargon leaked into user-facing text.
- [ ] Empty categories are omitted.
- [ ] The numeric summary exactly matches the listed items.
- [ ] No commit hashes, branch names, or PR IDs are present.
- [ ] The next version follows SemVer based on the changes.
- [ ] Output is delivered **in the chat** — no file was created (only `<repo-root>/.claude/settings.local.json` was updated in Step 3, and only its `customCommands.releaseNotes.lang` key).
