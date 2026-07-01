#!/usr/bin/env python3
"""
model-pin.py — list and pin Claude Code model aliases for opusplan.

Modes:
  --list               Print top-3 opus/sonnet candidates (family|id|label),
                       live from the Anthropic Models API when ANTHROPIC_API_KEY
                       is set, otherwise from a static fallback.
  --apply              Write ANTHROPIC_DEFAULT_{OPUS,SONNET}_MODEL into
                       ~/.claude/settings.json (idempotent, atomic, .bak first)
    --opus <id>        Opus model ID to pin
    --sonnet <id>      Sonnet model ID to pin
    --dry-run          Show diff without writing
"""

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

MODELS_API_LIMIT = 100
MODELS_API_TIMEOUT_S = 5

# Static fallback — 3 most recent per family as of 2026-06-30.
# Updated here whenever new models ship; the live --list path stays current.
STATIC_FALLBACK = [
    ("opus", "claude-opus-4-8", "Opus 4.8"),
    ("opus", "claude-opus-4-7", "Opus 4.7"),
    ("opus", "claude-opus-4-6", "Opus 4.6"),
    ("sonnet", "claude-sonnet-5", "Sonnet 5"),
    ("sonnet", "claude-sonnet-4-6", "Sonnet 4.6"),
    ("sonnet", "claude-sonnet-4-5", "Sonnet 4.5"),
]

# Minimum Claude Code version required to select each model, per the
# code.claude.com/docs/en/model-config release notes. Models absent here
# have no known minimum-version gate.
MODEL_MIN_VERSION = {
    "claude-sonnet-5": (2, 1, 197),
    "claude-opus-4-8": (2, 1, 154),
}

# Fallback to substitute when the installed Claude Code is below a model's
# minimum version. Absent entry -> drop the pin instead of substituting.
MODEL_VERSION_FALLBACK = {
    "claude-sonnet-5": "claude-sonnet-4-6",
}


def _label(model_id):
    """Derive a short display label from a model ID (e.g. claude-opus-4-8 -> Opus 4.8)."""
    parts = model_id.split("-")
    for i, p in enumerate(parts):
        if p in ("opus", "sonnet", "haiku", "fable"):
            family = p.capitalize()
            version = ".".join(parts[i + 1 :]) if i + 1 < len(parts) else ""
            return ("%s %s" % (family, version)).strip()
    return model_id


def _fetch_live():
    """Try the Anthropic Models API. Returns [(family, id, label)] or None.

    Returns None (triggering the static fallback) both when the API is
    unreachable/misconfigured AND when a live response only yields
    candidates for one family — a partial result is not usable by callers
    that expect both an opus and a sonnet list.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models?limit=%d" % MODELS_API_LIMIT,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=MODELS_API_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(
            "warn|model-pin|Models API returned HTTP %s — using static fallback"
            % e.code,
            file=sys.stderr,
        )
        return None
    except (urllib.error.URLError, OSError) as e:
        print(
            "warn|model-pin|Models API unreachable (%s) — using static fallback" % e,
            file=sys.stderr,
        )
        return None
    except (ValueError, TypeError) as e:
        print(
            "warn|model-pin|Models API returned malformed data (%s) — using static fallback"
            % e,
            file=sys.stderr,
        )
        return None

    models = data.get("data", [])
    buckets = {"opus": [], "sonnet": []}
    for m in models:
        mid = m.get("id", "")
        for fam in buckets:
            if ("claude-%s-" % fam) in mid:
                buckets[fam].append((m.get("created_at", 0), mid))
                break

    result = []
    for fam in ("opus", "sonnet"):
        top3 = sorted(buckets[fam], reverse=True)[:3]
        if not top3:
            # Partial live data (e.g. an API-key scope missing one family) is
            # not a usable candidate list — fall back to the static list in
            # full rather than silently offering only one family.
            return None
        for _, mid in top3:
            result.append((fam, mid, _label(mid)))
    return result


def cmd_list():
    rows = _fetch_live() or STATIC_FALLBACK
    for family, mid, label in rows:
        print("%s|%s|%s" % (family, mid, label))


def _load_settings():
    if not os.path.exists(SETTINGS):
        return {}
    try:
        with open(SETTINGS) as f:
            return json.load(f)
    except ValueError as e:
        print(
            "err|model-pin|cannot parse %s: %s" % (SETTINGS, e),
            file=sys.stderr,
        )
        sys.exit(1)


def _write_settings(settings):
    d = os.path.dirname(os.path.abspath(SETTINGS))
    os.makedirs(d, exist_ok=True)
    orig_mode = None
    if os.path.exists(SETTINGS):
        orig_mode = stat.S_IMODE(os.stat(SETTINGS).st_mode)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".settings-tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        if orig_mode is not None:
            os.chmod(tmp, orig_mode)
        os.replace(tmp, SETTINGS)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _backup():
    if not os.path.exists(SETTINGS):
        return None
    import shutil, datetime

    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak.%s" % (SETTINGS, ts)
    shutil.copy2(SETTINGS, bak)
    return bak


def _installed_cc_version():
    """Return the installed Claude Code version as (major, minor, patch), or None if it can't be determined."""
    try:
        out = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out.stdout)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def _version_gate(model_id):
    """Return model_id, or a fallback/None if the installed Claude Code is below its minimum version.

    Fails open (returns model_id unchanged) when the installed version can't
    be determined — the minimum-version requirement is still documented in
    CHANGELOG.md/doctor.md for the user to verify manually.
    """
    min_v = MODEL_MIN_VERSION.get(model_id)
    if not min_v:
        return model_id
    installed = _installed_cc_version()
    if installed is None or installed >= min_v:
        return model_id
    fallback = MODEL_VERSION_FALLBACK.get(model_id)
    print(
        "warn|model-pin|%s requires Claude Code >= %s (installed: %s) — %s"
        % (
            model_id,
            ".".join(map(str, min_v)),
            ".".join(map(str, installed)),
            ("pinning %s instead" % fallback) if fallback else "skipping this pin",
        ),
        file=sys.stderr,
    )
    return fallback


def cmd_apply(opus_id, sonnet_id, dry_run):
    if not opus_id and not sonnet_id:
        print(
            "err|model-pin|at least one of --opus or --sonnet is required",
            file=sys.stderr,
        )
        sys.exit(1)

    for model_id, family in ((opus_id, "opus"), (sonnet_id, "sonnet")):
        if model_id and ("claude-%s-" % family) not in model_id:
            print(
                "err|model-pin|--%s value %r is not a %s-family model id"
                % (family, model_id, family),
                file=sys.stderr,
            )
            sys.exit(1)

    if opus_id:
        opus_id = _version_gate(opus_id)
    if sonnet_id:
        sonnet_id = _version_gate(sonnet_id)

    if not opus_id and not sonnet_id:
        print(
            "ok|model-pin|nothing to apply after version gating",
        )
        return

    settings = _load_settings()
    if not isinstance(settings, dict):
        settings = {}
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        env = {}
        settings["env"] = env

    targets = {}
    if opus_id:
        targets["ANTHROPIC_DEFAULT_OPUS_MODEL"] = opus_id
    if sonnet_id:
        targets["ANTHROPIC_DEFAULT_SONNET_MODEL"] = sonnet_id

    # (key, status, old, new)
    changes = []
    for key, val in targets.items():
        if env.get(key) == val:
            changes.append((key, "already-set", env.get(key), val))
        else:
            changes.append((key, "set", env.get(key), val))

    if dry_run:
        for key, status, old, new in changes:
            if status == "set":
                print("- %s: %s" % (key, json.dumps(old)))
                print("+ %s: %s" % (key, json.dumps(new)))
            else:
                print("  %s: %s (already-set)" % (key, json.dumps(new)))
        return

    if any(s == "set" for _, s, _, _ in changes):
        bak = _backup()
        for key, status, _, val in changes:
            if status == "set":
                env[key] = val
        _write_settings(settings)
        if bak:
            print("ok|model-pin|backup=%s" % bak)

    for key, status, _, _ in changes:
        print("ok|%s|%s" % (key, status))


def main():
    parser = argparse.ArgumentParser(
        description="List and pin Claude Code model aliases for opusplan.",
    )
    parser.add_argument(
        "--list", action="store_true", help="Print top-3 opus/sonnet candidates"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write model pins to settings.json"
    )
    parser.add_argument("--opus", metavar="MODEL_ID", help="Opus model ID to pin")
    parser.add_argument("--sonnet", metavar="MODEL_ID", help="Sonnet model ID to pin")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show diff without writing"
    )

    args = parser.parse_args()

    if args.list:
        cmd_list()
    elif args.apply:
        cmd_apply(args.opus, args.sonnet, args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
