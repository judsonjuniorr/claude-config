#!/usr/bin/env python3
"""User personal profile (provider-agnostic).

Stores structured data about the user so that financial analyses are
personalized: age, occupation, income, family, housing, city,
risk tolerance, habits. Each time `/finance:organizze` runs, still-empty
required fields are asked via AskUserQuestion in the main chat.

File: ~/finance/profile.md (readable markdown, `key: value` format per line).

Usage:
  profile.py get [<key>]              # read all or a single field
  profile.py set <key> <value>        # write/update a field
  profile.py missing                  # list required keys that are still empty
  profile.py render                   # markdown block ready to inject into prompt
  profile.py mark-skip                # write timestamp to last_skip (silences for 7d)
  profile.py should-ask               # exit 0 if should ask now; 1 if silenced
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _storage import PROFILE, migrate_legacy  # noqa: E402

REQUIRED_KEYS = [
    "idade",
    "profissao",
    "renda_liquida_mensal_cents",
    "estado_civil",
    "dependentes",
    "moradia_tipo",
    "moradia_custo_cents",
    "cidade",
    "tolerancia_risco",
]
OPTIONAL_KEYS = ["habitos", "objetivo_principal"]
META_KEYS = ["updated", "last_skip"]
ALL_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS + META_KEYS

ENUM_VALUES = {
    "estado_civil": {"solteiro", "relacionamento", "casado", "divorciado", "viuvo"},
    "moradia_tipo": {
        "propria_quitada", "propria_financiada", "alugada", "cedida", "outra",
    },
    "tolerancia_risco": {"conservador", "moderado", "agressivo"},
}
INT_KEYS = {"idade", "renda_liquida_mensal_cents", "moradia_custo_cents"}

LINE_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*?)\s*$")


def _load() -> dict[str, str]:
    if not PROFILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in PROFILE.read_text().splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        out[m.group(1)] = m.group(2)
    return out


def _save(data: dict[str, str]) -> None:
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = [
        "# User profile",
        "# Manually editable. One field per line, format `key: value`. "
        "Do not use multiple lines.",
        "# Empty fields will be re-asked in /finance:organizze. To silence "
        "for 7 days, run `profile.py mark-skip`.",
        "",
    ]
    data["updated"] = dt.date.today().isoformat()
    ordered = REQUIRED_KEYS + OPTIONAL_KEYS + META_KEYS
    for k in ordered:
        if k in data and data[k] != "":
            out.append(f"{k}: {data[k]}")
    PROFILE.write_text("\n".join(out) + "\n")
    PROFILE.chmod(0o600)


def _brl(c: int | None) -> str:
    if c is None:
        return "(no data)"
    v = abs(int(c)) / 100.0
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _validate(key: str, value: str) -> str | None:
    """Returns error as string or None if OK."""
    if key in INT_KEYS:
        try:
            int(value)
        except ValueError:
            return f"field `{key}` requires an integer (cents for monetary values)"
    if key in ENUM_VALUES:
        if value not in ENUM_VALUES[key]:
            return f"field `{key}` accepts: {sorted(ENUM_VALUES[key])}"
    return None


def cmd_get(args) -> int:
    data = _load()
    if args.key:
        if args.key not in data:
            print("", end="")
            return 0
        print(data[args.key])
        return 0
    if not data:
        print("(profile is empty)", file=sys.stderr)
        return 0
    for k in REQUIRED_KEYS + OPTIONAL_KEYS:
        if k in data:
            print(f"{k}: {data[k]}")
    return 0


def cmd_set(args) -> int:
    key = args.key.strip()
    value = args.value.strip()
    if key not in ALL_KEYS:
        print(f"err|bad-key|{key} — accepted: {ALL_KEYS}", file=sys.stderr)
        return 1
    err = _validate(key, value)
    if err:
        print(f"err|bad-value|{err}", file=sys.stderr)
        return 1
    data = _load()
    if value == "":
        data.pop(key, None)
    else:
        data[key] = value
    # any field change clears the previous silence (renewed engagement)
    if key not in META_KEYS and "last_skip" in data:
        data.pop("last_skip", None)
    _save(data)
    print(f"ok|set|{key}={value}|{PROFILE}")
    return 0


def cmd_missing(args) -> int:
    data = _load()
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    for k in missing:
        print(k)
    return 0


def cmd_mark_skip(args) -> int:
    data = _load()
    data["last_skip"] = dt.date.today().isoformat()
    _save(data)
    print(f"ok|skip-marked|{data['last_skip']}")
    return 0


def cmd_should_ask(args) -> int:
    """Exit 0 = ask; 1 = silence.
    Silences if ALL required fields are filled OR if last_skip <7d and there are still missing fields."""
    data = _load()
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if not missing:
        return 1  # profile complete, nothing to ask
    last_skip = data.get("last_skip")
    if last_skip:
        try:
            d = dt.date.fromisoformat(last_skip)
            if (dt.date.today() - d).days < 7:
                return 1  # silenced
        except ValueError:
            pass
    return 0  # ask


def cmd_render(args) -> int:
    data = _load()
    print("# User profile (PERSONAL CONTEXT — calibrate recommendations)")
    print()
    print("Use this data to personalize analyses (age range, income, "
          "dependents, housing cost, city, risk tolerance). "
          "**Every recommendation must reference at least one field here.** "
          "Fields marked `(no data)` mean the user has not yet provided them — "
          "if any is critical for your recommendation, emit a "
          "`[QUESTION]` in the final block of the report.")
    print()

    idade = data.get("idade") or "(no data)"
    print(f"- **Age**: {idade}{' years' if idade != '(no data)' else ''}")
    print(f"- **Occupation**: {data.get('profissao') or '(no data)'}")
    renda = data.get("renda_liquida_mensal_cents")
    print(f"- **Monthly net income**: {_brl(int(renda)) if renda else '(no data)'}")
    print(f"- **Marital status**: {data.get('estado_civil') or '(no data)'}")
    print(f"- **Dependents**: {data.get('dependentes') or '(no data)'}")
    moradia = data.get("moradia_tipo") or "(no data)"
    custo = data.get("moradia_custo_cents")
    custo_str = _brl(int(custo)) if custo else "(no data)"
    print(f"- **Housing**: {moradia} — cost {custo_str}/month")
    print(f"- **City**: {data.get('cidade') or '(no data)'} "
          f"(use when looking up local prices/market alternatives)")
    print(f"- **Risk tolerance**: {data.get('tolerancia_risco') or '(no data)'} "
          f"(use to choose avalanche vs snowball for debt payoff)")
    if data.get("habitos"):
        print(f"- **Habits**: {data['habitos']}")
    if data.get("objetivo_principal"):
        print(f"- **Main short-term goal**: {data['objetivo_principal']}")
    if data.get("updated"):
        print(f"\n_(Last updated: {data['updated']})_")
    return 0


def main() -> int:
    migrate_legacy()

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get")
    g.add_argument("key", nargs="?", default=None)
    g.set_defaults(func=cmd_get)

    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(func=cmd_set)

    m = sub.add_parser("missing")
    m.set_defaults(func=cmd_missing)

    r = sub.add_parser("render")
    r.set_defaults(func=cmd_render)

    sk = sub.add_parser("mark-skip")
    sk.set_defaults(func=cmd_mark_skip)

    sa = sub.add_parser("should-ask")
    sa.set_defaults(func=cmd_should_ask)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
