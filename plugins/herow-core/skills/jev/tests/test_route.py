"""route.py: paths, catalog, postfilter, eval gate, and the output line format (REG-1)."""

import json
import os
import time
from pathlib import Path

import pytest
import route


def skill_names(cat):
    return set(cat["skills"])


def build(env):
    return route.build_catalog()


# paths


def test_paths_follow_env_at_call_time(env, monkeypatch, tmp_path):
    p = route.paths()
    assert p["herow"] == env.herow and p["claude"] == env.claude
    assert (
        p["cache"] == env.herow / "jev/cache"
        and p["log"] == env.herow / "jev/route.log"
    )
    monkeypatch.setenv("HEROW_HOME", str(tmp_path / "other"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cc"))
    p2 = route.paths()
    assert p2["herow"] == tmp_path / "other" and p2["claude"] == tmp_path / "cc"
    assert p2["registry"] == tmp_path / "cc/plugins/installed_plugins.json"


def test_paths_defaults(monkeypatch, env):
    monkeypatch.delenv("HEROW_HOME")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    p = route.paths()
    assert p["herow"] == env.home / ".herow" and p["claude"] == env.home / ".claude"


# command dirs


def test_default_command_dirs_are_scanned_recursively(env):
    env.add_command(env.claude / "commands", "plain.md", "Plain command")
    env.add_command(env.claude / "commands", "ns/nested.md", "Nested command")
    env.add_command(env.project / ".claude/commands", "proj.md", "Project command")
    skills = build(env)["skills"]
    assert {"plain", "ns:nested", "proj"} <= set(skills)
    assert route.command_dirs() == [env.claude / "commands", Path(".claude/commands")]


def test_extra_dirs_from_config_with_expansion(env, monkeypatch):
    monkeypatch.setenv("MY_CMDS", str(env.root / "extra2"))
    env.add_command(env.home / "extra1", "one.md", "One")
    env.add_command(env.root / "extra2", "two.md", "Two")
    env.config(
        {"extra_command_dirs": ["~/extra1", "$MY_CMDS", str(env.root / "missing")]}
    )
    assert {"one", "two"} <= skill_names(build(env))


def test_env_var_replaces_config(env, monkeypatch):
    env.add_command(env.home / "from-config", "cfg.md", "Cfg")
    env.add_command(env.home / "from-env", "envcmd.md", "Env")
    env.config({"extra_command_dirs": ["~/from-config"]})
    monkeypatch.setenv("JEV_EXTRA_COMMAND_DIRS", os.pathsep.join(["~/from-env", ""]))
    names = skill_names(build(env))
    assert "envcmd" in names and "cfg" not in names


def test_env_var_set_but_empty_means_no_extras(env, monkeypatch):
    env.add_command(env.home / "from-config", "cfg.md", "Cfg")
    env.config({"extra_command_dirs": ["~/from-config"]})
    monkeypatch.setenv("JEV_EXTRA_COMMAND_DIRS", "")
    assert "cfg" not in skill_names(build(env))
    assert route.extra_command_dirs() == []


def test_malformed_config_warns_once_and_uses_defaults(env, capsys):
    env.config("{oops")
    assert route.extra_command_dirs() == []
    assert route.read_config() == {}
    err = capsys.readouterr().err
    assert err.count("config.json") == 2 or "config.json" in err
    assert "jev" in err.lower()


def test_extra_dirs_feed_sources_mtime(env):
    extra = env.home / "extra"
    extra.mkdir()
    env.config({"extra_command_dirs": [str(extra)]})
    before = route.sources_mtime()
    time.sleep(0.02)
    os.utime(extra, None)
    assert route.sources_mtime() > before


# catalog cache


def test_catalog_written_atomically_and_reused(env):
    cat = route.load_catalog()
    files = sorted(p.name for p in route.paths()["cache"].iterdir())
    assert files == [route.catalog_path().name]
    assert route.load_catalog()["built"] == cat["built"]


def test_corrupt_cache_counts_as_stale(env):
    route.load_catalog()
    route.catalog_path().write_text('{"built": 99999999999, "agents": {')
    cat = route.load_catalog()
    assert "general-purpose" in cat["agents"]
    json.loads(route.catalog_path().read_text())


def test_cache_without_dict_shape_is_rebuilt(env):
    route.load_catalog()
    route.catalog_path().write_text("[]")
    assert "agents" in route.load_catalog()


def test_malformed_registry_is_unavailable_not_traceback(env):
    (env.claude / "plugins/installed_plugins.json").write_text("{x")
    with pytest.raises(route.jev_env.Unavailable):
        route.build_catalog()


# portable view


def seed_plugins(env):
    herow = env.install_plugin("herow-dev@herow", name="hd")
    env.add_agent(herow / "agents", "python-pro", "Python pro")
    env.add_skill(herow / "skills", "research", "Research things")
    other = env.install_plugin("gstackish@elsewhere", name="other")
    env.add_agent(other / "agents", "outsider", "Not herow")
    env.add_skill(other / "skills", "outside-skill", "Not herow either")
    env.add_skill(env.claude / "skills", "localskill", "A local skill")


def test_portable_view_keeps_herow_and_builtins_only(env):
    seed_plugins(env)
    cat = route.load_catalog()
    assert {"gstackish:outsider", "herow-dev:python-pro"} <= set(cat["agents"])
    view = route.portable_view(cat)
    assert (
        "herow-dev:python-pro" in view["agents"] and "general-purpose" in view["agents"]
    )
    assert "gstackish:outsider" not in view["agents"]
    assert "herow-dev:research" in view["skills"] and "code-review" in view["skills"]
    assert not ({"gstackish:outside-skill", "localskill"} & set(view["skills"]))


def test_portable_view_does_not_touch_cache(env):
    seed_plugins(env)
    cat = route.load_catalog()
    before = route.catalog_path().read_bytes()
    route.portable_view(cat)
    assert route.catalog_path().read_bytes() == before
    assert "gstackish:outsider" in route.load_catalog()["agents"]


# plugin install precedence shared with the shim


def test_plugin_installs_prefers_project_entry(env):
    env.install_plugin("herow-core@herow", "user", name="u")
    proj = env.install_plugin("herow-core@herow", "project", env.project, name="p")
    got = dict(route.plugin_installs())
    assert got["herow-core"] == proj


# questions + vault conditional


def cat_with(agents=(), skills=()):
    agents_d = {**route.BUILTIN_AGENTS, **{a: "desc" for a in agents}}
    skills_d = {**route.BUILTIN_SKILLS, **{s: "desc" for s in skills}}
    return {"built": 0, "agents": agents_d, "skills": skills_d}


def make_idx(cat):
    return {"agents": route.index(cat["agents"]), "skills": route.index(cat["skills"])}


def test_vault_question_only_when_vault_skill_installed(env):
    plain = cat_with()
    q, _ = route.questions(plain, "plan a trip", make_idx(plain))
    assert "vault" not in q
    with_vault = cat_with(skills=["vault"])
    q, keymap = route.questions(with_vault, "plan a trip", make_idx(with_vault))
    assert q["vault"]["type"] == "noul" and "vault" in keymap.values()


def test_question_instructions_are_static_and_hold_no_catalog_ids(env):
    a = cat_with(agents=["herow-core:debugger"], skills=["herow-dev:quick"])
    b = cat_with(agents=["other:agent"], skills=["vault", "other:skill"])
    qa, _ = route.questions(a, "fix a crash", make_idx(a))
    qb, _ = route.questions(b, "fix a crash", make_idx(b))
    for k in ("agent", "skill"):
        assert qa[k]["instructions"] == qb[k]["instructions"]
        text = qa[k]["instructions"] + qb[k]["instructions"]
        assert not any(
            n in text
            for n in (
                "herow-core:debugger",
                "herow-dev:quick",
                "other:agent",
                "other:skill",
            )
        )


# postfilter gating

FIN_PERSONAL = "Analyze my budget and cash flow in Organizze"
FIN_MARKET = "Research the pricing and market for CRM tools"


def test_postfilter_personal_finance_needs_financial_analyst(env):
    notes = []
    cat = cat_with(agents=["herow-finance:financial-analyst"])
    assert (
        route.postfilter(FIN_PERSONAL, "general-purpose", "none", notes, cat)[0]
        == "herow-finance:financial-analyst"
    )
    assert notes
    notes = []
    only_dev = cat_with(agents=["herow-dev:search-specialist"])
    assert (
        route.postfilter(FIN_PERSONAL, "general-purpose", "none", notes, only_dev)[0]
        == "general-purpose"
    )
    assert notes == []


def test_postfilter_market_needs_search_specialist(env):
    cat = cat_with(agents=["herow-dev:search-specialist"])
    assert (
        route.postfilter(FIN_MARKET, "general-purpose", "none", [], cat)[0]
        == "herow-dev:search-specialist"
    )
    only_fin = cat_with(agents=["herow-finance:financial-analyst"])
    assert (
        route.postfilter(FIN_MARKET, "general-purpose", "none", [], only_fin)[0]
        == "general-purpose"
    )


def test_postfilter_ignores_non_general_purpose(env):
    cat = cat_with(agents=["herow-finance:financial-analyst"])
    assert route.postfilter(FIN_PERSONAL, "Explore", "none", [], cat)[0] == "Explore"


# local rewrites

REWRITE = {
    "when_skill": "old-skill",
    "task_regex": r"(?i)\bcompany\b",
    "to_skill": "new-skill",
}


def test_rewrite_applies_when_target_installed(env):
    env.config({"rewrites": [REWRITE]})
    cat = cat_with(skills=["old-skill", "new-skill"])
    notes = []
    _, skill = route.postfilter(
        "file a company receipt", "none", "old-skill", notes, cat
    )
    assert skill == "new-skill" and notes


def test_rewrite_skipped_without_target_or_match(env):
    env.config({"rewrites": [REWRITE]})
    assert (
        route.postfilter(
            "company receipt", "none", "old-skill", [], cat_with(skills=["old-skill"])
        )[1]
        == "old-skill"
    )
    both = cat_with(skills=["old-skill", "new-skill"])
    assert (
        route.postfilter("personal receipt", "none", "old-skill", [], both)[1]
        == "old-skill"
    )
    assert route.postfilter("company receipt", "none", "other", [], both)[1] == "other"


def test_rewrite_invalid_regex_skipped_with_warning(env, capsys):
    env.config({"rewrites": [{**REWRITE, "task_regex": "("}]})
    cat = cat_with(skills=["old-skill", "new-skill"])
    assert route.postfilter("company", "none", "old-skill", [], cat)[1] == "old-skill"
    assert "invalid" in capsys.readouterr().err.lower()


# evaluation: N/A, gate, floor


def row(task, agent="none", skill="none", unc=(), vault=None, shortlist=("none",)):
    r = {
        "task": task,
        "agent": agent,
        "agent_conf": 0.9,
        "skill": skill,
        "skill_conf": 0.9,
        "uncertain": list(unc),
        "shortlist": list(shortlist),
    }
    if vault is not None:
        r.update(vault_first=vault >= 0.6, vault_p=vault)
    return r


CAT = cat_with(agents=["herow-core:debugger"], skills=["herow-dev:quick"])


def cases_rows(n, miss=0, unc=0, key="agent"):
    cases, rows = [], []
    for i in range(n):
        cases.append(
            {"task": f"t{i}", "agent": ["herow-core:debugger"], "skill": ["none"]}
        )
        wrong = i < miss
        u = ["agent"] if miss <= i < miss + unc else []
        rows.append(
            row(f"t{i}", agent="Explore" if wrong else "herow-core:debugger", unc=u)
        )
    return cases, rows


def test_evaluate_counts_and_na(env):
    cases = [
        {"task": "a", "agent": ["herow-core:debugger"], "skill": ["none"]},
        {"task": "b", "agent": ["uninstalled:agent"], "skill": ["uninstalled-skill"]},
        {"task": "c", "agent": ["none"], "skill": ["herow-dev:quick"]},
    ]
    rows = [
        row("a", agent="herow-core:debugger"),
        row("b"),
        row("c", skill="herow-dev:quick"),
    ]
    res = route.evaluate(cases, rows, CAT)
    assert res["stats"]["agent"]["n"] == 2 and res["stats"]["agent"]["right"] == 2
    assert res["stats"]["skill"]["n"] == 2
    assert {n[0] for n in res["na"]} == {"b"} and len(res["na"]) == 2
    assert res["errors"] == []


def test_evaluate_vault_na_without_vault_skill(env):
    cases = [{"task": "a", "agent": ["none"], "skill": ["none"], "vault": True}]
    res = route.evaluate(cases, [row("a")], CAT)
    assert res["stats"]["vault"]["n"] == 0
    assert any(m == "vault" for _, m, _ in res["na"])


def test_evaluate_vault_scored_when_asked(env):
    cases = [{"task": "a", "agent": ["none"], "skill": ["none"], "vault": True}]
    res = route.evaluate(cases, [row("a", vault=0.9)], CAT)
    assert res["stats"]["vault"]["right"] == 1 and res["stats"]["vault"]["n"] == 1


def test_gate_pass_with_two_confident_misses_of_23(env):
    cases, rows = cases_rows(23, miss=2)
    ok, lines = route.verdict(route.evaluate(cases, rows, CAT), 0.9)
    assert ok and any("agent" in ln and "PASS" in ln for ln in lines)


def test_gate_fails_with_three_misses_of_23(env):
    cases, rows = cases_rows(23, miss=3)
    ok, lines = route.verdict(route.evaluate(cases, rows, CAT), 0.9)
    assert not ok and any("agent" in ln and "FAIL" in ln for ln in lines)


def test_gate_coverage_floor_all_uncertain_but_one(env):
    cases, rows = cases_rows(10, unc=9)
    res = route.evaluate(cases, rows, CAT)
    assert res["stats"]["agent"]["cok"] == 1 and res["stats"]["agent"]["cn"] == 1
    ok, lines = route.verdict(res, 0.9)
    assert not ok and any("coverage" in ln and "FAIL" in ln for ln in lines)


def test_gate_coverage_floor_boundary(env):
    ok, _ = route.verdict(route.evaluate(*cases_rows(100, unc=24), CAT), 0.9)
    assert ok
    ok, lines = route.verdict(route.evaluate(*cases_rows(100, unc=26), CAT), 0.9)
    assert not ok and any("coverage" in ln and "FAIL" in ln for ln in lines)


def test_gate_zero_confident_fails(env):
    cases, rows = cases_rows(5, unc=5)
    ok, lines = route.verdict(route.evaluate(cases, rows, CAT), 0.9)
    assert not ok


def test_gate_error_row_fails_even_if_metrics_pass(env):
    cases, rows = cases_rows(5)
    rows.append({"task": "bad", "error": "jev unavailable: 500 x"})
    cases.append({"task": "bad", "agent": ["none"], "skill": ["none"]})
    res = route.evaluate(cases, rows, CAT)
    ok, lines = route.verdict(res, 0.9)
    assert res["errors"] and not ok and any("error" in ln.lower() for ln in lines)


def test_gate_skips_metric_with_no_scored_cases(env):
    cases, rows = cases_rows(5)
    ok, lines = route.verdict(route.evaluate(cases, rows, CAT), 0.9)
    assert ok and not any(ln.startswith("GATE vault") for ln in lines)


def test_skip_case_handled(env):
    cases = [{"task": "/doctor", "skip": True, "agent": [], "skill": []}]
    rows = [{"task": "/doctor", "skip": "slash command: let the skill run"}]
    res = route.evaluate(cases, rows, CAT)
    assert res["bad_skips"] == 0


# run_eval end to end with a stubbed jev


def test_run_eval_portable_gate_exit_codes(env, fake_jev, tmp_path, capsys):
    herow = env.install_plugin("herow-core@herow", name="hc")
    env.add_agent(
        herow / "agents", "debugger", "Fix a crash: find the root cause of failures"
    )
    cases = [
        {
            "task": f"fix crash number {i}",
            "agent": ["herow-core:debugger"],
            "skill": ["none"],
        }
        for i in range(10)
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    fake_jev({c["task"]: {"agent": "herow-core:debugger"} for c in cases})
    assert route.run_eval(str(path), 0.7, portable=True, gate=0.9) is True
    assert "GATE agent: PASS" in capsys.readouterr().out
    fake_jev({c["task"]: {"agent": "Explore"} for c in cases})
    assert route.run_eval(str(path), 0.7, portable=True, gate=0.9) is False
    assert "FAIL" in capsys.readouterr().out


def test_run_eval_default_runs_portable_then_local_separately(
    env, fake_jev, tmp_path, monkeypatch, capsys
):
    herow = env.install_plugin("herow-core@herow", name="hc")
    env.add_agent(
        herow / "agents", "debugger", "Fix a crash: find the root cause of failures"
    )
    case = {"task": "fix crash", "agent": ["herow-core:debugger"], "skill": ["none"]}
    portable = tmp_path / "portable.json"
    portable.write_text(json.dumps([case]))
    monkeypatch.setattr(route, "EVAL_CASES", portable)
    (env.herow / "jev/cases.local.json").write_text(json.dumps([case]))
    fake_jev({"fix crash": {"agent": "herow-core:debugger"}})
    assert route.run_eval(None, 0.7, portable=False, gate=0.9) is True
    out = capsys.readouterr().out
    assert "== portable set" in out and "== local set" in out


def test_run_eval_default_without_local_runs_only_portable(
    env, fake_jev, tmp_path, monkeypatch, capsys
):
    herow = env.install_plugin("herow-core@herow", name="hc")
    env.add_agent(
        herow / "agents", "debugger", "Fix a crash: find the root cause of failures"
    )
    case = {"task": "fix crash", "agent": ["herow-core:debugger"], "skill": ["none"]}
    portable = tmp_path / "portable.json"
    portable.write_text(json.dumps([case]))
    monkeypatch.setattr(route, "EVAL_CASES", portable)
    fake_jev({"fix crash": {"agent": "herow-core:debugger"}})
    assert route.run_eval(None, 0.7, portable=False, gate=None) is True
    out = capsys.readouterr().out
    assert "== portable set" in out and "== local set" not in out


# output line format (REG-1)


def test_output_line_format(env, fake_jev, capsys):
    skills_dir = env.claude / "skills"
    env.add_skill(skills_dir, "vault", "Notes vault lookup")
    env.add_agent(env.claude / "agents", "debugger", "Debug crashes and stack traces")
    env.add_skill(skills_dir, "deploy-helper", "Debug crash reports from production")
    fake_jev(
        {
            "debug the crash": {
                "agent": "debugger",
                "skill": "deploy-helper",
                "skill_conf": 0.5,
                "vault": 0.9,
            }
        }
    )
    rows, totals = route.route(["debug the crash"], 0.7)
    route.print_rows(rows, totals)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == (
        "debug the crash | agent=debugger (0.95) | skill=deploy-helper (0.50) | "
        "alt=none/none | vault-first | uncertain=skill"
    )
    assert out[1] == "-- 1 task(s), 2 ms, cost 0.0001, fake-model"


def test_output_line_has_no_vault_flag_without_vault_skill(env, fake_jev, capsys):
    fake_jev({"hello there": {}})
    rows, totals = route.route(["hello there"], 0.7)
    route.print_rows(rows, totals)
    line = capsys.readouterr().out.splitlines()[0]
    assert "vault" not in line and line.startswith(
        "hello there | agent=none (0.95) | skill=none (0.95)"
    )


def test_slash_command_skipped_and_log_written(env, fake_jev, capsys):
    fake_jev({"do thing": {}})
    rows, _ = route.route(["/vault foo", "do thing"], 0.7)
    assert "skip" in rows[0]
    assert route.paths()["log"].read_text().count("\n") == 2


def test_jev_unavailable_message_not_doubled(env, monkeypatch, tmp_path):
    script = tmp_path / "failing_jev.py"
    script.write_text(
        'import sys\nsys.exit("jev unavailable: no key. Fix: do the thing")\n'
    )
    monkeypatch.setattr(route, "JEV", script)
    with pytest.raises(SystemExit) as exc:
        route.route(["anything"], 0.7)
    assert str(exc.value) == "jev unavailable: no key. Fix: do the thing"


# CLI entry points


def run_main(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["route.py", *argv])
    try:
        route.main()
    except SystemExit as e:
        return e.code
    return 0


def test_main_eval_gate_exit_codes(env, fake_jev, tmp_path, monkeypatch, capsys):
    herow = env.install_plugin("herow-core@herow", name="hc")
    env.add_agent(
        herow / "agents", "debugger", "Fix a crash: find the root cause of failures"
    )
    cases = [
        {"task": f"fix crash {i}", "agent": ["herow-core:debugger"], "skill": ["none"]}
        for i in range(5)
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    fake_jev({c["task"]: {"agent": "herow-core:debugger"} for c in cases})
    assert (
        run_main(monkeypatch, ["--eval", str(path), "--portable", "--gate", "0.9"]) == 0
    )
    fake_jev({c["task"]: {"agent": "Explore"} for c in cases})
    assert (
        run_main(monkeypatch, ["--eval", str(path), "--portable", "--gate", "0.9"]) == 1
    )
    assert run_main(monkeypatch, ["--eval", str(path), "--portable"]) == 0


def test_main_rebuild_and_routing_json(env, fake_jev, monkeypatch, capsys):
    fake_jev({"hello there": {}})
    assert run_main(monkeypatch, ["--rebuild"]) == 0
    assert "catalog:" in capsys.readouterr().out
    assert run_main(monkeypatch, ["--json", "hello there"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"][0]["task"] == "hello there"


def test_main_error_row_exits_one(env, fake_jev, monkeypatch, capsys):
    fake_jev({"boom": {"error": True}})
    assert run_main(monkeypatch, ["boom"]) == 1
    assert "jev unavailable: 500" in capsys.readouterr().out


def test_main_malformed_registry_exits_with_unavailable_line(env, monkeypatch):
    (env.claude / "plugins/installed_plugins.json").write_text("{x")
    code = run_main(monkeypatch, ["anything"])
    assert isinstance(code, str) and code.startswith("jev unavailable: ")


def test_frontmatter_block_scalar_description(env, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("---\nname: a\ndescription: |\n  line one\n  line two\n---\nbody")
    assert route.frontmatter(f)["description"] == "line one line two"


# cache invalidation tracks the files build_catalog reads


def rebuilt_after(env, mutate):
    route.load_catalog()
    built = json.loads(route.catalog_path().read_text())["built"]
    time.sleep(0.05)
    mutate()
    return route.load_catalog()["built"] > built


def test_cache_invalidated_by_in_place_agent_edit(env):
    env.add_agent(env.claude / "agents", "helper", "Old text")
    f = env.claude / "agents/helper.md"
    assert rebuilt_after(
        env, lambda: f.write_text("---\nname: helper\ndescription: New text\n---\n")
    )
    assert route.load_catalog()["agents"]["helper"] == "New text"


def test_cache_invalidated_by_project_skill_edit(env):
    env.add_skill(env.project / ".claude/skills", "proj", "Old")
    f = env.project / ".claude/skills/proj/SKILL.md"
    assert rebuilt_after(
        env, lambda: f.write_text("---\nname: proj\ndescription: New\n---\n")
    )


def test_cache_invalidated_by_new_command_in_existing_subfolder(env):
    env.add_command(env.claude / "commands", "ns/one.md", "One")
    assert rebuilt_after(
        env, lambda: env.add_command(env.claude / "commands", "ns/two.md", "Two")
    )
    assert "ns:two" in route.load_catalog()["skills"]


# malformed input and responses


def test_missing_agent_or_skill_answer_is_a_row_error(
    env, monkeypatch, tmp_path, capsys
):
    script = tmp_path / "half_jev.py"
    script.write_text(
        "import json, sys\n"
        "items = json.load(sys.stdin)['items']\n"
        "print(json.dumps({'results': [{'id': i['id'], 'answers': {'agent': {'choice': 'none'}},"
        " 'uncertain': [], 'model': 'm', 'cost': 0} for i in items], 'errors': [],"
        " 'totals': {'n': 1, 'wall_ms': 1, 'cost': 0}}))\n"
    )
    monkeypatch.setattr(route, "JEV", script)
    rows, _ = route.route(["do a thing"], 0.7)
    assert (
        rows[0]["error"]
        == "jev unavailable: malformed Jev response (missing agent/skill answer)"
    )


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"a": 1}', "[1, 2]"])
def test_empty_or_bad_stdin_exits_with_unavailable(env, monkeypatch, stdin):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = run_main(monkeypatch, [])
    assert code == "jev unavailable: no tasks given. Pass one summary per argument"
