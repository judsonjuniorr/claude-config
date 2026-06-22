#!/usr/bin/env python3
"""Read-only orchestrator for /herow-core:doctor.

Runs security.py, tokens.py, hygiene.py (dry-run), collects their JSONL output,
and prints one consolidated, pretty-printed report:

  {"summary": {"fail": N, "warn": N, "pass": N}, "checks": [ {...}, ... ]}

This script NEVER applies a fix — remediation is per-check via each finding's
`fix_cmd`. Stdlib only. Exit code 0 even when checks fail.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _doctor import fatal  # noqa: E402

SUBSCRIPTS = ["security.py", "tokens.py", "hygiene.py"]


def run_subscript(name: str) -> list[dict]:
    script = pathlib.Path(__file__).resolve().parent / name
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    if r.stderr.strip():
        sys.stderr.write(r.stderr if r.stderr.endswith("\n") else r.stderr + "\n")
    checks: list[dict] = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            checks.append(json.loads(line))
        except json.JSONDecodeError:
            fatal("bad-line", f"{name}: {line[:120]}")
    return checks


def aggregate(checks: list[dict]) -> dict:
    summary = {"fail": 0, "warn": 0, "pass": 0}
    for c in checks:
        st = c.get("status")
        if st in summary:
            summary[st] += 1
    return {"summary": summary, "checks": checks}


def main(argv=None) -> int:
    all_checks: list[dict] = []
    for name in SUBSCRIPTS:
        all_checks.extend(run_subscript(name))
    print(json.dumps(aggregate(all_checks), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
