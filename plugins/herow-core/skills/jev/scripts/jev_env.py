#!/usr/bin/env python3
"""Environment helpers shared by the Jev shims, session hook, doctor and route.py.

Subcommands: `resolve <plugin>` (installPath), `probe` (key source name), `policy` (routing policy).
Runs under the system python3, so it stays stdlib-only and avoids 3.10+ syntax.
"""

import getpass
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

KEY_SERVICE = "openrouter-api-key"
KEYS_URL = "https://openrouter.ai/keys"
INSTALL_FIX = "Install it with /plugin install herow-core@herow"
_warned = set()  # type: set


class Unavailable(Exception):
    """A problem the user can act on; str() is the `jev unavailable: ...` line."""

    def __init__(self, reason: str, fix: str) -> None:
        super().__init__(f"jev unavailable: {reason}. {fix}")


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def herow_home() -> Path:
    return Path(os.environ.get("HEROW_HOME") or Path.home() / ".herow")


def registry_path() -> Path:
    override = os.environ.get("JEV_PLUGIN_REGISTRY")
    return (
        Path(override) if override else claude_dir() / "plugins/installed_plugins.json"
    )


def settings_path() -> Path:
    return claude_dir() / "settings.json"


def keychain_user() -> str:
    return getpass.getuser()


def security_bin() -> str:
    return os.environ.get("JEV_SECURITY_BIN") or "security"


def keychain_argv() -> List[str]:
    return [security_bin(), "find-generic-password", "-a", keychain_user(), "-s", KEY_SERVICE, "-w"]


def _load_json(path: Path, what: str) -> object:
    try:
        return json.loads(path.read_text())
    except OSError as e:
        raise Unavailable(
            f"cannot read {what} ({path}: {e.strerror})", "Check the file permissions"
        ) from e
    except ValueError as e:
        raise Unavailable(
            f"{what} is not valid JSON ({path})", "Repair or restore that file"
        ) from e


def load_json_file(path: Path) -> dict:
    """Parsed JSON object, {} when the file is absent; malformed content raises Unavailable."""
    if not path.is_file():
        return {}
    data = _load_json(path, path.name)
    return data if isinstance(data, dict) else {}


def _disabled() -> set:
    path = settings_path()
    if not path.is_file():
        return set()
    data = _load_json(path, "settings.json")
    enabled = data.get("enabledPlugins", {}) if isinstance(data, dict) else {}
    return (
        {k for k, v in enabled.items() if v is False}
        if isinstance(enabled, dict)
        else set()
    )


def _registry() -> Dict[str, list]:
    data = _load_json(registry_path(), "installed_plugins.json")
    plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
    return plugins if isinstance(plugins, dict) else {}


def _within(cwd: Path, project: str) -> bool:
    # Resolve both sides: macOS /var vs /private/var and symlinked checkouts would never match.
    try:
        here, proj = Path(os.path.realpath(cwd)), Path(os.path.realpath(project))
        return here == proj or proj in here.parents
    except (TypeError, ValueError, OSError):
        return False


def pick_entry(entries: list, cwd: Path) -> Optional[dict]:
    """Deepest project/local entry containing cwd, else the user entry."""
    best, best_depth = None, -1
    for e in entries:
        if (
            not isinstance(e, dict)
            or not e.get("installPath")
            or e.get("scope") == "user"
        ):
            continue
        proj = e.get("projectPath")
        if proj and _within(cwd, proj) and len(Path(proj).parts) > best_depth:
            best, best_depth = e, len(Path(proj).parts)
    if best:
        return best
    return next(
        (
            e
            for e in entries
            if isinstance(e, dict) and e.get("scope") == "user" and e.get("installPath")
        ),
        None,
    )


def plugin_installs(cwd: Optional[Path] = None) -> List[Tuple[str, Path, str]]:
    """(plugin name, installPath, registry key) per enabled plugin, using resolve's precedence."""
    if not registry_path().is_file():
        return []
    cwd = cwd or Path.cwd()
    disabled = _disabled()
    out = []
    for full, entries in _registry().items():
        if full in disabled or not isinstance(entries, list):
            continue
        e = pick_entry(entries, cwd)
        if e:
            out.append((full.split("@")[0], Path(e["installPath"]), full))
    return out


def resolve(plugin: str, cwd: Optional[Path] = None) -> Path:
    """installPath of the enabled `plugin` install that applies to cwd."""
    if not registry_path().is_file():
        raise Unavailable(f"plugin registry not found ({registry_path()})", INSTALL_FIX)
    cwd = cwd or Path.cwd()
    disabled = _disabled()
    entries, found_disabled = [], False
    for full, es in _registry().items():
        if full.split("@")[0] != plugin or not isinstance(es, list):
            continue
        if full in disabled:
            found_disabled = True
        else:
            entries.extend(es)
    if not entries:
        if found_disabled:
            raise Unavailable(
                f"{plugin} is disabled in settings.json", "Enable it with /plugin"
            )
        raise Unavailable(f"{plugin} is not installed", INSTALL_FIX)
    chosen = pick_entry(entries, cwd)
    if not chosen:
        raise Unavailable(f"{plugin} has no install that applies to {cwd}", INSTALL_FIX)
    path = Path(chosen["installPath"])
    if not path.is_dir():
        raise Unavailable(
            f"{plugin} install path is gone ({path})",
            "Run /herow-core:upgrade or reinstall with /plugin",
        )
    return path


def probe() -> str:
    """Name the first key source present, Keychain then env (as jev.py reads them); never emits the secret."""
    try:
        budget = float(os.environ.get("JEV_PROBE_BUDGET") or 3)
    except ValueError:
        budget = 3.0
    try:
        # Own process group: on timeout the whole tree dies, so no grandchild keeps the pipe open.
        proc = subprocess.Popen(
            keychain_argv(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        proc = None
    if proc is not None:
        try:
            out, _ = proc.communicate(timeout=budget)
            # Only emptiness is inspected; the value is dropped right here.
            if proc.returncode == 0 and out.strip():
                return "keychain"
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.communicate()
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return "env"
    return "none"


def load_config() -> dict:
    """config.json under HEROW_HOME/jev; malformed JSON warns once on stderr and yields {}."""
    path = herow_home() / "jev/config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return data
    except (OSError, ValueError):
        if str(path) not in _warned:
            _warned.add(str(path))
            print(f"jev: ignoring malformed {path}; using defaults", file=sys.stderr)
        return {}


def policy() -> dict:
    cfg = load_config()
    routing = "generic"
    consents = herow_home() / "jev/consents.md"
    try:
        text = consents.read_text()
    except OSError:
        text = ""
    if re.search(r"^\s*(?:[-*]\s*)?routing:\s*project-names\s*$", text, re.M):
        routing = "project-names"
    return {
        "routing_assist": cfg.get("routing_assist") is not False,
        "routing": routing,
    }


def main(argv: List[str]) -> int:
    try:
        if len(argv) == 3 and argv[1] == "resolve":
            print(resolve(argv[2]))
        elif len(argv) == 2 and argv[1] == "probe":
            print(probe())
        elif len(argv) == 2 and argv[1] == "policy":
            p = policy()
            print(f"routing_assist={'true' if p['routing_assist'] else 'false'}")
            print(f"routing={p['routing']}")
        else:
            print(
                "usage: jev_env.py resolve <plugin> | probe | policy", file=sys.stderr
            )
            return 2
    except Unavailable as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
