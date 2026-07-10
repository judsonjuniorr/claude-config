---
description: (herow) Registers a received NF (service invoice) in Contabilizei from a PDF/XML — headless login with code via Gmail, duplicate check, and confirmation before submitting.
argument-hint: "<path to the NF PDF or XML>"
allowed-tools: Bash, Read, Write, AskUserQuestion, mcp__playwright-headless__browser_navigate, mcp__playwright-headless__browser_snapshot, mcp__playwright-headless__browser_click, mcp__playwright-headless__browser_type, mcp__playwright-headless__browser_select_option, mcp__playwright-headless__browser_fill_form, mcp__playwright-headless__browser_evaluate, mcp__playwright-headless__browser_wait_for, mcp__playwright-headless__browser_close, mcp__claude_ai_Gmail__search_threads, mcp__claude_ai_Gmail__get_thread
effort: medium
---

# `/contabilizei:nf-tomada`

**Global rule: every question to the user uses `AskUserQuestion` with options — never inline.** `AskUserQuestion` requires **at least 2 options** per question; for free-text fields (email, password, code), offer the desired option + an alternative such as "Abort"/"Other".

Registers a received NF (a service invoice received from a provider) in Contabilizei from a local PDF or XML file.

## Step 0 — Extract NF data

Resolve `$ARGUMENTS` as the file path. If empty or not provided, use `AskUserQuestion` to ask for the path.

```bash
SCRIPT_DIR="${CLAUDE_PLUGIN_ROOT}/scripts/contabilizei"
[ -f "$SCRIPT_DIR/extract_nf.py" ] || { echo "err|scripts-not-found|$SCRIPT_DIR" >&2; exit 1; }
bash "$SCRIPT_DIR/setup.sh" >&2
python3 "$SCRIPT_DIR/extract_nf.py" "<path>"
```

Read the returned JSON. If any required field is `null` (`cnpj`, `razao_social`, `data_emissao`, `numero`, `valor`), read the corresponding `.txt` at `~/finance/contabilizei/extracted/<base>.txt` and fill in the fields using the raw text.

**Hard-stop:** if, after reading the `.txt`, any required field is still `null`, stop with a clear error:

> "Could not extract [fields] from the NF. Check the file and provide the values manually, or try another format."

Use `AskUserQuestion` to offer: correct manually / abort.

When showing the extracted data in the confirmation (step 6), **highlight** fields that came from the `.txt`/regex (fragile source) for the user to review.

**Value:** `parse_valor_br` returns cents (int). Format as `R$ X.XXX,XX` only for display; pass the formatted value into the form.

## Step 1 — Credentials (first time)

```bash
CONTABILIZEI_HOME="$HOME/finance/contabilizei"
CONFIG="$CONTABILIZEI_HOME/.config"
```

If `$CONFIG` does not exist or has no `EMAIL=`:

Use `AskUserQuestion` to collect the Contabilizei login email.

Save it in `$CONFIG` with `chmod 600`:
```
EMAIL="<email>"
```

Check whether the password is already in the Keychain:
```bash
security find-generic-password -a "<email>" -s "contabilizei-login" -w >/dev/null 2>&1
```

If not: use `AskUserQuestion` to ask for the password (free-text field with a warning that it won't be shown in the transcript). Save it **only in the Keychain**:
```bash
security add-generic-password -a "<email>" -s "contabilizei-login" -w "<password>" -U
```

The password **never appears in argv or in logs.** Use `browser_fill_form` or `browser_evaluate` to inject it into the form — never `browser_type` with the literal value visible.

## Step 2 — Login and listing

Record the moment the login starts (for the OTP code time guard):
```
SUBMIT_TIME = now (ISO)
```

**Initial guidance — mandatory snapshot before any action:**

```
browser_navigate → https://app.contabilizei.com.br/painel-de-controle/#/nota-tomada/listagem
browser_snapshot
```

> The canonical URL includes `/painel-de-controle/`. Without it the app redirects, but use the full form in the navigations of steps 4–6 to avoid extra redirects.

Analyze the snapshot:
- **If already on the listing** (logged in): go to step 3.
- **If on the login screen** (email/password form):
  1. Read the password from the Keychain: `security find-generic-password -a "<email>" -s "contabilizei-login" -w`
  2. Fill in the email field with `browser_type`.
  3. Fill in the password with `browser_evaluate`, injecting JS that writes to the password field — or use `browser_fill_form` — **never** with the literal value in `browser_type`.
  4. Submit the form.
  5. `browser_snapshot` → analyze the result.
- **If an access code challenge appears** (a form asking for a code sent by email):
  - See the "Access code" sub-step below.
- **If another challenge appears (SMS, authenticator, trusted device)**:
  - Use `AskUserQuestion` to ask the user for the code (manual fallback).
  - Fill it in and submit.
- **If the session expires during the flow** (detected at any step): re-run this entire step 2.

### Sub-step: Access code by email

The code sender is `seguranca@contabilizei.com.br` (subject: "Seu código de acesso à plataforma chegou!"). The query `from:contabilizei` covers it.

Gmail polling (up to ~30s, 6 attempts with `browser_wait_for {time: 5}` between them):

```
For each attempt (i = 1..6):
  browser_wait_for {time: 5}   # spaces out without a blocking sleep
  Gmail.search_threads(query="from:contabilizei newer_than:1h", max_results=5)
  For each thread (most recent first):
    Gmail.get_thread(thread_id=...)
    Extract the body of the most recent email
    Check: email timestamp > SUBMIT_TIME  ← time guard
    Contextual regex: r'(?:c[oó]digo(?:\s+de)?\s+(?:acesso|verifica[çc][ãa]o)|seu\s+c[oó]digo)[^\d]*(\d{4,8})'
    If match AND message-id not yet consumed:
      Record the message-id as consumed (avoids an expired code on retry)
      Use the found code → fill in and submit
      Mark the email as read (remove the UNREAD label via Gmail.unlabel_message — always, after obtaining the code)
      Break the loop
```

If after 6 attempts no code is found or the challenge isn't by email:
- Use `AskUserQuestion` to ask the user for the code (manual fallback).

After submitting the code: `browser_snapshot` → confirm you're on the listing before proceeding.

### Sub-step: Dismiss blocking modals (run after EVERY navigation)

The app shows recurring modals that reappear on every navigation and cover the content: **"Sua mensalidade está atrasada"** ("Your monthly fee is overdue"), **"Por onde eu começo?"** ("Where do I start?"), the app **QR code**, and similar. Dismiss them before interacting with the page — click directly via JS (they may be outside the viewport, which makes `browser_click` time out):

```
browser_evaluate:
() => {
  const labels = ['Solicitar mais dias', 'Entendi', 'Fechar', 'close'];
  const clicked = [];
  document.querySelectorAll('button').forEach(b => {
    const t = (b.textContent || '').trim();
    const aria = b.getAttribute('aria-label') || '';
    if (labels.some(l => t === l || t.includes(l) || aria === l)) { b.click(); clicked.push(t || aria); }
  });
  return clicked;
}
```

> Do **NOT** click "Regularizar mensalidade" ("Settle monthly fee"), "Cancelar" ("Cancel") on a registration dialog, or any fiscal action button. Only dismiss informational/onboarding modals.
>
> **Watch out for latent dialogs:** the accessibility snapshot may list `dialog` nodes that are in the DOM but **hidden** (`v-show`/`display:none`) — they aren't actually active. Before treating a dialog as blocking or acting on its buttons, **confirm it's visible**:
>
> ```
> browser_evaluate (on the dialog element):
> (el) => { const r = el.getBoundingClientRect(); return !!el.offsetParent && r.width > 0 && r.height > 0; }
> ```

## Step 3 — Check for duplicates

The listing **has no** free-text search by CNPJ/number — the real filter is the **Competência** ("Period") selector (month + year). Select the period matching the month/year of the NF's `data_emissao`.

`browser_snapshot` → locate the two Period **combobox** fields (month and year). Use `browser_select_option` to select the NF's month and year.

Examine the resulting "Histórico de notas" ("Invoice history"):
- If an NF with the same **number** (and series, if any) from the same provider appears:
  - Report: "NF already registered (CNPJ `<cnpj>`, series `<serie>`, no. `<numero>`)."
  - `browser_close`
  - End the command.
- If it shows "Nenhuma nota tomada encontrada" ("No received invoice found") or none with the NF's number: proceed to step 4.

> **Note:** this check is repeated in step 6 (immediately before Register) to cover the time window during the confirmation pause (TOCTOU).

## Step 4 — Resolve provider

`browser_snapshot` — check where you are before navigating.

```
browser_navigate → https://app.contabilizei.com.br/painel-de-controle/#/nota-tomada/prestadores
browser_snapshot
```

Dismiss the modals (sub-step from step 2). The screen has a "Busque pelo nome ou CNPJ do prestador" ("Search by provider name or CNPJ") field and the list of already-registered providers.

Search for the provider by the extracted CNPJ (or locate it in the list).

- **Exists:** click the provider item. The URL changes to `.../nota-tomada/registrar` with CNPJ and company name already filled in at the top of the form. Confirm with `browser_snapshot`.
- **Doesn't exist:** click "Cadastrar novo prestador" ("Register new provider") and fill in CNPJ and company name in the corresponding fields (identify them by the labels/placeholders in the snapshot).

## Step 5 — Fill in the form

`browser_snapshot` — confirm you're on the registration form and dismiss the modals (sub-step from step 2).

Identify the fields from the snapshot (real labels/placeholders). The `data-testid` values below were observed and serve as a **hint/fallback** — confirm in the snapshot before using them:

- **Issue date** (`input-emission-date`, placeholder `00/00/0000`): value of `data_emissao` in `DD/MM/AAAA` format.
- **Number** (`input-invoice-number`): value of `numero`.
- **Series** (`input-serial-number`): **the field only accepts digits.** If `serie` is non-numeric (e.g., "E"), **leave it blank** — don't try to type the letter (it's silently rejected).
- **Value** (`input-grade-value`, id `input-valor-nota`): a **masked** field (`R$ 0,00`). `browser_fill_form`/`browser_type` don't work. Inject via JS using the native setter, passing only the digits with a decimal comma (e.g., `10,99`):
  ```
  browser_evaluate:
  () => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const el = document.querySelector('[data-testid="input-grade-value"]');
    set.call(el, ''); el.dispatchEvent(new Event('input', {bubbles:true}));
    set.call(el, '10,99');  // replace with the actual value
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
    return el.value;  // should return "R$ 10,99"
  }
  ```
- **Description** (`Descrição do serviço*`): `descricao` truncated to 250 chars.

**Service type** (`select-list-services`) **and Category** (`select-list-categories`): read the actual options from the `<select>` in the snapshot. Case-fold and compare against `descricao` and `codigo_servico`. If there's a reasonable match, select it with `browser_select_option`. If ambiguous, note the top-3 options to show in the confirmation (step 6). Category usually has few options (e.g., "Outras" / "Other", "Sistemas de Pagamento" / "Payment Systems") — choose "Outras" ("Other") if none is specific.

## Step 6 — Confirm before registering

**Re-check for duplicates** (TOCTOU): repeat the search from step 3. If the NF now appears → report duplicate and end.

`browser_snapshot` — check the form's state. If the session expired or the form is in an unexpected state: re-authenticate (step 2) and re-fill (steps 4–5). **Never submit over a stale form.**

Before confirming, **read back the actual values from the form** (via `browser_evaluate`, reading the fields' `.value`) — confirm that what will be submitted matches what was extracted.

Use `AskUserQuestion`. **The full summary goes in the question text itself (`question`)** — not just in `annotations`/`description`. The user needs to see all fields directly in the question card. Include, one per line:

```
Confirm registering this received NF?

• CNPJ:          <formatted CNPJ XX.XXX.XXX/XXXX-XX>
• Provider:      <razao_social>
• Issue date:    <data_emissao>
• Number:        <numero>   Series: <serie or —>
• Value:         R$ <X,XXX.XX>
• Service type:  <selected>
• Category:      <selected>
• Description:   <descricao>
• Period:        <MM/YYYY> (<current month — no reopening | past month — WARNING: reopening/fee>)

⚠️ Fields extracted via regex (review): [list of fragile fields, or "none"]
```

Options:
- "Confirm and register"
- "Fix a field"
- "Abort"

If "Fix a field": use `AskUserQuestion` to ask which field and the new value, update it in the form, and return to the start of this step.

If "Abort": `browser_close`, end reporting "Registration aborted by the user."

## Step 7 — Register and verify

Click the *Registrar nota* ("Register invoice") button (identify it from the snapshot — it stays disabled until the form is valid).

`browser_snapshot` → check the result.

### "Reabertura do mês contábil" ("Reopening the accounting month") dialog

When registering an NF for an **already-closed period** (a past accounting month), Contabilizei opens the **"Reabertura do mês contábil"** dialog — it informs a **one-time fee** (≈R$ 21,90 Simples / R$ 54,90 Lucro Presumido per month out of deadline) and **shifts to the user** the responsibility for fines/interest. Buttons: "Cancelar" ("Cancel") and "Aceitar reabertura e registrar nota" ("Accept reopening and register invoice").

> **Don't confuse DOM presence with active.** This dialog is a Vue component that appears in the snapshot **mounted but self-hides** (via a CSS transition) for an NF in the current month (open period). An **instantaneous** visibility check gives a **false positive** — it catches the modal mid-mount with `opacity` transitioning (`offsetParent` still truthy, `opacity` going 1→0).
>
> So: when entering `/registrar`, **wait for it to settle** (`browser_wait_for {time: 2}`) **before** checking. Then confirm visibility via `data-testid="modal-reopening-month-accounting"`:
>
> ```
> browser_evaluate:
> () => {
>   const el = document.querySelector('[data-testid="modal-reopening-month-accounting"]');
>   if (!el) return { active: false };
>   const cs = getComputedStyle(el);
>   return { active: !!el.offsetParent && cs.opacity !== '0' && cs.visibility !== 'hidden' };
> }
> ```
>
> If `active === false`, **ignore the dialog** — the period is on time, registration proceeds normally without a fee (the app itself even confirms: "prazo máximo é dia 05 do mês seguinte" / "the deadline is the 5th of the following month").

If the dialog is **actually visible** (NF from a past month):
- Use `AskUserQuestion` to surface to the user: the exact fee shown + the shift of responsibility for fines/interest.
- Only click "Aceitar reabertura e registrar nota" ("Accept reopening and register invoice") with explicit consent.
- If "Abort": click "Cancelar" ("Cancel"), `browser_close`, end.

After resolving the dialog (or if it didn't appear), `browser_snapshot` → check the result:
- **Success** (redirected to the listing or shows a confirmation): report "NF registered successfully."
- **Visible error on the form**: report the error, offer to fix or abort via `AskUserQuestion`.
- **Ambiguous state** (snapshot neither confirms nor denies): report "Inconclusive result — check the Contabilizei listing to confirm whether the NF was registered."

`browser_close`

Final report in one line: `✅ NF registered` / `ℹ️ Already existed` / `⚠️ Aborted` / `❓ Inconclusive`.
