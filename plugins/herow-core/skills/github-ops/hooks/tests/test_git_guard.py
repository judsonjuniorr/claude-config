#!/usr/bin/env python3
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(__file__), "..", "git-guard.sh")


def run(cmd):
    p = subprocess.run(
        ["bash", HOOK],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
    )
    o = p.stdout.strip()
    if not o:
        return "NO-DECISION"
    try:
        return json.loads(o)["hookSpecificOutput"]["permissionDecision"]
    except Exception:
        return "PARSE-ERR:" + o[:100]


# Placeholder script root — the hook matches on the `github-ops/scripts/<name>`
# path suffix, not an absolute prefix, so this doesn't need to be a real path.
root = "/x/skills/github-ops/scripts"
ATTR1 = (
    "Co-Authored-By" + ": Claude"
)  # split so this file doesn't itself read as a footer
ATTR2 = "generated with " + "claude" + " code"
ATTR3 = "claude" + " code"

must_allow_regression = [
    "gh pr view 42",
    "gh pr list",
    "gh pr view 42 | head -50",
    "gh pr diff 42",
    "gh run list --limit 5",
    "glab mr view 5",
    "rtk gh pr view 42",
    "gh pr view 42 > /tmp/pr.json",
    "gh pr view 42 --json title,body",
    'gh pr diff 42 | grep -c ""',
    "gh pr checks 42",
    "gh pr view 42 --web",
    "gh auth status",
    "gh workflow list",
    "gh run view 123 --log",
    "gh pr view 42 | sort -o /tmp/y",
    "gh pr list -L 5 | cat",
]

must_allow_fixed = [
    f'bash "{root}/pr.sh" view 42',
    f'bash "{root}/inspect.sh"',
    f'bash "{root}/repo.sh" runs',
    f'bash "{root}/commit-msg.sh"',
    f'bash "{root}/issue.sh" view 7',
    f'bash "{root}/issue.sh" list',
    f'bash "{root}/pr.sh" checks 42',
    f'bash "{root}/pr.sh" diff 42',
    f'bash "{root}/repo.sh" info',
    f'bash "{root}/repo.sh" releases',
    "gh api repos/o/r/pulls/42",
    "glab api projects/1",
    "gh status",
    "gh label list",
    "gh repo list",
    "gh cache list",
    "gh variable list",
    "gh secret list",
    "gh gist list",
    "gh browse",
    "gh extension list",
    "gh --version",
    "glab mr checks 5",
    "glab pipeline list",
    "rtk proxy gh pr view 42",
    'gh pr list --search "created:>2024-01-01"',
    # ro_re spot checks beyond the first sibling verb per branch.
    "gh pr status",
    "gh pr checkout 42",
    "gh issue view 7",
    "gh issue status",
    "gh release view v1",
    "gh release download v1",
    "gh run watch 123",
    "gh workflow view build.yml",
    "gh repo view",
    "gh search repos gstack",
    "glab mr list",
    "glab mr diff 5",
    "glab issue view 7",
    "glab issue list",
    "glab release list",
    "glab ci view 1",
    "glab ci trace 1",
    "glab repo view",
    "glab auth status",
    # safe_re pipe-target spot checks beyond cat/head/grep/sort/echo.
    "gh pr diff 42 | tail -5",
    "gh pr diff 42 | wc -l",
    "gh pr view 42 --json body | jq .body",
    'gh pr diff 42 | rg "^\\+"',
    "gh pr view 42 | git diff --stat",
    "gh pr view 42 | git show HEAD",
    "gh pr view 42 | git rev-parse HEAD",
    # de-quoting: single-quote form (only double-quote was tested before).
    "gh pr list --search 'created:>2024-01-01'",
    # mid-chain rtk-proxy prefix on a segment that ALSO calls a script.
    f'echo hi; rtk proxy bash "{root}/pr.sh" view 42',
    # stderr-to-devnull redirect must not defeat the read-only fast-allow.
    "gh pr view 42 2>/dev/null",
]

# Commands the hook must bail on entirely (perf-gate fast exit) — asserted
# as exact NO-DECISION, not folded into must_not_allow/must_not_deny.
must_bail_perf_gate = [
    "npm test",
    "cat a | grep b",
]

must_not_allow = [
    "gh pr merge 42 --squash",
    "gh api -X DELETE repos/o/r/issues/1",
    "gh api repos/o/r/issues -f title=x",
    "gh api --method=POST repos/o/r/issues",
    "gh api -X delete repos/o/r/issues/1",  # lowercase method must not slip through
    f'bash "{root}/ship.sh" --message "x"',
    f'bash "{root}/pr.sh" view 42; bash "{root}/ship.sh" --message x',
    "gh pr view 42; rm -rf /tmp/x",
    "gh pr view 42 | tee /tmp/x",
    # script_ro_re negative control: recognized script NAME, verb OUTSIDE the
    # read-only allowlist — proves the verb allowlist itself gates, not just
    # the script-name alternation (the only prior "script write" case was
    # rejected via an unrecognized script name, never exercising this axis).
    f'bash "{root}/pr.sh" merge 42',
    f'bash "{root}/issue.sh" close 7',
    f'bash "{root}/repo.sh" workflow-run somename',
    # Command-substitution guard, both directions.
    "gh $(echo pr view 42)",
    "gh pr view `echo 42`",
    "gh pr view 42 < <(echo x)",
    # Adversarial-review Finding 2: the /tmp-redirect tolerance must not
    # treat a path-traversal target as a plain tolerated /tmp filename.
    "gh pr view 42 > /tmp/../../../etc/passwd-test",
    "gh pr diff 16 > /tmp/../../Users/x/.ssh/id_rsa.pub",
]

must_not_deny = [
    # Boundary-collision repros from the testing-specialist finding: `-m` and
    # verb-name substrings must not fire the attribution deny on unrelated
    # tools/verbs.
    f'rg -m 1 "{ATTR3}" CHANGELOG.md',
    "find . -mtime -1 | grep anthropic",
    "gh pr reviews 42 --repo anthropics/claude-code",  # `review` must not prefix-match `reviews`
    f'gh pr view 42 && echo hi | grep -i "{ATTR3}"',
]

must_deny = [
    f'git commit -m "fix stuff {ATTR1}"',
    f'bash "{root}/ship.sh" --message "feat: x {ATTR1}"',
    f'bash "{root}/pr.sh" edit 42 --body "{ATTR2}"',
    # Mutating-verb path (no -m/--message/--body flag involved at all) —
    # spot-check across gh and glab, pr/issue/release/mr.
    f'gh pr create --title "mentions {ATTR3}"',
    f'gh pr edit 42 --title "mentions {ATTR3}"',
    f'gh pr comment 42 --body "mentions {ATTR3}"',
    f'gh pr review 42 --approve --body "mentions {ATTR3}"',
    f'gh issue create --title "mentions {ATTR3}"',
    f'gh issue comment 7 --body "mentions {ATTR3}"',
    f'gh release create v1 --notes "mentions {ATTR3}"',
    f'glab mr create --description "mentions {ATTR3}"',
    f'glab issue create --description "mentions {ATTR3}"',
    # Adversarial-review Finding 1: a wrapper script invoked by a RELATIVE
    # path or bare filename (no `github-ops/scripts/` literal in the
    # string) must still trip the attribution deny — issue.sh has no
    # scrub_body_file call of its own, so this hook is its only defense.
    f'bash scripts/ship.sh -m "x {ATTR1}"',
    f'bash issue.sh create --title t --body "x {ATTR1}"',
    f'bash issue.sh comment 7 --body "x {ATTR2}"',
]


def report(title, cases, expect_fn):
    print(f"=== {title} ===")
    ok = True
    for c in cases:
        d = run(c)
        good = expect_fn(d)
        if not good:
            ok = False
        print(f"{'OK ' if good else 'FAIL'} [{d:12}] {c[:95]}")
    return ok


def main():
    results = [
        report(
            "MUST ALLOW (regression)", must_allow_regression, lambda d: d == "allow"
        ),
        report("MUST ALLOW (newly fixed)", must_allow_fixed, lambda d: d == "allow"),
        report("MUST NOT ALLOW", must_not_allow, lambda d: d != "allow"),
        report("MUST NOT DENY", must_not_deny, lambda d: d != "deny"),
        report("MUST DENY", must_deny, lambda d: d == "deny"),
        report(
            "MUST BAIL (perf gate, exact NO-DECISION)",
            must_bail_perf_gate,
            lambda d: d == "NO-DECISION",
        ),
    ]
    total = sum(
        len(x)
        for x in [
            must_allow_regression,
            must_allow_fixed,
            must_not_allow,
            must_not_deny,
            must_deny,
            must_bail_perf_gate,
        ]
    )
    print()
    print(f"{total} cases")
    ok = all(results)
    print("ALL PASS" if ok else "SOME FAILURES ABOVE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
