# contabilizei

Commands to register invoices (notas fiscais) in Contabilizei via headless automation.

## `/contabilizei:nf-tomada <file>`

Registers a **received NF** (nota fiscal, an incoming service invoice) from a local PDF or XML.

**What it does:**
1. Extracts the invoice data via a Python script (defensive multi-municipality PDF parsing or ABRASF XML).
2. Performs a headless login into Contabilizei; reads the access code automatically from Gmail.
3. Checks for duplicates via the UI listing (CNPJ + series + number).
4. Resolves the service provider (existing or new registration).
5. Fills in the registration form.
6. **Pauses for confirmation** before submitting — a fiscal action that's hard to reverse.
7. Reports the result.

**When to use:** whenever you receive a service invoice that needs to be registered in Contabilizei.

**Prerequisites:**
- macOS Keychain (used to store the password — never kept on disk).
- MCP `playwright-headless` configured and active in the Claude Code session.
- MCP `Gmail` configured and authenticated (`mcp__claude_ai_Gmail__*`).
- Python 3 with `pdfplumber` (installed automatically by `setup.sh`).

**Local data in `~/finance/contabilizei/`** — this directory is **never committed** to the repository. It contains:
- `.config` — login email (mode `600`).
- `extracted/` — JSONs and texts extracted from invoices (mode `600`), fiscal/PII data.

Clean up `extracted/` periodically; the files contain third-party data.
