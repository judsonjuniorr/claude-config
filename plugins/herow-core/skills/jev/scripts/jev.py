#!/usr/bin/env python3
"""Ask Jev (typesafe/jev-1.13, OpenRouter Decisions) typed questions about texts.
Input: {"items": [{"id", "state", "questions"?}], "questions": {...}, "model"?}; output: {"results", "errors", "totals"}."""

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "https://openrouter.ai/api/alpha/decisions"
GENERATION_URL = "https://openrouter.ai/api/v1/generation?id="
DEFAULT_MODEL = "typesafe/jev-1.13"
KEY_SERVICE = "openrouter-api-key"

# Order matters: labelled agência/conta first, then document numbers, then any leftover long digit run.
BR_PATTERNS = [
    re.compile(r"(?i)\b(ag[eê]ncia|ag\.?)\s*:?\s*\d[\d.\-]*"),
    re.compile(r"(?i)\b(conta|c/c|cc)\s*:?\s*\d[\d.\-]*"),
    # CPF/CNPJ full, masked, or cut short by a PDF line wrap (e.g. "82.951.310").
    re.compile(
        r"[\d•*xX]{2,3}\.[\d•*xX]{3}\.[\d•*xX]{3}(?:/[\d•*xX]{4})?(?:-[\d•*xX]{2})?"
    ),
    re.compile(r"\b(?:\d{4}[ .]?){10}\d{4}\b"),
    re.compile(r"\d{9,}"),
]


def redact_br(value):
    if isinstance(value, str):
        for p in BR_PATTERNS:
            value = p.sub("[redacted]", value)
        return value
    if isinstance(value, list):
        return [redact_br(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_br(v) for k, v in value.items()}
    return value


def checked_key(key, source):
    # http.client rejects CR/LF in headers with a ValueError that echoes the whole header value.
    if re.fullmatch(r"[\x21-\x7e]+", key):
        return key
    sys.exit(
        f"jev unavailable: the OpenRouter key from {source} contains whitespace or control characters. "
        f'Fix: re-store it in your own terminal with `security add-generic-password -U -a "$USER" -s {KEY_SERVICE} -w` '
        "(macOS) or re-export OPENROUTER_API_KEY as a single token."
    )


def scrub(text, key):
    return text.replace(key, "[redacted]") if key and isinstance(text, str) else text


def read_key():
    """Keychain (macOS) first, then OPENROUTER_API_KEY; a missing, hung or empty source falls through."""
    try:
        timeout = float(os.environ.get("JEV_KEY_TIMEOUT") or 5)
    except ValueError:
        timeout = 5.0
    try:
        r = subprocess.run(
            [
                os.environ.get("JEV_SECURITY_BIN") or "security",
                "find-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                KEY_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        if r.returncode == 0 and r.stdout.strip():
            return checked_key(r.stdout.strip(), "Keychain")
    except (OSError, subprocess.SubprocessError):
        pass
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if key:
        return checked_key(key, "OPENROUTER_API_KEY")
    sys.exit(
        "jev unavailable: no OpenRouter key found. Fix: create one at https://openrouter.ai/keys, then in your own "
        f'terminal run `security add-generic-password -a "$USER" -s {KEY_SERVICE} -w` (macOS) '
        "or export OPENROUTER_API_KEY in your shell profile (other systems)."
    )


def http(method, url, key, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"{type(e).__name__}: {e}"


def lookup_cost(key, gen_id):
    # Generation stats can lag a moment behind the response.
    for _ in range(3):
        status, text = http("GET", GENERATION_URL + gen_id, key, timeout=20)
        if status == 200:
            cost = (json.loads(text).get("data") or {}).get("total_cost")
            if cost is not None:
                return cost
        time.sleep(1)
    return None


def uncertain(answers, conf, band):
    out = []
    for name, a in answers.items():
        if a.get("type") == "noul":
            if band[0] <= a["noul"] <= band[1]:
                out.append(name)
        elif a.get("confidence") is None or a["confidence"] < conf:
            out.append(name)
    return out


def redact_questions(questions):
    # Only criteria values: answers echo the option keys verbatim.
    out = {}
    for name, q in questions.items():
        c = q.get("criteria")
        if isinstance(c, dict):
            c = {k: redact_br(v) for k, v in c.items()}
        elif isinstance(c, list):
            c = redact_br(c)
        out[name] = {**q, "criteria": c}
    return out


def ask(item, body, key, args):
    try:
        return _ask(item, body, key, args)
    except Exception as e:
        return None, {
            "item_id": item.get("id"),
            "status": "exception",
            "body": scrub(f"{type(e).__name__}: {e}", key),
            "request": {"method": "POST", "url": URL, "body": body},
        }


def _ask(item, body, key, args):
    t0 = time.perf_counter()
    status, text = http("POST", URL, key, body, args.timeout)
    ms = round((time.perf_counter() - t0) * 1000)
    if status != 200:
        return None, {
            "item_id": item.get("id"),
            "status": status,
            "body": scrub(text, key),
            "request": {"method": "POST", "url": URL, "body": body},
        }
    resp = json.loads(text)
    cost = (resp.get("usage") or {}).get("cost")
    cost_source = "usage.cost"
    if cost is None and resp.get("id"):
        cost, cost_source = lookup_cost(key, resp["id"]), "generation"
    if cost is None:
        cost_source = None
    answers = resp.get("answers", {})
    return {
        "id": item.get("id"),
        "answers": answers,
        "uncertain": uncertain(answers, args.conf, args.noul_band),
        "ms": ms,
        "cost": cost,
        "cost_source": cost_source,
        "model": resp.get("model"),
        "generation_id": resp.get("id"),
        "usage": resp.get("usage"),
    }, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", nargs="?", help="JSON file (default: stdin)")
    p.add_argument(
        "--conf", type=float, default=0.7, help="choice/score confidence floor"
    )
    p.add_argument(
        "--noul-band", type=float, nargs=2, default=[0.3, 0.7], metavar=("LO", "HI")
    )
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--workers", type=int, default=8, help="concurrent requests")
    p.add_argument(
        "--redact-br",
        action="store_true",
        help="scrub CPF/CNPJ, chave, agência/conta and long digit runs from state",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print outgoing bodies and exit; no key read, no request",
    )
    args = p.parse_args()

    spec = json.load(open(args.input) if args.input else sys.stdin)
    model = spec.get("model", DEFAULT_MODEL)
    items = spec["items"]
    bodies = []
    for i in items:
        questions = i.get("questions") or spec["questions"]
        bodies.append(
            {
                "model": model,
                "state": redact_br(i["state"]) if args.redact_br else i["state"],
                "questions": redact_questions(questions)
                if args.redact_br
                else questions,
            }
        )

    if args.dry_run:
        print(json.dumps({"dry_run": bodies}, indent=2, ensure_ascii=False))
        return

    key = read_key()
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        outcomes = list(
            pool.map(lambda ib: ask(ib[0], ib[1], key, args), zip(items, bodies))
        )
    wall_ms = round((time.perf_counter() - t0) * 1000)

    # Failed items don't discard the rest: those were already billed.
    results = [r for r, _ in outcomes if r]
    errors = [e for _, e in outcomes if e]
    cost_missing = any(r["cost"] is None for r in results)
    print(
        json.dumps(
            {
                "results": results,
                "errors": errors,
                "totals": {
                    "n": len(results),
                    "failed": len(errors),
                    "ms": sum(r["ms"] for r in results),
                    "wall_ms": wall_ms,
                    "cost": None if cost_missing else sum(r["cost"] for r in results),
                    "cost_note": "cost not reported for at least one item"
                    if cost_missing
                    else None,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
