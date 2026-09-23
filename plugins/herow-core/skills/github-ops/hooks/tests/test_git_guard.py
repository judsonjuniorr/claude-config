#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
import time

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
    # script_allow_re spot check: pr.sh's other read-only verb (list) beyond
    # view/checks/diff was untested.
    f'bash "{root}/pr.sh" list',
]

# Commands the hook must bail on entirely (perf-gate fast exit) — asserted
# as exact NO-DECISION, not folded into must_not_allow/must_not_deny.
must_bail_perf_gate = [
    "npm test",
    "cat a | grep b",
]

# Read-only / non-destructive-write commands that fail the tier-1/2 fast-allow
# (piped to an unrecognized helper, `;`/`|` inside a quoted arg) must now fall
# through to NO-DECISION instead of getting an `ask` nudging toward a script
# that has nothing to do with them — see destructive_re in git-guard.sh.
must_no_decision_nondestructive = [
    # Verbatim repro of the reported prompt: a read-only `gh pr list` piped to
    # python3 (not in safe_re) got an `ask` suggesting pr.sh, which is
    # unrelated to a list command.
    "gh pr list --author @me --state open --json number,title,headRefName,baseRefName --limit 50 2>&1 "
    '| python3 -c "import json,sys; d=json.load(sys.stdin); '
    "[print(p['number'], '|', p['title']) for p in d]\"",
    "gh pr view 42 | bat",
    "gh issue list | python3 -c \"print('hi')\"",
    # Quoted-delimiter gap (documented above the segment-split loop), on the
    # non-destructive write tier this time — distinct from the must_not_allow
    # cases pinned below, which are all destructive/attacker-shaped.
    'gh issue comment 7 --body "a | b"',
]

must_not_allow = [
    "gh api -X DELETE repos/o/r/issues/1",
    "gh api repos/o/r/issues -f title=x",
    "gh api --method=POST repos/o/r/issues",
    "gh api -X delete repos/o/r/issues/1",  # lowercase method must not slip through
    f'bash "{root}/ship.sh" --message "x"',
    f'bash "{root}/pr.sh" view 42; bash "{root}/ship.sh" --message x',
    "gh pr view 42; rm -rf /tmp/x",
    "gh pr view 42 | tee /tmp/x",
    # script_allow_re negative control: recognized script NAME, verb OUTSIDE
    # the allowlist — proves the verb allowlist itself gates, not just the
    # script-name alternation (the only prior "script write" case was
    # rejected via an unrecognized script name, never exercising this axis).
    f'bash "{root}/pr.sh" merge 42',
    f'bash "{root}/issue.sh" close 7',
    # Command-substitution guard, both directions.
    "gh $(echo pr view 42)",
    "gh pr view `echo 42`",
    "gh pr view 42 < <(echo x)",
    # Adversarial-review Finding 2: the /tmp-redirect tolerance must not
    # treat a path-traversal target as a plain tolerated /tmp filename.
    "gh pr view 42 > /tmp/../../../etc/passwd-test",
    "gh pr diff 16 > /tmp/../../home/x/.ssh/id_rsa.pub",
    # Non-destructive-write guard: an allow-eligible verb chained with a
    # destructive command must not smuggle an allow for the whole chain.
    "gh pr ready 51; rm -rf /tmp/x",
    'gh pr comment 42 --body "$(cat x)"',
    "gh pr ready 51 > /etc/hosts",
    "gh pr ready 51 && rm -rf /tmp/x",
    "gh pr ready 51 || rm -rf /tmp/x",
    # KNOWN GAP, deliberately accepted (see git-guard.sh's comment above the
    # segment-split loop): a quoted --body/--message containing a real
    # `;`/`|`/`&`/newline still fragments and sinks an otherwise
    # write-tier-eligible command to non-allow. Four straight adversarial
    # review cycles each broke a "smarter" quote-aware pre-split transform
    # meant to fix this (raw quote-count parity; per-type count +
    # backslash-adjacency; a full linear quote-state scanner; the same
    # scanner narrowed to bail on backslash/`$'`) — the last was defeated via
    # bash's `#` end-of-line comments. These cases pin each of those 4
    # confirmed-live bypasses so the underlying vulnerability can never
    # silently return if a future change reintroduces quote-aware splitting
    # without re-reading this history.
    'gh pr comment 42 --body \\"; rm -rf /tmp/x; echo \\"',
    "gh pr comment 42 --body \\'; rm -rf /tmp/x; echo \\'",
    'gh pr comment 42 --body "unterminated; rm -rf /tmp/x',
    'gh pr comment 42 --body "it\'s" --other "arg" ; rm -rf /tmp/x ; echo "can\'t"',
    'glab mr note 5 --message "ok\'s fine" ; git push --force origin main ; echo "done\'d"',
    "gh pr ready 51 $'a\\'b'; rm -rf /tmp/x \\'",
    "glab mr note 5 -m x $'a\\'b'; git push --force origin main \\'",
    'gh pr comment 42 --body "a; b" \\\\',
    "gh pr comment 42 --body \"x\" #'\ngh pr close 99\n#'",
    'gh pr comment 42 --body "linha1; linha2 | x"',
    'gh pr comment 42 --body "line1\nline2\nline3"',
    'gh pr comment 42 --body "it\'s fine; ship it"',
    f'bash "{root}/pr.sh" ready 51 --body "a; b | c"',
]

# Destructive/identity-shaping verbs that must keep asking even after the
# non-destructive-write tier was added — these are exactly the verbs the user
# chose to keep confirmation on.
must_ask = [
    "gh pr merge 42 --squash",
    "gh pr create --title x",
    "gh issue close 7",
    "gh release delete v1",
    "gh run cancel 1",
    "glab mr update 5",
    # delete/delete-asset boundary: destructive_re must not let `delete`
    # prefix-match `delete-asset` (which is listed explicitly, same tier).
    "gh release delete-asset v1 file.zip",
    # destructive_re is unanchored: the destructive verb must still be found
    # when it's not the first segment of a chain — a `^`-anchored version
    # would wrongly drop this to NO-DECISION.
    "gh pr list && gh pr merge 42",
    # The script suggestion is classified from the destructive segment, not the
    # command's first word — a non-gh first segment must not drop the ask.
    "cd /tmp && gh pr merge 42",
    "GH_REPO=a/b gh pr merge 42",
    "git push && gh pr create --title x",
    "true; gh issue close 7",
    "cd /tmp && glab mr update 5",
    # Separators with no surrounding whitespace still start a segment.
    "cd /tmp&&gh pr merge 1",
    "x=1;gh pr merge 1",
    "(gh pr merge 1)",
]

# Non-destructive gh/glab writes — newly allowed outright (no prompt), one
# tier below the destructive verbs in must_ask.
must_allow_writes = [
    # Verbatim repro of the reported prompt (rtk prefix, fd-dup, trailing
    # `echo "EXIT:$?"` — the shape essentially every gh call arrives in).
    'rtk gh pr ready 51 2>&1; echo "EXIT:$?"',
    "gh pr comment 42 --body x",
    "gh pr review 42 --approve",
    "gh issue comment 7 --body x",
    "gh run rerun 123",
    "gh workflow run build.yml",
    "glab mr note 5 -m x",
    "glab ci retry 1",
    f'bash "{root}/pr.sh" ready 51',
    f'bash "{root}/issue.sh" comment 7 --body x',
    f'bash "{root}/repo.sh" workflow-run somename',
    # write_allow_re full verb coverage — every alternative gets a positive
    # assertion so a future boundary/alternation slip is caught.
    "gh pr reopen 42",
    "gh pr lock 42",
    "gh pr unlock 42",
    "gh pr update-branch 42",
    "gh issue reopen 7",
    "gh issue pin 7",
    "gh issue unpin 7",
    "gh issue transfer 7 other-repo",
    "gh issue lock 7",
    "gh issue unlock 7",
    "gh issue develop 7",
    "gh release upload v1 file.tar.gz",
    "gh workflow enable build.yml",
    "gh workflow disable build.yml",
    "glab mr approve 5",
    "glab mr revoke 5",
    "glab mr rebase 5",
    "glab mr todo 5",
    "glab mr subscribe 5",
    "glab mr unsubscribe 5",
    "glab issue note 7 -m x",
    "glab issue reopen 7",
    "glab issue subscribe 7",
    "glab issue unsubscribe 7",
    "glab release upload v1 file.tar.gz",
    "glab ci run",
    "glab ci trigger 1",
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


# The writer delay MUST exceed the guard's bound, or the bound never fires and
# the stall cases degrade into ordinary-EOF tests that pass while covering
# nothing. BOUND_CEILING splits "bounded" from "waited for EOF" with margin.
STALL_WRITER_SLEEP = 5.0
BOUND_CEILING = 3.0


def shell_major(shell):
    """Probe the shell's bash major version. 0 = unavailable/unreadable.

    Never assumed: /bin/bash is bash 3.2 on stock macOS but bash 5 on Linux CI
    and on brew-linked Macs. The guard's bound no longer branches on the
    version (it lives inside the python3 call, which behaves the same on both),
    but the hook still has to work under either shell, so both are exercised.
    """
    try:
        r = subprocess.run(
            [shell, "-c", "echo ${BASH_VERSINFO[0]}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return int(r.stdout.strip())
    except Exception:
        return 0


# Probed ONCE. Three reporters used to re-probe the same two shells, paying six
# subprocesses to answer a question that cannot change mid-run, and each made
# its own decision about how to skip a missing shell.
SHELLS = [(s, m) for s in ("bash", "/bin/bash") for m in (shell_major(s),) if m]
SKIPPED_SHELLS = [s for s in ("bash", "/bin/bash") if s not in {x[0] for x in SHELLS}]


def _announce_skips():
    for s in SKIPPED_SHELLS:
        print(f"SKIP [{'n/a':12}] {s} unavailable or version unreadable")


def run_stalled(cmd, shell="bash"):
    """Run the hook with a LATE EOF, and report how long it took.

    The payload arrives immediately; the writer then holds the pipe open past
    the guard's bound before closing. That is the real stall shape the bounded
    read exists for -- a harness slow to CLOSE stdin, not slow to send -- so
    the decision must still be made from the payload that did arrive.

    Returns (decision, elapsed_seconds). The elapsed value is what pins the
    bound itself: without it, removing the deadline still passes, because the
    writer closes on its own and the decision comes out either way.

    The close MUST happen on a timer rather than after communicate(): an
    unbounded guard blocks until EOF, so closing afterwards would deadlock
    against exactly the regression this case exists to catch.
    """
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    r, w = os.pipe()
    try:
        p = subprocess.Popen([shell, HOOK], stdin=r, stdout=subprocess.PIPE, text=True)
    except BaseException:
        os.close(w)
        raise
    finally:
        os.close(r)

    os.write(w, payload.encode())
    # A plain is_set()/set() pair is not atomic, so the timer thread and the
    # finally block below could both reach os.close(w) and double-close a fd
    # that may since have been reused. The lock is what makes _close() the
    # idempotent thing its callers assume it is.
    close_lock = threading.Lock()
    closed = threading.Event()

    def _close():
        with close_lock:
            if not closed.is_set():
                closed.set()
                os.close(w)

    closer = threading.Timer(STALL_WRITER_SLEEP, _close)
    closer.start()
    t0 = time.monotonic()
    try:
        out = p.communicate(timeout=30)[0].strip()
    except subprocess.TimeoutExpired:
        # The guard hung. Kill it rather than leaking the child and its pipe --
        # and note a bare p.wait() here would raise a second TimeoutExpired
        # that masked the real failure.
        p.kill()
        out = (p.communicate()[0] or "").strip()
    finally:
        elapsed = time.monotonic() - t0
        closer.cancel()
        _close()
    if not out:
        return "NO-DECISION", elapsed
    try:
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"], elapsed
    except Exception:
        return "PARSE-ERR:" + out[:100], elapsed


def run_raw(payload_text, shell="bash"):
    """Feed raw bytes straight to the hook -- not a well-formed payload."""
    r = subprocess.run(
        [shell, HOOK],
        input=payload_text,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.stdout.strip() or "NO-DECISION", r.returncode


def report_stall():
    """Assert BOTH that the guard still decides under stall AND that the bound
    actually fired, per shell.

    The bound lives inside the guard's python3 call, which reads in blocks
    against a wall-clock deadline and keeps what arrived, so it behaves
    identically on bash 3.2 and bash 5 -- there is no version branch left to
    cover, only the two shells the hook must run under.
    """
    print("=== LATE-EOF STALL: still denies, and the bound is pinned ===")
    attributed = f'git commit -m "fix\n\n{ATTR1} <x@y>"'
    ok = True
    n = 0
    _announce_skips()
    for shell, maj in SHELLS:
        d, secs = run_stalled(attributed, shell)
        good = d == "deny"
        n += 1
        print(
            f"{'OK ' if good else 'FAIL'} [{d:12}] {shell} (bash {maj}): "
            f"attribution under stall, {secs:.1f}s"
        )
        bounded = secs < BOUND_CEILING
        n += 1
        print(
            f"{'OK ' if bounded else 'FAIL'} [{'bounded':12}] bash {maj}: "
            f"read returned in {secs:.1f}s "
            f"(ceiling {BOUND_CEILING}s, writer closes at {STALL_WRITER_SLEEP}s)"
            + ("" if bounded else "  -- the bound is GONE")
        )
        ok = ok and bounded and good
    if not SHELLS:
        # Zero coverage used to return ok=True with n=0: a green run that
        # exercised nothing at all.
        print("FAIL [no-shell    ] no usable bash found; the bound was never exercised")
        ok = False
        n += 1
    return ok, n


def report_size_bound():
    """A large payload over a PIPE must still produce a decision.

    Regression pin. A previous bound used bash `read -r -d '' -t 2`, which
    drains a non-seekable fd one byte per read(2) syscall (~1MB/s), turning a
    wall-clock bound into a payload-SIZE cap: past a couple of MB the JSON
    arrived truncated and the attribution deny was silently skipped. Reproduces
    only over a pipe -- with `< file` the fd is seekable and bash reads in bulk.
    """
    print("=== PAYLOAD SIZE must not bound the read ===")
    ok = True
    n = 0
    # The padding goes in a field the guard does not scan, NOT into the command
    # itself: a multi-MB single-line command trips a pre-existing quadratic
    # blowup in the downstream `grep -E` (minutes of CPU), which is an older,
    # separate problem and would mask what this case is about. What is under
    # test is the READ -- whether a 3MB payload reaches the parser intact.
    cmd = f'git commit -m "fix\\n\\n{ATTR1} <x@y>"'
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd, "_pad": "x" * 3_000_000}}
    )
    for shell, maj in SHELLS:
        p = subprocess.run(
            [shell, HOOK], input=payload, capture_output=True, text=True, timeout=60
        )
        o = p.stdout.strip()
        try:
            d = json.loads(o)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            d = "NO-DECISION" if not o else "PARSE-ERR"
        good = d == "deny"
        ok = ok and good
        n += 1
        print(
            f"{'OK ' if good else 'FAIL'} [{d:12}] {shell} (bash {maj}): "
            f"3MB payload over a pipe (command itself is small)"
        )
    return ok, n


def report_failopen():
    """Empty / malformed stdin must fail OPEN silently on every shell."""
    print("=== MUST FAIL OPEN (empty / malformed stdin, exit 0) ===")
    ok = True
    n = 0
    _announce_skips()
    for shell, _maj in SHELLS:
        for label, payload in (("empty stdin", ""), ("not json", "not json")):
            out, rc = run_raw(payload, shell)
            good = out == "NO-DECISION" and rc == 0
            ok = ok and good
            n += 1
            print(
                f"{'OK ' if good else 'FAIL'} [{out[:12]:12}] {shell}: {label} (exit {rc})"
            )
    return ok, n


def report_shell_parity():
    """An ordinary prompt-EOF payload must behave identically on both shells,
    and must NOT pay the bound -- this is ~100% of real calls."""
    print("=== SHELL PARITY (normal payload, both shells) ===")
    attributed = f'git commit -m "fix\n\n{ATTR1} <x@y>"'
    ok = True
    n = 0
    _announce_skips()
    for shell, maj in SHELLS:
        for cmd, want, what in (
            (attributed, "deny", "attribution denied"),
            ("gh pr view 42", "allow", "read-only fast-allow"),
        ):
            t0 = time.monotonic()
            p = subprocess.run(
                [shell, HOOK],
                input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                capture_output=True,
                text=True,
                timeout=30,
            )
            elapsed = time.monotonic() - t0
            o = p.stdout.strip()
            try:
                d = json.loads(o)["hookSpecificOutput"]["permissionDecision"]
            except Exception:
                d = "NO-DECISION" if not o else "PARSE-ERR"
            good = d == want
            ok = ok and good
            n += 1
            print(f"{'OK ' if good else 'FAIL'} [{d:12}] {shell} (bash {maj}): {what}")
            # A read that stopped seeing EOF would satisfy every assertion above
            # while making every single call wait the full bound.
            quick = elapsed < 1.0
            ok = ok and quick
            n += 1
            print(
                f"{'OK ' if quick else 'FAIL'} [{'immediate':12}] {shell}: "
                f"ordinary payload returned in {elapsed:.1f}s (no bound paid)"
            )
    return ok, n


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
        report(
            "MUST ALLOW (non-destructive writes)",
            must_allow_writes,
            lambda d: d == "allow",
        ),
        report("MUST NOT ALLOW", must_not_allow, lambda d: d != "allow"),
        report("MUST NOT DENY", must_not_deny, lambda d: d != "deny"),
        report("MUST DENY", must_deny, lambda d: d == "deny"),
        report("MUST ASK (destructive writes)", must_ask, lambda d: d == "ask"),
        report(
            "MUST BAIL (perf gate, exact NO-DECISION)",
            must_bail_perf_gate,
            lambda d: d == "NO-DECISION",
        ),
        report(
            "MUST NOT ASK (non-destructive fast-allow miss -> NO-DECISION)",
            must_no_decision_nondestructive,
            lambda d: d == "NO-DECISION",
        ),
    ]
    extra = [
        report_stall(),
        report_size_bound(),
        report_failopen(),
        report_shell_parity(),
    ]
    results += [r[0] for r in extra]
    extra_n = sum(r[1] for r in extra)
    total = extra_n + sum(  # extra_n: self-counted by the report_* helpers above
        len(x)
        for x in [
            must_allow_regression,
            must_allow_fixed,
            must_allow_writes,
            must_not_allow,
            must_not_deny,
            must_deny,
            must_ask,
            must_bail_perf_gate,
            must_no_decision_nondestructive,
        ]
    )
    print()
    print(f"{total} cases")
    ok = all(results)
    print("ALL PASS" if ok else "SOME FAILURES ABOVE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
