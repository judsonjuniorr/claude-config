# organizze — market research & per-account forecast (Steps 5.5–5.6)

On-demand resource for `/finance:organizze`. Read and follow after Step 5 (base prompt
rendered) and before Step 6 (delegate). Step 5.5 fires parallel market research and renders
the prompt with `--research-dir`; Step 5.6 appends the per-account forecast block. The
GLOBAL RULE (ask via `AskUserQuestion`) and the main command's `**Absolute paths**` apply.

## Step 5.5 — Parallel market research (with cache)

Instead of `financial-analyst` running 3 `WebSearch` calls sequentially within its own context (slow and consumes its tokens), **fire `search-specialist` in parallel now** and save the reports to `$RESEARCH_DIR/<category>.md` — `analyze.py` injects them as a "Market research (PRE-COLLECTED)" block.

Before firing a new agent, **check the cache** (default TTL 14 days): if a recent report for that category already exists in any `~/finance/organizze/research/<TS>/<category>.md`, reuse it by copying to the current `$RESEARCH_DIR`.

1. List the target categories + city from the profile (pipe-delimited output):
   ```bash
   TARGETS=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/analyze.py --snapshot "$SNAP" --list-targets)
   echo "$TARGETS"
   ```
   Expected format, 1 record per line:
   - `profile|cidade|<city or "(no data)">`
   - `target|<category name>|<total_cents>|<median_6m_cents>|<top5 transactions separated by ';'>`

2. Parse:
   - `CITY` = value from the `profile|cidade|...` line (use the literal `"the user's city"` if it's `(no data)`).
   - Each `target|...` line becomes an entry with `name`, `total_cents`, `top_txs`.

3. **For each target, check the cache first** (TTL 14d configurable, category-level cache). If `--refresh` was passed in `$ARGUMENTS`, pass `--max-age-days 0` to force re-research of all categories. Split into two groups: `CACHED` and `MISSING`:
   ```bash
   for cat in <list of names>; do
     CACHED_PATH=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/analyze.py \
       --research-cache-lookup "$cat" --max-age-days 14)
     if [ -n "$CACHED_PATH" ]; then
       cp "$CACHED_PATH" "$RESEARCH_DIR/$cat.md"
       echo "info|cache-hit|$cat|$CACHED_PATH" >&2
     else
       echo "info|cache-miss|$cat" >&2
       # add $cat to the MISSING list
     fi
   done
   ```
   Expected output: each category becomes `cache-hit` (report copied, no agent fired) or `cache-miss` (needs research).

   To force re-research of everything (ignore cache), use `--max-age-days 0`. For a longer TTL (e.g.: 30 days), `--max-age-days 30`.

4. If ALL are cache-hits, skip to Step 6 (render prompt and invoke analyst — no agents). Otherwise, **fire ALL pending agents IN A SINGLE MESSAGE with multiple parallel `Agent` tool calls** (1 per cache-miss category). DO NOT run in series. Configuration per call:
   - `subagent_type`: `search-specialist`
   - `description`: `Market research: <category>`
   - `prompt`:
     ```
     Research cheaper alternatives for spending in the category "<CATEGORY NAME>" considering the user lives in "<CITY>".
     
     Current monthly spending in this category: R$ <formatted total>.
     6-month median: R$ <median>.
     Top 5 transactions this month in this category:
       - <transaction 1>
       - <transaction 2>
       - ... (up to 5)
     
     Goal: find 3-5 legitimate and cheaper alternatives, viable for the user. Focus on comparable quality (don't compare a car to a bicycle). For each:
       - Name of the option
       - Current price (R$/month or R$/unit, as applicable)
       - Source URL (prioritize official sites — comparison sites like Buscapé/Zoom OK if official site has no price)
       - Differentiator / catch / restriction the user should know (e.g.: limited coverage, loyalty requirement, perceived quality)
     
     Required output:
       1. 1-paragraph summary (most recommended alternative + why).
       2. List of 3-5 alternatives in the format above.
       3. Table of consulted sources (URL, date, authority H/M/L).
     
     If nothing useful is found (category too specific or no public alternative), respond only "(no alternative found)" and justify in 1 line.
     ```

5. After each agent returns, save the report (raw text returned) in a separate file:
   ```bash
   # For each category with cache-miss, write the report returned by the agent to:
   # $RESEARCH_DIR/<category_name>.md
   # (keep the exact category name — analyze.py uses the file stem as header
   # and also for future cache lookups)
   ```

6. If ALL pending categories fail (rare), the files are missing from `$RESEARCH_DIR` — `analyze.py` injects only the ones that exist, and the analyst's rule 14 directs using WebSearch as fallback for the rest.

7. Now render the prompt **with** the `--research-dir` and `--snapshot-sanitized`:
   ```bash
   SNAP=$(ls -t ~/finance/organizze/snapshots/*.json 2>/dev/null | grep -v '\.bak$' | head -1)
   SNAP_SAN=~/finance/organizze/snapshot_sanitized.json
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/analyze.py \
     --snapshot "$SNAP" --snapshot-sanitized "$SNAP_SAN" \
     --research-dir "$RESEARCH_DIR" --out "$PROMPT_FILE"
   ```

## Step 5.4 — IPCA fetch (BCB API)

Fetch the latest IPCA (Brazilian CPI) for use in the analysis:

```bash
IPCA=$(python3 - <<'PY'
import urllib.request, json, sys
try:
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"
    with urllib.request.urlopen(url, timeout=5) as r:
        data = json.loads(r.read())[0]
        print(f"{data['data']}={data['valor']}%")
except Exception:
    print("null")
PY
)
echo "info|ipca|$IPCA" >&2
```

If the result is `null` (API unavailable or timeout), continue without it — do not block the analysis. If fetched, append to `$PROMPT_FILE`:
```bash
if [ "$IPCA" != "null" ]; then
  echo "" >> "$PROMPT_FILE"
  echo "## Macro context" >> "$PROMPT_FILE"
  echo "- IPCA (latest): $IPCA (source: BCB, fetched live)" >> "$PROMPT_FILE"
fi
```

## Step 5.6 — Balance and forecast per account (base for the transfer plan)

`balance_on.py` is the factual source for transfer recommendations: for a given date, it returns per main account (and per caixinha, in a separate section) the **current balance**, the **forecast (Organizze)** = balance + unpaid future transactions + invoices due by that date in the paying account (matches the app's "previsto" widget), and the **forecast with overdue items** = also sums past-due unpaid transactions. Generate the block for key dates and **append to `$PROMPT_FILE`** before delegating.

1. Define target dates: end of current month, +30d, +60d and end of the horizon (use the same `--future-days` as Step 3 — so no date exceeds the snapshot range). E.g.:
   ```bash
   FUTURE_DAYS=<N or 90>   # identical to --future-days in Step 3
   DATES="$(FUTURE_DAYS="$FUTURE_DAYS" python3 - <<'PY'
import datetime as dt, calendar, os
t = dt.date.today()
horizon = int(os.environ.get("FUTURE_DAYS", "90"))
def eom(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])
cands = {eom(t), t + dt.timedelta(days=30), t + dt.timedelta(days=60),
         t + dt.timedelta(days=horizon)}
ds = sorted(d.isoformat() for d in cands if d <= t + dt.timedelta(days=horizon))
print(" ".join(ds))
PY
)"
   ```

2. Append the tables (one per date) to the prompt:
   ```bash
   {
     echo
     echo "# Balance and forecast per account (generated by balance_on.py — DO NOT invent numbers)"
     echo "Use as the basis for the **Transfer and savings plan**: for each date, compare the **Forecast (Organizze)** column across main accounts. Where an account has a negative forecast (or below CASHFLOW_THRESHOLD_CENTS), propose moving the slack from another MAIN account with a positive forecast on the same date — stating origin → destination, amount and date. Caixinhas/reserves are the LAST resort: only suggest using them when NO main account has enough slack to cover the shortfall; when doing so, explicitly label it 'emergency use of reserve' and quantify how much of the reserve would be consumed. Use **Forecast with overdue** to see the real impact of past-due transactions. If not even reserves can cover it, flag the shortfall and suggest adjustments (defer/cut an unpaid expense, accelerate income)."
     for D in $DATES; do
       echo
       python3 ${CLAUDE_PLUGIN_ROOT}/scripts/organizze/balance_on.py \
         --snapshot "$SNAP" --date "$D"
     done
   } >> "$PROMPT_FILE"
   ```

3. If the warning `⚠️ Cards WITHOUT paying account` appears, run Step 2.7 (`config.py card-account ...`) and re-run — without the mapping, invoices won't enter the forecast and the transfer plan will be underestimated.
