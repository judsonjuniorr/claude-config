#!/usr/bin/env python3
"""Sanitize Organizze snapshot for LLM consumption.

Usage:
  sanitize.py --snapshot PATH --out PATH

- Tokenizes account IDs: replaces account_id values with acct_<sha256[:8]> tokens.
  Stores mapping in ~/finance/organizze/.id-map.json for auditability.
- Strips CPF/CNPJ patterns from description fields (replaces with [PII_REMOVED]).
- Masks medical descriptions (keywords from enrichment_rules.yaml medical_keywords list)
  with [MEDICAL_EXPENSE].
- Strips account names and card names (replaces with token).
- Output: sanitized snapshot JSON (same schema, PII removed).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
import sys
from typing import Optional

SCRIPTS_DIR = pathlib.Path(__file__).parent

CPF_RE = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')
CNPJ_RE = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')


def _load_yaml_simple(path: pathlib.Path) -> dict:
    """Minimal YAML parser for simple key: value, list, and nested dict structures.

    Handles:
    - top-level scalars: key: value
    - top-level empty lists: key: []
    - indented list items: - item
    - indented dict entries: "key": "value"
    """
    if not path.exists():
        return {}

    result: dict = {}
    current_key: Optional[str] = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        if indent == 0:
            if ":" not in stripped:
                continue
            idx = stripped.index(":")
            key = stripped[:idx].strip().strip('"').strip("'")
            rest = stripped[idx + 1 :].strip()
            # Remove inline comment
            if "#" in rest:
                rest = rest[: rest.index("#")].strip()

            if rest == "" or rest == "{}":
                current_key = key
                result.setdefault(key, {})
            elif rest == "[]":
                current_key = key
                result[key] = []
            else:
                current_key = key
                val_raw = rest.strip('"').strip("'")
                try:
                    if "." in val_raw:
                        result[key] = float(val_raw)
                    else:
                        result[key] = int(val_raw)
                except ValueError:
                    result[key] = val_raw
        else:
            # Indented content under current_key
            if current_key is None:
                continue

            if stripped.startswith("- "):
                # List item
                val = stripped[2:].strip().strip('"').strip("'")
                if not isinstance(result.get(current_key), list):
                    result[current_key] = []
                result[current_key].append(val)
            elif ":" in stripped:
                # Dict entry
                idx = stripped.index(":")
                k = stripped[:idx].strip().strip('"').strip("'")
                v = stripped[idx + 1 :].strip().strip('"').strip("'")
                if not isinstance(result.get(current_key), dict):
                    result[current_key] = {}
                result[current_key][k] = v

    return result


def tokenize_account_id(account_id: int, id_map: Optional[dict] = None) -> str:
    """Return deterministic acct_<sha256[:8]> token for account_id.

    Args:
        account_id: Numeric account identifier to tokenize.
        id_map: Optional existing map (not used in computation, here for API compat).

    Returns:
        Token string like "acct_a1b2c3d4".
    """
    h = hashlib.sha256(str(account_id).encode()).hexdigest()[:8]
    return f"acct_{h}"


def strip_pii_from_text(text: str, medical_keywords: Optional[list[str]] = None) -> str:
    """Strip CPF/CNPJ patterns and optionally mask medical descriptions.

    Args:
        text: Input description text.
        medical_keywords: Case-insensitive substrings that indicate medical expense.

    Returns:
        Sanitized text with PII replaced.
    """
    if not text:
        return text
    # Medical keywords checked first (returns whole replacement)
    if medical_keywords:
        lower = text.lower()
        for kw in medical_keywords:
            if kw and kw.lower() in lower:
                return "[MEDICAL_EXPENSE]"
    # Strip CPF
    text = CPF_RE.sub("[PII_REMOVED]", text)
    # Strip CNPJ
    text = CNPJ_RE.sub("[PII_REMOVED]", text)
    return text


def sanitize_snapshot(snapshot: dict, id_map: dict) -> dict:
    """Return a sanitized deep copy of snapshot with PII removed.

    Args:
        snapshot: Raw Organizze snapshot dict.
        id_map: Mutable map of {str(account_id): token}. Updated in-place with new mappings.

    Returns:
        Sanitized snapshot dict (same schema, PII removed).
    """
    rules_path = SCRIPTS_DIR / "enrichment_rules.yaml"
    rules = _load_yaml_simple(rules_path)
    medical_keywords: list[str] = []
    mk = rules.get("medical_keywords")
    if isinstance(mk, list):
        medical_keywords = [str(k) for k in mk if k]

    result = copy.deepcopy(snapshot)

    def _get_or_create_token(numeric_id: int) -> str:
        key = str(numeric_id)
        if key not in id_map:
            id_map[key] = tokenize_account_id(numeric_id)
        return id_map[key]

    # Tokenize account names and IDs
    for acc in result.get("accounts") or []:
        aid = acc.get("id")
        if aid is not None:
            token = _get_or_create_token(int(aid))
            acc["name"] = token
            acc["id"] = token  # replace numeric id with token

    # Tokenize credit card names and IDs
    for cc in result.get("credit_cards") or []:
        cid = cc.get("id")
        if cid is not None:
            token = _get_or_create_token(int(cid))
            cc["name"] = token
            cc["id"] = token  # replace numeric id with token

    # Sanitize transactions_past
    for t in result.get("transactions_past") or []:
        aid = t.get("account_id")
        if aid is not None:
            t["account_id"] = _get_or_create_token(int(aid))
        desc = t.get("description") or ""
        t["description"] = strip_pii_from_text(desc, medical_keywords)

    # Sanitize transactions_future
    for t in result.get("transactions_future") or []:
        aid = t.get("account_id")
        if aid is not None:
            t["account_id"] = _get_or_create_token(int(aid))
        desc = t.get("description") or ""
        t["description"] = strip_pii_from_text(desc, medical_keywords)

    return result


def _load_id_map(map_path: pathlib.Path) -> dict:
    if map_path.exists():
        try:
            return json.loads(map_path.read_text())
        except Exception:
            return {}
    return {}


def _save_id_map(map_path: pathlib.Path, id_map: dict) -> None:
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sanitize Organizze snapshot for LLM consumption."
    )
    ap.add_argument("--snapshot", required=True, help="Input snapshot path")
    ap.add_argument("--out", required=True, help="Output sanitized snapshot path")
    args = ap.parse_args()

    snap_path = pathlib.Path(args.snapshot)
    out_path = pathlib.Path(args.out)

    if not snap_path.exists():
        print(f"err|snapshot-missing|{snap_path}", file=sys.stderr)
        return 1

    try:
        snapshot = json.loads(snap_path.read_text())
    except Exception as e:
        print(f"err|snapshot-parse|{e}", file=sys.stderr)
        return 1

    map_path = pathlib.Path.home() / "finance" / "organizze" / ".id-map.json"
    id_map = _load_id_map(map_path)

    try:
        sanitized = sanitize_snapshot(snapshot, id_map)
    except Exception as e:
        print(f"err|sanitize|{e}", file=sys.stderr)
        return 1

    try:
        _save_id_map(map_path, id_map)
    except Exception as e:
        print(f"warn|id-map-save|{e}", file=sys.stderr)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"err|output-write|{e}", file=sys.stderr)
        return 1

    print(f"ok|sanitized|{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
