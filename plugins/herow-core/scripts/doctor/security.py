#!/usr/bin/env python3
"""Security checks for /herow-core:doctor. Stdlib only; dry-run by default.

Checks:
  permissions_deny   — ~/.claude/settings.json must deny reads of env/credentials/
                       secrets/mcp-stash (FAIL if the deny block is missing/partial).
  plaintext_secrets  — ~/.claude/mcp-stash.json must hold ${VAR} refs, not literal
                       tokens/keys (FAIL if any literal secret is found).

Apply (`--apply <id>`) is idempotent and always writes a timestamped .bak first.
No real secret value is ever written to a file or printed to stdout — the literal
survives only in the chmod-600 backup.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _doctor import (  # noqa: E402
    backup,
    emit,
    fix_cmd_for,
    load_json,
    mcp_stash_path,
    run_main,
    settings_path,
    write_json,
)

# --- permissions_deny -------------------------------------------------------


def deny_rules() -> list[str]:
    """Deny rules that protect secret material. The mcp-stash entries are absolute
    (resolved at runtime from the home dir) — never stored as a literal in source."""
    stash = mcp_stash_path()
    return [
        "Read(.env)",
        "Read(.env.*)",
        "Read(**/.env)",
        "Read(**/.env.*)",
        "Read(**/*credentials*)",
        "Read(**/*secret*)",
        f"Read({stash})",
        f"Read({stash}.bak.*)",
    ]


def check_permissions_deny() -> None:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        emit("permissions_deny", "pass", "settings.json missing/unreadable — skipping")
        return
    rules = deny_rules()
    perms = s.get("permissions")
    deny = perms.get("deny") if isinstance(perms, dict) else None
    have = set(deny) if isinstance(deny, list) else set()
    missing = [r for r in rules if r not in have]
    if not missing:
        emit(
            "permissions_deny",
            "pass",
            "permissions.deny covers env/credentials/secrets/mcp-stash",
        )
        return
    diff = "+ permissions.deny:\n" + "\n".join(f"  + {r}" for r in missing)
    emit(
        "permissions_deny",
        "fail",
        f"permissions.deny missing {len(missing)} secret-protection rule(s)",
        diff=diff,
        fix_cmd=fix_cmd_for(__file__, "permissions_deny"),
    )


def apply_permissions_deny() -> bool:
    s = load_json(settings_path())
    if not isinstance(s, dict):
        return False  # missing/unparseable — never fabricate or clobber settings.json
    perms = s.setdefault("permissions", {})
    if not isinstance(perms, dict):
        return False
    existing = perms.get("deny")
    existing = list(existing) if isinstance(existing, list) else []
    union = existing + [r for r in deny_rules() if r not in existing]
    if union == existing:
        return False  # idempotent noop
    backup(settings_path())
    perms["deny"] = union
    write_json(settings_path(), s)
    return True


# --- plaintext_secrets ------------------------------------------------------

_REF_RE = re.compile(r"^\$\{.+\}$")
_SECRET_KEY_RE = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD|PASSWD|PAT|CREDENTIAL)", re.I)
_NON_SECRET_VALUES = {
    "stdio",
    "error",
    "true",
    "false",
    "debug",
    "info",
    "warn",
    "http",
    "https",
    "none",
    "off",
    "on",
}
_TOKEN_SHAPE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def looks_like_secret(key: str, value) -> bool:
    """True when an mcp env value is a literal secret (not a ${VAR} ref, not config)."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or _REF_RE.match(v):
        return False  # empty or already a ${VAR} reference
    if _SECRET_KEY_RE.search(key):
        return v.lower() not in _NON_SECRET_VALUES
    # value-based fallback: long opaque token, no spaces, not a URL
    if (
        len(v) >= 20
        and _TOKEN_SHAPE_RE.match(v)
        and not v.lower().startswith(("http://", "https://"))
    ):
        return True
    return False


def _upper_snake(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()


def derive_var_name(server: str, key: str, key_counts: dict[str, int]) -> str:
    """Env key verbatim when globally unique across the stash; else server-prefixed."""
    base = key if key.isupper() and "_" in key else _upper_snake(key)
    if key_counts.get(key, 0) <= 1:
        return base
    return f"{_upper_snake(server)}__{base}"


def _env_of(cfg) -> dict:
    """The server's env mapping, or {} when absent/malformed (never crashes scan)."""
    env = cfg.get("env") if isinstance(cfg, dict) else None
    return env if isinstance(env, dict) else {}


def _scan_secrets(stash: dict):
    """Return (hits, key_counts) where hits = [(server, key, value), ...]."""
    key_counts: dict[str, int] = {}
    for cfg in stash.values():
        for k in _env_of(cfg):
            key_counts[k] = key_counts.get(k, 0) + 1
    hits = []
    for srv, cfg in stash.items():
        for k, v in _env_of(cfg).items():
            if looks_like_secret(k, v):
                hits.append((srv, k, v))
    return hits, key_counts


def check_plaintext_secrets() -> None:
    stash = load_json(mcp_stash_path())
    if not isinstance(stash, dict):
        emit("plaintext_secrets", "pass", "no mcp-stash.json — nothing to scan")
        return
    hits, key_counts = _scan_secrets(stash)
    if not hits:
        emit("plaintext_secrets", "pass", "all mcp-stash secrets are ${VAR} references")
        return
    lines = [
        f"  {srv}.env.{k}: <literal secret> -> ${{{derive_var_name(srv, k, key_counts)}}}"
        for srv, k, _v in hits
    ]
    emit(
        "plaintext_secrets",
        "fail",
        f"{len(hits)} literal secret(s) in mcp-stash.json (move to ${{VAR}} refs)",
        diff="\n".join(lines),
        fix_cmd=fix_cmd_for(__file__, "plaintext_secrets"),
    )


def apply_plaintext_secrets() -> bool:
    stash = load_json(mcp_stash_path())
    if not isinstance(stash, dict):
        return False
    hits, key_counts = _scan_secrets(stash)
    if not hits:
        return False  # idempotent: already ${VAR} refs
    bak = backup(mcp_stash_path())  # only surviving copy of the literals (chmod 600)
    vars_needed = []
    for srv, k, _v in hits:
        var = derive_var_name(srv, k, key_counts)
        stash[srv]["env"][k] = "${" + var + "}"
        vars_needed.append(var)
    write_json(mcp_stash_path(), stash)
    # Surface var NAMES only — never the values (they stay in the chmod-600 .bak).
    for var in vars_needed:
        print(f"info|export-needed|{var}")
    if bak is not None:
        print(
            f"info|secrets-bak|{bak} (chmod 600 — original values preserved here only)"
        )
    print(
        "info|restart|add the exports to ~/.zshrc, then fully restart Claude Code "
        "(${VAR} resolves at MCP server spawn)"
    )
    return True


CHECKS = {
    "permissions_deny": (check_permissions_deny, apply_permissions_deny),
    "plaintext_secrets": (check_plaintext_secrets, apply_plaintext_secrets),
}


def main(argv=None) -> int:
    return run_main(CHECKS, sys.argv[1:] if argv is None else argv, __file__)


if __name__ == "__main__":
    raise SystemExit(main())
