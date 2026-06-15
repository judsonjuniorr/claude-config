"""Shared HTTP + auth for Organizze REST v2 (stdlib only).

Extracted so the write path (create.py) reuses the exact auth/header contract
the read path (pull.py) already proved. pull.py/apply_budgets.py keep their
inline copies until a separate cleanup — this module is the one DRY win taken
now (see eng-review).

Error protocol (matches pull.py): every failure exits with `err|<code>|<detail>`
on stderr. For http_post, `err|http-422|...` is the EXPECTED validation channel
(Organizze surfaces field errors as 422), so callers may catch SystemExit to
turn it into an AskUserQuestion instead of dying.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import AUTH  # noqa: E402

API = "https://api.organizze.com.br/rest/v2"


def load_auth() -> tuple[str, str, str]:
    """Return (email, token, user_agent) from ~/finance/organizze/.auth.

    Lifted verbatim from pull.py so the write path shares one auth contract.
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
        return env["ORGANIZZE_EMAIL"], env["ORGANIZZE_TOKEN"], env["ORGANIZZE_USER_AGENT"]
    except KeyError as e:
        sys.exit(f"err|bad-auth|missing {e}")


def _auth_headers(email: str, token: str, ua: str) -> dict[str, str]:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "User-Agent": ua,
        "Accept": "application/json",
    }


def http_get(path: str, params: dict | None, email: str, token: str, ua: str) -> object:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{API}{path}{qs}"
    req = urllib.request.Request(url, headers=_auth_headers(email, token, ua))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https API host)
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        sys.exit(f"err|http-{e.code}|{path} {body}")
    except urllib.error.URLError as e:
        sys.exit(f"err|network|{e.reason}")


def http_post(path: str, body: dict, email: str, token: str, ua: str) -> object:
    """POST JSON to {API}{path}. Returns parsed JSON (dict) on 2xx.

    Same auth/UA as http_get plus Content-Type: application/json. Error mapping
    matches http_get, except `err|http-422|...` is the expected validation
    channel (Organizze returns 422 with a field-error body the caller surfaces
    verbatim).
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
