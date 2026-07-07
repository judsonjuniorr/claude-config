"""Read path over the official `organizze` CLI (github.com/organizze/agent-tools).

The CLI wraps the same REST v2 (`api.organizze.com.br/rest/v2`) our `.auth` token
already authorizes — HTTP Basic auth, email + API key — so no separate login or
OAuth is needed. We just forward the credentials already on disk as env vars and
call `organizze --json <args...>`.

Why the CLI instead of hand-rolled urllib: it's officially maintained, auto-
paginates (`transactions list --all`), and exposes REAL account balances
(`accounts get <id>` -> balance) — the old code had to reconstruct balances by
summing 5 years of transactions because GET /accounts omits them.

Writes are NOT routed here. create.py keeps POSTing through _http.py because the
CLI's write surface is a strict subset of what create.py needs (no
credit_card_invoice_id, no installments_attributes/recurrence_attributes, no
transfers create).

Error protocol (matches _http.py): every failure exits with `err|<code>|<detail>`
on stderr, mapped from the CLI's documented exit codes:
  0 ok · 1 generic · 2 usage · 3 auth · 4 not-found · 5 validation(422) ·
  6 rate-limited(429) · 7 network
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import AUTH  # noqa: E402

BIN = "organizze"

_EXIT_CODE_ERR = {
    1: "generic",
    2: "usage",
    3: "auth",
    4: "not-found",
    5: "http-422",
    6: "rate-limited",
    7: "network",
}


def load_auth() -> tuple[str, str, str]:
    """Return (email, token, user_agent) from ~/finance/organizze/.auth.

    Lifted verbatim from _http.py so the CLI path shares one auth contract.
    """
    if not AUTH.exists():
        sys.exit("err|no-auth|run setup_auth.sh first")
    env: dict[str, str] = {}
    for line in AUTH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    try:
        return (
            env["ORGANIZZE_EMAIL"],
            env["ORGANIZZE_TOKEN"],
            env["ORGANIZZE_USER_AGENT"],
        )
    except KeyError as e:
        sys.exit(f"err|bad-auth|missing {e}")


def _cli_env(email: str, token: str, ua: str) -> dict[str, str]:
    """Env for the CLI subprocess: our API token becomes ORGANIZZE_API_KEY."""
    import os

    env = dict(os.environ)
    env["ORGANIZZE_EMAIL"] = email
    env["ORGANIZZE_API_KEY"] = token
    env["ORGANIZZE_USER_AGENT"] = ua
    return env


def cli_json(args: list[str], auth: tuple[str, str, str]) -> object:
    """Run `organizze --json <args...>` and return the parsed JSON stdout.

    auth = (email, token, user_agent), typically from load_auth().
    """
    if shutil.which(BIN) is None:
        sys.exit(
            f"err|no-cli|{BIN} not found on PATH — install via scripts/setup/ensure-deps.sh"
        )
    email, token, ua = auth
    try:
        proc = subprocess.run(
            [BIN, "--json", *args],
            env=_cli_env(email, token, ua),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        sys.exit(f"err|network|{BIN} timed out: {' '.join(args)}")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        code = _EXIT_CODE_ERR.get(proc.returncode, f"exit-{proc.returncode}")
        sys.exit(f"err|{code}|{' '.join(args)} {detail}")

    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as e:
        sys.exit(f"err|bad-json|{BIN} {' '.join(args)}: {e}")


# --- typed helpers used by pull.py / create.py ------------------------------


def accounts_list(auth: tuple[str, str, str]) -> list[dict]:
    data = cli_json(["accounts", "list"], auth)
    return data if isinstance(data, list) else []


def _parse_brl_cents(value: str) -> int:
    """Parse a formatted BRL string ('R$ 1.234,56', 'R$ -50,00') to integer cents.

    Per the REST v2 OpenAPI spec, GET /accounts/{id}'s `balance` is a formatted
    string (unlike every other money field in the API, which is integer cents) —
    strip the currency symbol/thousands separators, keep sign and decimal comma.
    """
    negative = "-" in value
    digits = re.sub(r"[^\d,]", "", value)
    if not digits:
        return 0
    reais_part, _, cents_part = digits.partition(",")
    reais_part = reais_part or "0"
    cents_part = (cents_part + "00")[:2] or "00"
    cents = int(reais_part) * 100 + int(cents_part)
    return -cents if negative else cents


def account_get(account_id: int, auth: tuple[str, str, str]) -> dict:
    data = cli_json(["accounts", "get", str(account_id)], auth)
    if not isinstance(data, dict):
        return {}
    data = dict(data)
    if isinstance(data.get("balance"), str):
        data["balance"] = _parse_brl_cents(data["balance"])
    return data


def categories_list(auth: tuple[str, str, str]) -> list[dict]:
    data = cli_json(["categories", "list"], auth)
    return data if isinstance(data, list) else []


def credit_cards_list(auth: tuple[str, str, str]) -> list[dict]:
    data = cli_json(["credit-cards", "list"], auth)
    return data if isinstance(data, list) else []


def invoices_list(
    credit_card_id: int,
    since: str | None,
    until: str | None,
    auth: tuple[str, str, str],
) -> list[dict]:
    args = ["invoices", "list", str(credit_card_id)]
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    data = cli_json(args, auth)
    return data if isinstance(data, list) else []


def transactions_list(
    since: str | None,
    until: str | None,
    auth: tuple[str, str, str],
    all_pages: bool = True,
) -> list[dict]:
    args = ["transactions", "list"]
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    if all_pages:
        args += ["--all"]
    data = cli_json(args, auth)
    return data if isinstance(data, list) else []


def budgets(year: int, month: int, auth: tuple[str, str, str]) -> list[dict]:
    data = cli_json(["budgets", "--year", str(year), "--month", str(month)], auth)
    return data if isinstance(data, list) else []
