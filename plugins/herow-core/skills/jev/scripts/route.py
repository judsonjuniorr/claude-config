#!/usr/bin/env python3
"""Suggest a subagent and a skill per task via Jev; advisory only.
Usage: route.py "task 1" ["task 2" ...] | route.py --eval [cases.json] | route.py --rebuild"""

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter

import jev_env

JEV = pathlib.Path(__file__).with_name("jev.py")
EVAL_CASES = pathlib.Path(__file__).parent.parent / "eval/routing-cases.json"
DESC_MAX = 300

BUILTIN_AGENTS = {
    "general-purpose": "Multi-step research, code search or execution that matches no specialist; 'where is X' across a codebase.",
    "Explore": "Read-only broad codebase search to locate files, symbols or conventions; returns conclusions, not edits.",
    "Plan": "Designs an implementation plan for a coding task: steps, critical files, trade-offs. No edits.",
    "claude-code-guide": "Questions about Claude Code itself, the Claude Agent SDK or the Claude API: features, hooks, settings, MCP.",
}

# Shipped inside Claude Code, so there is no SKILL.md on disk to read.
BUILTIN_SKILLS = {
    "code-review": "Review the current diff, a PR number or branch for correctness bugs at a chosen effort level.",
    "simplify": "Review changed code for reuse, simplification and efficiency cleanups, then apply them. Not a bug hunt.",
    "security-review": "Security review of the pending changes on the current branch.",
    "run": "Launch and drive this project's app to see a change working, or screenshot it.",
    "loop": "Run a prompt or slash command on a recurring interval, or poll a status repeatedly.",
    "schedule": "Create or manage scheduled cloud agents (cron routines), or a one-time scheduled run.",
    "claude-api": "Building with the Claude API or Anthropic SDK: model ids, pricing, tool use, caching, agents.",
    "update-config": "Configure Claude Code settings.json: hooks, permissions, env vars, automated behaviors.",
    "dataviz": "Create any chart, graph, plot, dashboard or data visualization in any medium (HTML, React, matplotlib, SVG).",
    "anthropic-skills:deep-research": "Research a topic across many sources and synthesize a narrative report.",
    "anthropic-skills:docs": "Write a shareable document: report, proposal, guide, letter, resume.",
    "anthropic-skills:pdf": "Read, create or edit PDF files.",
    "anthropic-skills:xlsx": "Create or edit Excel spreadsheets.",
    "anthropic-skills:pptx": "Create or edit PowerPoint decks.",
    "anthropic-skills:docx": "Create or edit Word .docx files when Word is named explicitly.",
    "anthropic-skills:skill-creator": "Create, modify, evaluate or tune a Claude Code skill.",
}

FINANCE = re.compile(
    r"(?i)\b(financ|organizze|ynab|budget|or[cç]amento|fatura|invoice|cash ?flow|"
    r"fluxo de caixa|debt|d[ií]vida|invest(?!igat)|patrim|saldo|extrato|market(?!place)|mercado|pricing|pre[cç]o)"
)
PERSONAL_FINANCE = re.compile(
    r"(?i)\b(organizze|ynab|budget|cash ?flow|debt|saldo|extrato|patrim|invest|fire)\b"
)
NF_PJ = re.compile(r"(?i)\b(pj|cnpj|empresa|company|herow|contabilizei|tomad)")


def paths():
    """Resolved at call time so HOME, HEROW_HOME and CLAUDE_CONFIG_DIR changes (and tests) apply."""
    claude, herow = jev_env.claude_dir(), jev_env.herow_home()
    return {
        "home": pathlib.Path.home(),
        "claude": claude,
        "herow": herow,
        "cache": herow / "jev/cache",
        "log": herow / "jev/route.log",
        "registry": jev_env.registry_path(),
        "settings": jev_env.settings_path(),
        "config": herow / "jev/config.json",
        "cases_local": herow / "jev/cases.local.json",
    }


def read_config():
    return jev_env.load_config()


def extra_command_dirs():
    # JEV_EXTRA_COMMAND_DIRS replaces the config value; set-but-empty means no extras.
    env = os.environ.get("JEV_EXTRA_COMMAND_DIRS")
    raw = (
        [d for d in env.split(os.pathsep) if d]
        if env is not None
        else read_config().get("extra_command_dirs", [])
    )
    if not isinstance(raw, list):
        raw = []
    return [
        pathlib.Path(os.path.expandvars(os.path.expanduser(str(d)))) for d in raw if d
    ]


def command_dirs():
    return [
        paths()["claude"] / "commands",
        pathlib.Path(".claude/commands"),
        *extra_command_dirs(),
    ]


def frontmatter(path):
    text = path.read_text(errors="replace")
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out, lines = {}, m.group(1).splitlines()
    i = 0
    while i < len(lines):
        km = re.match(r"^([\w-]+):\s*(.*)$", lines[i])
        i += 1
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        # YAML block scalars (description: | or >) carry the text on indented lines.
        if val in ("", "|", ">", "|-", ">-"):
            block = []
            while i < len(lines) and (
                lines[i].startswith((" ", "\t")) or not lines[i].strip()
            ):
                block.append(lines[i].strip())
                i += 1
            val = " ".join(b for b in block if b)
        out[key] = val.strip("'\"")
    return out


def trim(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= DESC_MAX else s[: DESC_MAX - 1] + "…"


def plugin_installs():
    return [(name, path) for name, path, _ in jev_env.plugin_installs()]


def build_catalog():
    p = paths()
    settings = jev_env.load_json_file(p["settings"])
    disabled = {
        k for k, v in (settings.get("skillOverrides") or {}).items() if v == "off"
    }
    agents = dict(BUILTIN_AGENTS)
    skills = dict(BUILTIN_SKILLS)
    herow = {"agents": [], "skills": []}

    for d in (pathlib.Path(".claude/agents"), p["claude"] / "agents"):
        for f in sorted(d.glob("*.md")) if d.is_dir() else []:
            fm = frontmatter(f)
            agents.setdefault(fm.get("name") or f.stem, trim(fm.get("description")))

    for d in (pathlib.Path(".claude/skills"), p["claude"] / "skills"):
        for f in sorted(d.glob("*/SKILL.md")) if d.is_dir() else []:
            fm = frontmatter(f)
            name = fm.get("name") or f.parent.name
            if name not in disabled and f.parent.name not in disabled:
                skills.setdefault(name, trim(fm.get("description")))

    for d in command_dirs():
        for f in sorted(d.glob("**/*.md")) if d.is_dir() else []:
            rel = f.relative_to(d).with_suffix("")
            skills.setdefault(
                ":".join(rel.parts), trim(frontmatter(f).get("description"))
            )

    for plug, root, full in jev_env.plugin_installs():
        is_herow = full.endswith("@herow")
        found = []
        for f in sorted(root.glob("agents/*.md")):
            fm = frontmatter(f)
            name = f"{plug}:{fm.get('name') or f.stem}"
            agents.setdefault(name, trim(fm.get("description")))
            found.append(("agents", name))
        for f in sorted(root.glob("skills/*/SKILL.md")):
            fm = frontmatter(f)
            name = f"{plug}:{fm.get('name') or f.parent.name}"
            skills.setdefault(name, trim(fm.get("description")))
            found.append(("skills", name))
        for f in sorted(root.glob("commands/**/*.md")):
            rel = f.relative_to(root / "commands").with_suffix("")
            name = f"{plug}:{':'.join(rel.parts)}"
            skills.setdefault(name, trim(frontmatter(f).get("description")))
            found.append(("skills", name))
        if is_herow:
            for kind, name in found:
                herow[kind].append(name)

    catalog = {"built": time.time(), "agents": agents, "skills": skills, "herow": herow}
    write_catalog(catalog)
    return catalog


def write_catalog(catalog):
    """Write via a temp file in the same dir so a concurrent reader never sees a partial catalog."""
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".catalog-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(catalog, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def portable_view(cat):
    """In-memory subset: herow marketplace components plus built-ins. Never cached."""
    herow = cat.get("herow") or {}
    keep_a = set(BUILTIN_AGENTS) | set(herow.get("agents", []))
    keep_s = set(BUILTIN_SKILLS) | set(herow.get("skills", []))
    return {
        **cat,
        "agents": {n: d for n, d in cat["agents"].items() if n in keep_a},
        "skills": {n: d for n, d in cat["skills"].items() if n in keep_s},
    }


def catalog_path():
    # Project agents, skills and project-scoped plugins differ per directory.
    return (
        paths()["cache"]
        / f"catalog-{hashlib.sha1(str(pathlib.Path.cwd()).encode()).hexdigest()[:10]}.json"
    )


def sources_mtime():
    p = paths()
    watched = [
        pathlib.Path(__file__),
        p["registry"],
        p["settings"],
        p["config"],
        p["claude"] / "skills",
        p["claude"] / "agents",
        pathlib.Path(".claude/agents"),
        pathlib.Path(".claude/skills"),
        *command_dirs(),
    ]
    # Same files build_catalog reads: editing one in place doesn't touch its dir's mtime.
    for d in (p["claude"] / "agents", pathlib.Path(".claude/agents")):
        watched += d.glob("*.md")
    for d in (p["claude"] / "skills", pathlib.Path(".claude/skills")):
        watched += d.glob("*/SKILL.md")
    for d in command_dirs():
        watched += d.glob("**")
        watched += d.glob("**/*.md")
    return max((q.stat().st_mtime for q in watched if q.exists()), default=0)


def load_catalog(force=False):
    path = catalog_path()
    if not force and path.is_file():
        try:
            cat = json.loads(path.read_text())
            if (
                isinstance(cat, dict)
                and "herow" in cat
                and cat.get("built", 0) >= sources_mtime()
            ):
                return cat
        except (OSError, ValueError, TypeError):
            pass  # a corrupt or partial cache counts as stale
    return build_catalog()


def get_catalog(portable=False):
    cat = load_catalog()
    return portable_view(cat) if portable else cat


TOP_AGENTS, TOP_SKILLS = 8, 15
ALWAYS_AGENTS = ("general-purpose", "Explore")
# A vault skill's description is phrased as questions, so lexical match misses it; skipped when not installed.
ALWAYS_SKILLS = ("vault",)
STOP = set(
    "the and for with that this from into when use used uses using user users skill skills task tasks "
    "claude code any all are not its it's you your via run runs then than also only one two can "
    "should will what which who how does each per before after about over under more most".split()
)
# pt-BR descriptions and summaries share no words with English ones; bridge the common domain terms.
SYNONYMS = {
    "concili": "reconcile reconciliation statement bank balance match",
    "extrato": "statement bank",
    "fatura": "invoice credit card statement bill",
    "nota fiscal": "invoice receipt purchase",
    "sincroniz": "sync",
    "viage": "travel trip flight hotel",
    "orcament": "budget",
    "lancament": "transaction entry",
    "baixar": "download",
    "curso": "course",
    "arquiv": "file archive store",
    "despesa": "expense",
    "agenda": "calendar schedule",
    "corrig": "fix bug",
    "relatorio": "report",
}


def tokens(text):
    text = (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )
    text += " " + " ".join(v for k, v in SYNONYMS.items() if k in text)
    words = (
        w[:-1] if len(w) > 3 and w.endswith("s") else w
        for w in re.findall(r"[a-z][a-z0-9]{2,}", text)
    )
    return [w[:6] for w in words if w not in STOP]


def index(options):
    docs = {
        n: tokens(re.sub(r"[:_-]", " ", n) * 2 + " " + d) for n, d in options.items()
    }
    df = Counter(t for d in docs.values() for t in set(d))
    avg = sum(map(len, docs.values())) / max(1, len(docs))
    return (
        docs,
        {t: math.log(1 + (len(docs) - c + 0.5) / (c + 0.5)) for t, c in df.items()},
        avg,
    )


def shortlist(task, options, idx, k, always=()):
    # BM25 over name + description; only the top k reach Jev.
    docs, idf, avg = idx
    q = set(tokens(task))
    scores = {}
    for n, d in docs.items():
        tf = Counter(d)
        scores[n] = sum(
            idf.get(t, 0) * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avg))
            for t in q
            if t in tf
        )
    ranked = [n for n in sorted(scores, key=lambda n: -scores[n]) if scores[n] > 0][:k]
    return ranked + [a for a in always if a in options and a not in ranked]


def questions(cat, task, idx):
    agents = shortlist(task, cat["agents"], idx["agents"], TOP_AGENTS, ALWAYS_AGENTS)
    skills = shortlist(task, cat["skills"], idx["skills"], TOP_SKILLS, ALWAYS_SKILLS)
    akeys = {f"a{i}": n for i, n in enumerate(agents, 1)}
    skeys = {f"s{i}": n for i, n in enumerate(skills, 1)}
    q = {
        "agent": {
            "type": "choice",
            "instructions": "Which subagent should Claude delegate this task to? Pick 'none' when the task is a single small edit, a question answerable directly, a chore run end to end by a dedicated workflow (reconciling a statement, syncing a budget, filing a receipt, planning a trip, fixing dependency CVEs, drawing a chart), or no agent's description fits.",
            "criteria": {
                **{k: f"{n}: {cat['agents'][n]}" for k, n in akeys.items()},
                "none": "No subagent; Claude does it inline.",
            },
        },
        "skill": {
            "type": "choice",
            "instructions": "Which skill's description best covers this task? Pick a skill only when its description names this kind of task; a reference skill about patterns is not a review. Pick 'none' unless one skill clearly matches.",
            "criteria": {
                **{k: f"{n}: {cat['skills'][n]}" for k, n in skeys.items()},
                "none": "No skill fits.",
            },
        },
    }
    if "vault" in cat["skills"]:
        q["vault"] = {
            "type": "noul",
            "instructions": "Does this task touch the user's personal life or a named project that may have earlier notes (trip, calendar, purchase, person, family, health, finances, or an ongoing project)?",
            "criteria": {
                "true": "Personal matter or named project with possible history.",
                "false": "Generic coding or a question with no personal or project history.",
            },
        }
    return q, {**akeys, **skeys, "none": "none"}


def top(answer, keymap):
    probs = sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
    alt = next((keymap.get(k, k) for k, _ in probs[1:2]), None)
    return (
        keymap.get(answer.get("choice"), answer.get("choice")),
        answer.get("confidence"),
        alt,
    )


LOG_MAX_BYTES = 1_000_000


def write_log(log, rows):
    import jev

    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
        os.replace(log, log.with_suffix(".log.1"))
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        for row in rows:
            entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **row, "task": jev.redact_br(row["task"])}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def postfilter(task, agent, skill, notes, cat):
    """Rules a description match can miss; each rewrite applies only when its target is installed."""
    if agent == "general-purpose" and FINANCE.search(task):
        target = (
            "herow-finance:financial-analyst"
            if PERSONAL_FINANCE.search(task)
            else "herow-dev:search-specialist"
        )
        if target in cat["agents"]:
            agent = target
            notes.append("general-purpose barred for finance/market")
    rewrites = read_config().get("rewrites", [])
    for rw in rewrites if isinstance(rewrites, list) else []:
        try:
            when, rx, to = rw["when_skill"], rw["task_regex"], rw["to_skill"]
            if skill == when and to in cat["skills"] and re.search(rx, task):
                skill = to
                notes.append(f"rewrite: {when} -> {to}")
        except (KeyError, TypeError):
            print(f"jev: skipping invalid rewrite entry {rw!r}", file=sys.stderr)
        except re.error as e:
            print(
                f"jev: skipping invalid rewrite regex {rw.get('task_regex')!r}: {e}",
                file=sys.stderr,
            )
    return agent, skill


def route(tasks, conf, dry_run=False, cat=None):
    cat = cat or load_catalog()
    idx = {"agents": index(cat["agents"]), "skills": index(cat["skills"])}
    out, items, keymaps = [], [], {}
    for i, t in enumerate(tasks):
        if t.lstrip().startswith("/"):
            out.append({"task": t, "skip": "slash command: let the skill run"})
            continue
        q, keymaps[str(i)] = questions(cat, t, idx)
        items.append({"id": str(i), "state": t, "questions": q})
        out.append({"task": t, "shortlist": list(keymaps[str(i)].values())})
    if not items:
        return out, None
    args = [
        sys.executable,
        str(JEV),
        "--redact-br",
        "--conf",
        str(conf),
        "--timeout",
        "10",
    ]
    if dry_run:
        args.append("--dry-run")
    r = subprocess.run(
        args,
        input=json.dumps({"items": items}),
        capture_output=True,
        text=True,
    )
    if dry_run:
        return None, r.stdout
    try:
        resp = json.loads(r.stdout)
    except json.JSONDecodeError:
        last = ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1]
        sys.exit(
            last if last.startswith("jev unavailable:") else f"jev unavailable: {last}"
        )
    for e in resp.get("errors", []):
        out[int(e["item_id"])]["error"] = (
            f"jev unavailable: {e['status']} {str(e['body'])[:200]}"
        )
    for res in resp.get("results", []):
        row = out[int(res["id"])]
        a = res.get("answers")
        if not (
            isinstance(a, dict)
            and isinstance(a.get("agent"), dict)
            and isinstance(a.get("skill"), dict)
        ):
            row["error"] = (
                "jev unavailable: malformed Jev response (missing agent/skill answer)"
            )
            continue
        keymap = keymaps[res["id"]]
        agent, aconf, aalt = top(a["agent"], keymap)
        skill, sconf, salt = top(a["skill"], keymap)
        notes = []
        agent, skill = postfilter(row["task"], agent, skill, notes, cat)
        vault = (a.get("vault") or {}).get("noul")
        row.update(
            agent=agent,
            agent_conf=aconf,
            agent_alt=aalt,
            skill=skill,
            skill_conf=sconf,
            skill_alt=salt,
            vault_first=vault is not None and vault >= 0.6,
            vault_p=vault,
            uncertain=[u for u in res["uncertain"] if u != "vault"],
            notes=notes,
            model=res["model"],
            cost=res["cost"],
            tokens=(res.get("usage") or {}).get("input_tokens"),
        )
    log = paths()["log"]
    try:
        write_log(log, out)
    except OSError as e:
        print(f"jev: could not write log {log}: {e}", file=sys.stderr)
    return out, resp.get("totals")


def fmt(v, c):
    return f"{v} ({c:.2f})" if c is not None else str(v)


def print_rows(rows, totals):
    for r in rows:
        if "skip" in r or "error" in r:
            print(f"{r['task']} | {r.get('skip') or r['error']}")
            continue
        unc = ",".join(r["uncertain"])
        parts = [
            r["task"],
            f"agent={fmt(r['agent'], r['agent_conf'])}",
            f"skill={fmt(r['skill'], r['skill_conf'])}",
            f"alt={r['agent_alt']}/{r['skill_alt']}",
        ]
        if r["vault_first"]:
            parts.append("vault-first")
        if unc:
            parts.append(f"uncertain={unc}")
        if r["notes"]:
            parts.append("rule: " + "; ".join(r["notes"]))
        print(" | ".join(parts))
    if totals:
        model = next((r["model"] for r in rows if r.get("model")), None)
        print(
            f"-- {totals['n']} task(s), {totals['wall_ms']} ms, cost {totals['cost']}, {model}"
        )


METRICS = ("agent", "skill", "vault")
COVERAGE_FLOOR = 0.75


def as_list(v):
    return v if isinstance(v, list) else [v]


def evaluate(cases, rows, cat):
    """Score rows against cases. A metric whose expected targets are all uninstalled is N/A, not a miss."""
    stats = {k: {"right": 0, "n": 0, "cok": 0, "cn": 0} for k in METRICS}
    installed = {
        "agent": set(cat["agents"]) | {"none"},
        "skill": set(cat["skills"]) | {"none"},
    }
    res = {
        "stats": stats,
        "na": [],
        "errors": [],
        "lines": [],
        "bad_skips": 0,
        "lost": 0,
        "tokens": [],
    }
    for c, r in zip(cases, rows):
        label = c["task"][:60]
        if "skip" in r:
            ok = bool(c.get("skip", False))
            res["bad_skips"] += not ok
            res["lines"].append(f"{'OK ' if ok else 'BAD'} {label} | skip")
            continue
        if "error" in r:
            res["errors"].append((c["task"], r["error"]))
            res["lines"].append(f"ERR {label} | {r['error']}")
            continue
        if r.get("tokens"):
            res["tokens"].append(r["tokens"])
        miss = []
        for k in ("agent", "skill"):
            want = as_list(c[k])
            if not set(want) & installed[k]:
                res["na"].append((c["task"], k, want))
                continue
            ok = r[k] in want
            confident = k not in r["uncertain"]
            s = stats[k]
            s["right"] += ok
            s["n"] += 1
            s["cok"] += ok and confident
            s["cn"] += confident
            if not ok:
                lost = set(want) & set(r["shortlist"] + ["none"])
                res["lost"] += not lost
                miss.append(
                    f"{k}={r[k]}({r[k + '_conf']}) want {want}{'' if lost else ' [not shortlisted]'}"
                )
        if "vault" in c:
            if r.get("vault_p") is None:
                res["na"].append((c["task"], "vault", c["vault"]))
            else:
                ok = r["vault_first"] == c["vault"]
                s = stats["vault"]
                s["right"] += ok
                s["n"] += 1
                s["cok"] += ok
                s["cn"] += 1
                if not ok:
                    miss.append(f"vault={r['vault_p']} want {c['vault']}")
        res["lines"].append(
            f"{'OK ' if not miss else 'BAD'} {label} | {'; '.join(miss)}"
        )
    return res


def verdict(res, gate):
    """PASS per metric needs confident accuracy >= gate AND confident n >= 75% of scored cases."""
    lines, ok = [], True
    for k in METRICS:
        s = res["stats"][k]
        if not s["n"]:
            continue
        acc = s["cok"] / s["cn"] if s["cn"] else 0.0
        cov = s["cn"] / s["n"]
        problems = []
        if not s["cn"] or acc < gate:
            problems.append(f"accuracy {acc:.0%} < {gate:.0%}")
        if cov < COVERAGE_FLOOR:
            problems.append(f"coverage {cov:.0%} < {COVERAGE_FLOOR:.0%}")
        ok &= not problems
        detail = f"confident {s['cok']}/{s['cn']} = {acc:.0%}, coverage {s['cn']}/{s['n']} = {cov:.0%}"
        lines.append(
            f"GATE {k}: {'FAIL' if problems else 'PASS'} ({detail}{'; ' + '; '.join(problems) if problems else ''})"
        )
    if res["errors"]:
        ok = False
        lines.append(
            f"GATE errors: FAIL ({len(res['errors'])} error row(s), e.g. {res['errors'][0][1][:120]})"
        )
    if not any(res["stats"][k]["n"] for k in METRICS):
        ok = False
        lines.append("GATE: FAIL (no scored cases)")
    return ok, lines


def report(res, totals):
    print("\n".join(res["lines"]))
    print()
    for k, s in res["stats"].items():
        if s["n"]:
            cacc = s["cok"] / s["cn"] if s["cn"] else 0
            print(
                f"{k}: top1 {s['right']}/{s['n']} = {s['right'] / s['n']:.0%} | confident {s['cok']}/{s['cn']} = {cacc:.0%} | uncertain {s['n'] - s['cn']}"
            )
    for task, metric, want in res["na"]:
        print(f"N/A {metric}: {task[:60]} (none of {want} installed)")
    toks = res["tokens"]
    print(
        f"shortlist misses: {res['lost']} | avg input tokens {sum(toks) // max(1, len(toks))}"
    )
    if totals:
        print(
            f"-- {totals['n']} case(s), {totals['wall_ms']} ms, cost {totals['cost']}"
        )


def eval_one(path, conf, portable, gate, label):
    try:
        cases = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"jev: cannot read eval cases {path}: {e}")
    cat = get_catalog(portable)
    print(
        f"== {label} ({'herow components + built-ins' if portable else 'full installed catalog'}) =="
    )
    rows, totals = route([c["task"] for c in cases], conf, cat=cat)
    res = evaluate(cases, rows, cat)
    report(res, totals)
    if gate is None:
        return True
    ok, lines = verdict(res, gate)
    print("\n".join(lines))
    return ok


def run_eval(path, conf, portable=False, gate=None):
    """Bare --eval: bundled portable set, then the local set if present. Each set is reported separately."""
    if path:
        sets = [(path, portable, path)]
    else:
        sets = [(str(EVAL_CASES), True, "portable set")]
        if paths()["cases_local"].is_file():
            sets.append((str(paths()["cases_local"]), False, "local set"))
    results = [eval_one(p, conf, port, gate, label) for p, port, label in sets]
    return all(results)


def read_stdin_tasks():
    try:
        tasks = json.load(sys.stdin)
    except ValueError:
        tasks = None
    if not (
        isinstance(tasks, list) and tasks and all(isinstance(t, str) for t in tasks)
    ):
        sys.exit("jev unavailable: no tasks given. Pass one summary per argument")
    return tasks


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "tasks",
        nargs="*",
        help="one English summary per task (default: JSON list on stdin)",
    )
    p.add_argument("--conf", type=float, default=0.7)
    p.add_argument("--rebuild", action="store_true", help="rebuild the catalog")
    p.add_argument(
        "--eval",
        nargs="?",
        const="",
        metavar="CASES",
        help="run labelled cases: bare = portable set, then the local set if present",
    )
    p.add_argument(
        "--portable",
        action="store_true",
        help="with --eval CASES: use herow components + built-ins only",
    )
    p.add_argument(
        "--gate",
        type=float,
        metavar="MIN",
        help="with --eval: exit 1 unless every metric passes MIN",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the Jev request bodies; no call"
    )
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    try:
        if a.rebuild:
            cat = load_catalog(force=True)
            print(
                f"catalog: {len(cat['agents'])} agents, {len(cat['skills'])} skills -> {catalog_path()}"
            )
            if not a.tasks and a.eval is None:
                return
        if a.eval is not None:
            if not run_eval(a.eval or None, a.conf, a.portable, a.gate):
                sys.exit(1)
            return
        tasks = a.tasks or read_stdin_tasks()
        rows, totals = route(tasks, a.conf, a.dry_run)
    except jev_env.Unavailable as e:
        sys.exit(str(e))
    if a.dry_run:
        return print(totals)
    if a.json:
        return print(
            json.dumps({"rows": rows, "totals": totals}, indent=1, ensure_ascii=False)
        )
    print_rows(rows, totals)
    if any("error" in r for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
