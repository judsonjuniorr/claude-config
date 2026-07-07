"""HTTP write path for Organizze REST v2 (stdlib only).

Reads now go through the official `organizze` CLI (see _cli.py) — official
transport, auto-pagination, real balances. This module is what's left: the
actual POSTs. The CLI's write surface is a strict subset of what create.py
needs (no credit_card_invoice_id, no installments_attributes/
recurrence_attributes, no transfers create), so writes stay on hand-rolled
urllib against the REST API directly.

Error protocol (matches _cli.py): every failure exits with `err|<code>|<detail>`
on stderr. For http_post, `err|http-422|...` is the EXPECTED validation channel
(Organizze surfaces field errors as 422), so callers may catch SystemExit to
turn it into an AskUserQuestion instead of dying.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request

API = "https://api.organizze.com.br/rest/v2"


def _auth_headers(email: str, token: str, ua: str) -> dict[str, str]:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "User-Agent": ua,
        "Accept": "application/json",
    }


def http_post(path: str, body: dict, email: str, token: str, ua: str) -> object:
    """POST JSON to {API}{path}. Returns parsed JSON (dict) on 2xx.

    Same auth/UA as _cli.py's reads plus Content-Type: application/json.
    `err|http-422|...` is the expected validation channel (Organizze returns
    422 with a field-error body the caller surfaces verbatim).
    """
    url = f"{API}{path}"
    headers = _auth_headers(email, token, ua)
    headers["Content-Type"] = "application/json"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https API host)
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        sys.exit(f"err|http-{e.code}|{path} {body}")
    except urllib.error.URLError as e:
        sys.exit(f"err|network|{e.reason}")
