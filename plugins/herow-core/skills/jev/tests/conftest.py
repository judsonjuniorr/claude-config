"""Shared fixtures: an isolated HOME/HEROW_HOME/CLAUDE_CONFIG_DIR and stub binaries."""

import json
import stat
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def write_exe(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class Env:
    """Handle on the isolated environment built by the `env` fixture."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.claude = self.home / ".claude"
        self.herow = self.home / ".herow"
        self.project = root / "project"
        for d in (self.claude / "plugins", self.herow / "jev", self.project):
            d.mkdir(parents=True)

    def install_plugin(
        self,
        full: str,
        scope: str = "user",
        project_path: Optional[Path] = None,
        name: Optional[str] = None,
    ) -> Path:
        """Create an installPath dir and register it; returns the dir."""
        plugin = full.split("@")[0]
        install = self.root / "cache" / (name or f"{full}-{scope}")
        install.mkdir(parents=True, exist_ok=True)
        reg = self.claude / "plugins/installed_plugins.json"
        data = (
            json.loads(reg.read_text())
            if reg.exists()
            else {"version": 2, "plugins": {}}
        )
        entry: Dict[str, str] = {"scope": scope, "installPath": str(install)}
        if project_path is not None:
            entry["projectPath"] = str(project_path)
        data["plugins"].setdefault(full, []).append(entry)
        reg.write_text(json.dumps(data))
        assert plugin
        return install

    def settings(self, data: dict) -> None:
        (self.claude / "settings.json").write_text(json.dumps(data))

    def config(self, data: object) -> None:
        text = data if isinstance(data, str) else json.dumps(data)
        (self.herow / "jev/config.json").write_text(text)

    def add_skill(self, base: Path, name: str, desc: str) -> None:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\nbody\n"
        )

    def add_command(self, base: Path, rel: str, desc: str) -> None:
        f = base / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"---\ndescription: {desc}\n---\nbody\n")

    def add_agent(self, base: Path, name: str, desc: str) -> None:
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\nbody\n"
        )


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env(tmp_path)
    monkeypatch.setenv("HOME", str(e.home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(e.claude))
    monkeypatch.setenv("HEROW_HOME", str(e.herow))
    for var in (
        "OPENROUTER_API_KEY",
        "JEV_PLUGIN_REGISTRY",
        "JEV_EXTRA_COMMAND_DIRS",
        "JEV_PROBE_BUDGET",
        "JEV_KEY_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    # Default: no Keychain. Tests that want one overwrite JEV_SECURITY_BIN.
    monkeypatch.setenv(
        "JEV_SECURITY_BIN", str(write_exe(tmp_path / "security-fail", "exit 44\n"))
    )
    monkeypatch.chdir(e.project)
    return e


@pytest.fixture
def security_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Path]:
    """Build a fake `security`; logs its argv to <stub>.args and prints `out`/`err`."""

    def make(rc: int = 0, out: str = "", err: str = "", sleep: float = 0) -> Path:
        stub = tmp_path / "security-stub"
        body = f'printf "%s\\n" "$*" > "{stub}.args"\n'
        if sleep:
            body += f"sleep {sleep}\n"
        if out:
            body += f'printf "%s" "{out}"\n'
        if err:
            body += f'printf "%s" "{err}" >&2\n'
        body += f"exit {rc}\n"
        write_exe(stub, body)
        monkeypatch.setenv("JEV_SECURITY_BIN", str(stub))
        return stub

    return make


FAKE_JEV = r"""#!/usr/bin/env python3
import json, os, sys
spec = json.load(open(os.environ["FAKE_JEV_SPEC"]))
items = json.load(sys.stdin)["items"]
results, errors = [], []
for it in items:
    s = spec.get(it["state"], {})
    if s.get("error"):
        errors.append({"item_id": it["id"], "status": 500, "body": "boom", "request": {}})
        continue
    qs = it["questions"]
    def pick(q, name):
        for k, v in qs[q]["criteria"].items():
            if v.split(": ", 1)[0] == name or k == name:
                return k
        return "none"
    answers, unc = {}, []
    for q in ("agent", "skill"):
        conf = s.get(q + "_conf", 0.95)
        key = pick(q, s.get(q, "none"))
        answers[q] = {"type": "choice", "choice": key, "confidence": conf,
                      "probabilities": {key: conf, "none": 1 - conf}}
        if conf < 0.7:
            unc.append(q)
    if "vault" in qs:
        answers["vault"] = {"type": "noul", "noul": s.get("vault", 0.1)}
    results.append({"id": it["id"], "answers": answers, "uncertain": unc, "ms": 1,
                    "cost": 0.0001, "cost_source": "usage.cost", "model": "fake-model",
                    "generation_id": "g", "usage": {"input_tokens": 100}})
print(json.dumps({"results": results, "errors": errors,
                  "totals": {"n": len(results), "failed": len(errors), "ms": 1, "wall_ms": 2, "cost": 0.0001 * len(results)}}))
sys.exit(1 if errors else 0)
"""


@pytest.fixture
def fake_jev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[Dict[str, dict]], Path]:
    """Replace route.JEV with a script that answers per task text from a spec dict."""
    import route

    def make(spec: Dict[str, dict]) -> Path:
        script = tmp_path / "fake_jev.py"
        script.write_text(FAKE_JEV)
        spec_file = tmp_path / "fake_spec.json"
        spec_file.write_text(json.dumps(spec))
        monkeypatch.setenv("FAKE_JEV_SPEC", str(spec_file))
        monkeypatch.setattr(route, "JEV", script)
        return script

    return make


def names(rows: List[dict], key: str) -> List[str]:
    return [r[key] for r in rows]
