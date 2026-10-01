"""jev_env: registry resolve, key probe and routing policy."""

import subprocess
import sys
import time
from pathlib import Path

import jev_env
import pytest

HELPER = Path(jev_env.__file__)


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *args], capture_output=True, text=True
    )


# resolve


def test_resolve_user_scope(env):
    install = env.install_plugin("herow-core@herow")
    assert jev_env.resolve("herow-core") == install


def test_resolve_project_beats_user_inside_project(env):
    env.install_plugin("herow-core@herow", "user")
    proj = env.install_plugin("herow-core@herow", "project", env.project)
    assert jev_env.resolve("herow-core") == proj


def test_resolve_project_ignored_outside_project(env, tmp_path):
    user = env.install_plugin("herow-core@herow", "user")
    env.install_plugin("herow-core@herow", "local", tmp_path / "elsewhere")
    assert jev_env.resolve("herow-core") == user


def test_resolve_deepest_project_wins(env):
    env.install_plugin("herow-core@herow", "user")
    shallow = env.install_plugin(
        "herow-core@herow", "project", env.root, name="shallow"
    )
    deep = env.install_plugin("herow-core@herow", "local", env.project, name="deep")
    assert jev_env.resolve("herow-core") == deep != shallow


def test_resolve_skips_disabled(env):
    env.install_plugin("herow-core@herow")
    env.settings({"enabledPlugins": {"herow-core@herow": False}})
    with pytest.raises(jev_env.Unavailable) as exc:
        jev_env.resolve("herow-core")
    assert "disabled" in str(exc.value)
    assert str(exc.value).startswith("jev unavailable: ")


def test_resolve_disabled_marketplace_falls_to_other(env):
    env.install_plugin("herow-core@herow", name="a")
    other = env.install_plugin("herow-core@other", name="b")
    env.settings({"enabledPlugins": {"herow-core@herow": False}})
    assert jev_env.resolve("herow-core") == other


def test_resolve_path_gone(env):
    install = env.install_plugin("herow-core@herow")
    install.rmdir()
    with pytest.raises(jev_env.Unavailable, match="gone"):
        jev_env.resolve("herow-core")


def test_resolve_malformed_registry(env):
    (env.claude / "plugins/installed_plugins.json").write_text("{not json")
    with pytest.raises(jev_env.Unavailable, match="installed_plugins.json"):
        jev_env.resolve("herow-core")


def test_resolve_malformed_settings(env):
    env.install_plugin("herow-core@herow")
    (env.claude / "settings.json").write_text("{nope")
    with pytest.raises(jev_env.Unavailable, match="settings.json"):
        jev_env.resolve("herow-core")


def test_resolve_missing_registry_and_plugin(env):
    with pytest.raises(jev_env.Unavailable, match="registry"):
        jev_env.resolve("herow-core")
    env.install_plugin("herow-dev@herow")
    with pytest.raises(jev_env.Unavailable, match="not installed"):
        jev_env.resolve("herow-core")


def test_resolve_registry_override(env, tmp_path, monkeypatch):
    install = env.install_plugin("herow-core@herow")
    moved = tmp_path / "other-registry.json"
    moved.write_text((env.claude / "plugins/installed_plugins.json").read_text())
    (env.claude / "plugins/installed_plugins.json").unlink()
    monkeypatch.setenv("JEV_PLUGIN_REGISTRY", str(moved))
    assert jev_env.resolve("herow-core") == install


def test_cli_resolve_ok_and_fail(env):
    install = env.install_plugin("herow-core@herow")
    ok = cli("resolve", "herow-core")
    assert ok.returncode == 0 and ok.stdout.strip() == str(install)
    bad = cli("resolve", "nope")
    assert bad.returncode == 1 and bad.stdout == ""
    assert bad.stderr.startswith("jev unavailable: ") and "Traceback" not in bad.stderr


def test_plugin_installs_uses_same_precedence(env):
    env.install_plugin("herow-core@herow", "user", name="user")
    proj = env.install_plugin("herow-core@herow", "project", env.project, name="proj")
    got = {full: path for _, path, full in jev_env.plugin_installs()}
    assert got["herow-core@herow"] == proj


# probe


def test_probe_keychain_first_like_read_key(env, monkeypatch, security_stub):
    security_stub(rc=0, out="sk-from-keychain")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert jev_env.probe() == "keychain"


def test_probe_env_when_keychain_has_no_entry(monkeypatch, security_stub):
    security_stub(rc=44)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert jev_env.probe() == "env"


def test_probe_empty_keychain_item_does_not_count(monkeypatch, security_stub):
    security_stub(rc=0, out="")
    assert jev_env.probe() == "none"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert jev_env.probe() == "env"


def test_probe_empty_env_is_not_a_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert jev_env.probe() == "none"


def test_probe_keychain_never_emits_the_secret(env, security_stub):
    stub = security_stub(rc=0, out="sk-SECRET-STDOUT", err="sk-SECRET-STDERR")
    res = cli("probe")
    assert res.stdout == "keychain\n"
    assert "SECRET" not in res.stdout + res.stderr
    args = Path(f"{stub}.args").read_text().split()
    assert "-w" in args and "openrouter-api-key" in args


def test_probe_keychain_missing_entry(security_stub):
    security_stub(rc=44)
    assert jev_env.probe() == "none"


def test_probe_hung_keychain_times_out(security_stub, monkeypatch):
    security_stub(rc=0, out="late", sleep=5)
    monkeypatch.setenv("JEV_PROBE_BUDGET", "0.5")
    t0 = time.time()
    assert jev_env.probe() == "none"
    assert time.time() - t0 < 3
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert jev_env.probe() == "env"


def test_probe_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("JEV_SECURITY_BIN", str(tmp_path / "does-not-exist"))
    assert jev_env.probe() == "none"


# policy


def test_policy_defaults(env):
    assert jev_env.policy() == {"routing_assist": True, "routing": "generic"}


def test_policy_project_names_from_consents(env):
    (env.herow / "jev/consents.md").write_text(
        "# Consents\n\n- routing: project-names\n"
    )
    assert jev_env.policy()["routing"] == "project-names"


def test_policy_consents_needs_exact_line(env):
    (env.herow / "jev/consents.md").write_text(
        "routing: project-names-not\nno routing: project-names here\n"
    )
    assert jev_env.policy()["routing"] == "generic"


def test_policy_routing_assist_false(env):
    env.config({"routing_assist": False})
    assert jev_env.policy()["routing_assist"] is False


def test_policy_malformed_config_warns_on_stderr_only(env):
    env.config("{broken")
    res = cli("policy")
    assert res.returncode == 0
    assert res.stdout == "routing_assist=true\nrouting=generic\n"
    assert "config.json" in res.stderr


def test_cli_policy_lines(env):
    env.config({"routing_assist": False})
    (env.herow / "jev/consents.md").write_text("routing: project-names\n")
    assert cli("policy").stdout == "routing_assist=false\nrouting=project-names\n"


def test_cli_usage_error():
    res = cli("bogus")
    assert res.returncode == 2


def test_resolve_project_path_through_symlink(env):
    link = env.root / "link-to-project"
    link.symlink_to(env.project)
    env.install_plugin("herow-core@herow", "user")
    proj = env.install_plugin("herow-core@herow", "project", link)
    assert jev_env.resolve("herow-core") == proj
