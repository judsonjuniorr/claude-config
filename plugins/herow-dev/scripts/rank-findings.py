#!/usr/bin/env python3
"""Deduplicate, filter, and rank code-review findings.

The deterministic half of `/herow-dev:code:review` Phase 3. Everything here is a pure
function of its input — grouping, dropping same-location duplicates, applying the effort
cutoff, applying Second Opinion verdicts, and rendering the count line. Choosing a
finding's initial level stays with the model; so does normalizing each agent's prose
into the JSON this script consumes.

Usage:
  rank-findings.py --findings FILE [--verdicts FILE] [--cutoff N]
                   [--line-window N] [--mode local|pr] [--json]

  --findings     JSON array of finding objects (or "-" for stdin).
  --verdicts     JSON array of Second Opinion verdicts. Omit when none were collected.
  --cutoff       Drop findings with confidence below this (default 0 = keep all).
  --line-window  Lines within which two same-class findings in one file collide
                 (default 3).
  --mode         Where the caller will place the count line (default local).
  --json         Emit a JSON object instead of pipe-delimited records.

Finding object:
  {"id": 1, "level": "High", "confidence": 85, "file": "a.ts", "line": 42,
   "title": "...", "issue": "...", "fix": "...",
   "class": "optional-issue-class", "memory": false}

  `level` accepts the emoji, the word, or both ("High", "🟠", "🟠 High").
  `class` defaults to a normalized `title` when absent.
  `memory` marks a memory-management finding (the 🧠 tag).

Verdict object:
  {"id": 1, "verdict": "CONFIRM|DISPUTE|ESCALATE", "note": "optional"}

Output (pipe-delimited, one record per line, most severe first):
  finding|<rank>|<emoji>|<level>|<memory>|<badge>|<verdict>|<fixable>|<confidence>|<file>|<line>|<title>|<note>
  count|<count line>
  count-position|last|after-decision
  dropped|duplicate|<n>
  dropped|cutoff|<n>
Warnings go to stderr as warn|<code>|<detail>.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Severity ladder, most severe first. Index is the sort key and the ESCALATE step.
LEVELS = [
    ("🔴", "Critical"),
    ("🟠", "High"),
    ("🟡", "Medium"),
    ("🟢", "Low"),
]
EMOJI_TO_IDX = {emoji: i for i, (emoji, _) in enumerate(LEVELS)}
WORD_TO_IDX = {word.lower(): i for i, (_, word) in enumerate(LEVELS)}

# Legacy vocabulary the agents used before the findings contract existed. Accepted so a
# stale agent definition degrades to a sane level instead of being dropped.
LEGACY_TO_IDX = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "suggestion": 3,
    "nit": 3,
}

VERDICT_BADGE = {"CONFIRM": "✅", "DISPUTE": "⚠️", "ESCALATE": "⏫"}


def warn(code: str, detail: str) -> None:
    print("warn|%s|%s" % (code, detail), file=sys.stderr)


def parse_level(raw: object) -> int:
    """Map a level in any accepted spelling to its ladder index. Unknown -> Medium."""
    if isinstance(raw, int) and 0 <= raw < len(LEVELS):
        return raw
    text = str(raw or "").strip()
    for emoji, idx in EMOJI_TO_IDX.items():
        if emoji in text:
            return idx
    word = re.sub(r"[^a-z]", "", text.lower())
    if word in WORD_TO_IDX:
        return WORD_TO_IDX[word]
    if word in LEGACY_TO_IDX:
        warn("legacy-level", "%r is pre-contract vocabulary" % text)
        return LEGACY_TO_IDX[word]
    warn("unknown-level", "%r — defaulting to Medium" % text)
    return 2


def issue_class(finding: dict) -> str:
    """Explicit class when given, else a normalized title."""
    explicit = str(finding.get("class") or "").strip().lower()
    if explicit:
        return explicit
    title = str(finding.get("title") or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def normalize(raw: list) -> list[dict]:
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            warn("bad-finding", "index %d is not an object — skipped" % i)
            continue
        out.append(
            {
                "id": item.get("id", i + 1),
                "level": parse_level(item.get("level", item.get("severity"))),
                "confidence": as_int(item.get("confidence"), 0),
                "file": str(item.get("file") or ""),
                "line": as_int(item.get("line"), 0),
                "title": str(item.get("title") or "").strip(),
                "issue": str(item.get("issue") or "").strip(),
                "fix": str(item.get("fix") or "").strip(),
                "memory": bool(item.get("memory")),
                "class": issue_class(item),
            }
        )
    return out


def dedupe(findings: list[dict], window: int) -> tuple[list[dict], int]:
    """Collapse same-file, same-class findings whose lines sit within `window`.

    The survivor is the highest-confidence member; ties go to the more severe level, then
    to the earlier one, so the result does not depend on agent return order. A survivor
    inherits the 🧠 tag if any member carried it — dropping it would lose the memory lane.
    """
    kept: list[dict] = []
    dropped = 0
    for finding in findings:
        for i, existing in enumerate(kept):
            same_place = (
                existing["file"] == finding["file"]
                and existing["class"] == finding["class"]
                and abs(existing["line"] - finding["line"]) <= window
            )
            if not same_place:
                continue
            incoming_wins = (finding["confidence"], -finding["level"]) > (
                existing["confidence"],
                -existing["level"],
            )
            memory = existing["memory"] or finding["memory"]
            kept[i] = (finding if incoming_wins else existing).copy()
            kept[i]["memory"] = memory
            dropped += 1
            break
        else:
            kept.append(finding)
    return kept, dropped


def apply_verdicts(findings: list[dict], verdicts: list | None) -> bool:
    """Attach badge/verdict to each finding. Returns True if any verdict was applied.

    A missing or unrecognized verdict degrades to CONFIRM with a warning rather than
    dropping the finding; verdict ids matching nothing are ignored silently.
    """
    if verdicts is None:
        for finding in findings:
            finding["verdict"] = ""
            finding["badge"] = ""
            finding["note"] = ""
            finding["fixable"] = True
        return False

    by_id: dict[str, dict] = {}
    for item in verdicts:
        if not isinstance(item, dict) or "id" not in item:
            warn("bad-verdict", "entry without an id — ignored")
            continue
        by_id[str(item["id"])] = item

    seen = set()
    for finding in findings:
        key = str(finding["id"])
        entry = by_id.get(key)
        seen.add(key)
        verdict = str((entry or {}).get("verdict") or "").strip().upper()
        if entry is None:
            verdict = "CONFIRM"
        elif verdict not in VERDICT_BADGE:
            warn("unknown-verdict", "%r on id %s — treated as CONFIRM" % (verdict, key))
            verdict = "CONFIRM"
        if verdict == "ESCALATE":
            finding["level"] = max(0, finding["level"] - 1)
        finding["verdict"] = verdict
        finding["badge"] = VERDICT_BADGE[verdict]
        finding["note"] = str((entry or {}).get("note") or "").strip()
        finding["fixable"] = verdict != "DISPUTE"

    for key in by_id:
        if key not in seen:
            warn("orphan-verdict", "id %s matches no finding — ignored" % key)
    return True


def count_line(findings: list[dict], has_verdicts: bool) -> str:
    tally = [0] * len(LEVELS)
    for finding in findings:
        tally[finding["level"]] += 1
    head = "  ".join(
        "%s %d" % (LEVELS[i][0], tally[i]) for i in range(len(LEVELS))
    )

    terms = []
    memory = sum(1 for f in findings if f["memory"])
    if memory:
        terms.append("🧠 %d" % memory)
    if has_verdicts:
        counts = {v: 0 for v in VERDICT_BADGE}
        for finding in findings:
            if finding["verdict"] in counts:
                counts[finding["verdict"]] += 1
        terms.append(
            "2nd opinion: %s"
            % " ".join(
                "%s%d" % (VERDICT_BADGE[v], counts[v])
                for v in ("CONFIRM", "DISPUTE", "ESCALATE")
                if counts[v]
            ).strip()
        )
    return head + ("   (%s)" % " · ".join(terms) if terms else "")


def title_line(finding: dict) -> str:
    emoji, word = LEVELS[finding["level"]]
    parts = ["%s %s" % (emoji, word)]
    if finding["memory"]:
        parts.append("🧠")
    if finding["verdict"]:
        parts.append("%s %s" % (finding["badge"], finding["verdict"]))
    return "%s — %s" % (" · ".join(parts), finding["title"])


def load_json(path: str) -> list:
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("findings", data.get("verdicts", []))
    if not isinstance(data, list):
        raise ValueError("expected a JSON array, got %s" % type(data).__name__)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("--findings", required=True)
    ap.add_argument("--verdicts")
    ap.add_argument("--cutoff", type=int, default=0)
    ap.add_argument("--line-window", type=int, default=3)
    ap.add_argument("--mode", choices=("local", "pr"), default="local")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        findings = normalize(load_json(args.findings))
    except (OSError, ValueError) as exc:
        print("err|rank-findings|cannot read --findings: %s" % exc, file=sys.stderr)
        return 1

    verdicts = None
    if args.verdicts:
        try:
            verdicts = load_json(args.verdicts)
        except (OSError, ValueError) as exc:
            # Matches review.md's parse-failure path: keep the findings, skip the overlay.
            warn("verdict-parse-failed", "%s — skipping verdict overlay" % exc)
            verdicts = None

    findings, dup_dropped = dedupe(findings, args.line_window)

    before = len(findings)
    findings = [f for f in findings if f["confidence"] >= args.cutoff]
    cut_dropped = before - len(findings)

    has_verdicts = apply_verdicts(findings, verdicts)

    # Sort after verdicts so an ESCALATE re-ranks before rendering.
    findings.sort(key=lambda f: (f["level"], -f["confidence"], f["file"], f["line"]))

    line = count_line(findings, has_verdicts)

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [
                        dict(f, title_line=title_line(f)) for f in findings
                    ],
                    "count_line": line,
                    "count_position": "last" if args.mode == "local" else "after-decision",
                    "dropped": {"duplicate": dup_dropped, "cutoff": cut_dropped},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for rank, finding in enumerate(findings, 1):
        print(
            "finding|%d|%s|%s|%s|%s|%s|%s|%d|%s|%d|%s|%s"
            % (
                rank,
                LEVELS[finding["level"]][0],
                LEVELS[finding["level"]][1],
                "memory" if finding["memory"] else "-",
                finding["badge"] or "-",
                finding["verdict"] or "-",
                "fixable" if finding["fixable"] else "disputed",
                finding["confidence"],
                finding["file"],
                finding["line"],
                finding["title"],
                finding["note"] or "-",
            )
        )
    print("count|%s" % line)
    print("count-position|%s" % ("last" if args.mode == "local" else "after-decision"))
    print("dropped|duplicate|%d" % dup_dropped)
    print("dropped|cutoff|%d" % cut_dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
