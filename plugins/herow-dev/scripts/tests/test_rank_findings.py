#!/usr/bin/env python3
"""Unit tests for rank-findings.py.

Run:
  python3 -m unittest discover -s plugins/herow-dev/scripts/tests -p 'test_*.py' -t .
  python3 plugins/herow-dev/scripts/tests/test_rank_findings.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "rank-findings.py"
_spec = importlib.util.spec_from_file_location("rank_findings", _SCRIPT)
rf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rf)


def finding(**kw):
    base = {
        "id": 1,
        "level": "Medium",
        "confidence": 90,
        "file": "a.ts",
        "line": 10,
        "title": "t",
        "issue": "i",
        "fix": "f",
    }
    base.update(kw)
    return base


def prep(items, verdicts=None, window=3, cutoff=0):
    fs, dup = rf.dedupe(rf.normalize(items), window)
    fs = [f for f in fs if f["confidence"] >= cutoff]
    has = rf.apply_verdicts(fs, verdicts)
    fs.sort(key=lambda f: (f["level"], -f["confidence"], f["file"], f["line"]))
    return fs, dup, has


class TestLevelParsing(unittest.TestCase):
    def test_accepts_emoji_word_and_both(self):
        for raw in ("🟠", "High", "high", "🟠 High"):
            self.assertEqual(rf.parse_level(raw), 1, raw)

    def test_accepts_legacy_vocabulary(self):
        self.assertEqual(rf.parse_level("CRITICAL"), 0)
        self.assertEqual(rf.parse_level("SUGGESTION"), 3)

    def test_unknown_defaults_to_medium(self):
        self.assertEqual(rf.parse_level("banana"), 2)
        self.assertEqual(rf.parse_level(None), 2)


class TestEscalate(unittest.TestCase):
    def test_escalate_raises_exactly_one_level(self):
        for start, expect in (("Low", "Medium"), ("Medium", "High"), ("High", "Critical")):
            fs, _, _ = prep(
                [finding(level=start)], [{"id": 1, "verdict": "ESCALATE"}]
            )
            self.assertEqual(rf.LEVELS[fs[0]["level"]][1], expect, start)

    def test_critical_saturates(self):
        fs, _, _ = prep([finding(level="Critical")], [{"id": 1, "verdict": "ESCALATE"}])
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "Critical")

    def test_dispute_keeps_level_but_blocks_fix(self):
        fs, _, _ = prep([finding(level="High")], [{"id": 1, "verdict": "DISPUTE"}])
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "High")
        self.assertFalse(fs[0]["fixable"])

    def test_confirm_is_fixable_and_unchanged(self):
        fs, _, _ = prep([finding(level="High")], [{"id": 1, "verdict": "CONFIRM"}])
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "High")
        self.assertTrue(fs[0]["fixable"])


class TestVerdictDegradation(unittest.TestCase):
    def test_missing_verdict_degrades_to_confirm(self):
        fs, _, has = prep([finding(id=1), finding(id=2, line=99)], [{"id": 1, "verdict": "CONFIRM"}])
        self.assertTrue(has)
        self.assertEqual({f["verdict"] for f in fs}, {"CONFIRM"})

    def test_unknown_verdict_string_degrades_to_confirm(self):
        fs, _, _ = prep([finding()], [{"id": 1, "verdict": "MAYBE"}])
        self.assertEqual(fs[0]["verdict"], "CONFIRM")

    def test_orphan_verdict_is_ignored(self):
        fs, _, _ = prep([finding(id=1)], [{"id": 7, "verdict": "ESCALATE"}])
        self.assertEqual(len(fs), 1)
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "Medium")

    def test_no_verdicts_leaves_badges_empty(self):
        fs, _, has = prep([finding()], None)
        self.assertFalse(has)
        self.assertEqual(fs[0]["badge"], "")
        self.assertEqual(fs[0]["verdict"], "")
        self.assertTrue(fs[0]["fixable"])


class TestDedupe(unittest.TestCase):
    def test_same_class_within_window_collapses_keeping_highest_confidence(self):
        fs, dup, _ = prep(
            [
                finding(id=1, line=10, confidence=70, title="same thing"),
                finding(id=2, line=12, confidence=95, title="same thing"),
            ]
        )
        self.assertEqual((len(fs), dup), (1, 1))
        self.assertEqual(fs[0]["confidence"], 95)

    def test_outside_window_survives(self):
        fs, dup, _ = prep(
            [
                finding(id=1, line=10, title="same thing"),
                finding(id=2, line=40, title="same thing"),
            ]
        )
        self.assertEqual((len(fs), dup), (2, 0))

    def test_different_class_survives(self):
        fs, dup, _ = prep(
            [finding(id=1, title="leak"), finding(id=2, title="typo")]
        )
        self.assertEqual((len(fs), dup), (2, 0))

    def test_different_file_survives(self):
        fs, dup, _ = prep(
            [finding(id=1, file="a.ts"), finding(id=2, file="b.ts")]
        )
        self.assertEqual((len(fs), dup), (2, 0))

    def test_explicit_class_beats_title(self):
        fs, dup, _ = prep(
            [
                finding(id=1, title="worded one way", **{"class": "leak"}),
                finding(id=2, title="worded another way", **{"class": "leak"}),
            ]
        )
        self.assertEqual((len(fs), dup), (1, 1))

    def test_memory_tag_survives_collapse(self):
        fs, _, _ = prep(
            [
                finding(id=1, confidence=95, title="x", memory=False),
                finding(id=2, confidence=70, title="x", memory=True),
            ]
        )
        self.assertEqual(len(fs), 1)
        self.assertTrue(fs[0]["memory"], "the 🧠 lane must not be lost to dedupe")

    def test_order_independence(self):
        a = [finding(id=1, confidence=70, title="x"), finding(id=2, confidence=95, title="x")]
        fs1, _, _ = prep(a)
        fs2, _, _ = prep(list(reversed(a)))
        self.assertEqual(fs1[0]["confidence"], fs2[0]["confidence"])


class TestCutoff(unittest.TestCase):
    def test_below_cutoff_dropped(self):
        fs, _, _ = prep(
            [finding(id=1, confidence=95, title="a"), finding(id=2, confidence=60, title="b")],
            cutoff=80,
        )
        self.assertEqual([f["confidence"] for f in fs], [95])

    def test_missing_confidence_is_zero_and_filtered(self):
        items = [{"id": 1, "level": "High", "file": "a.ts", "line": 1, "title": "t"}]
        fs, _, _ = prep(items, cutoff=80)
        self.assertEqual(fs, [])


class TestCountLine(unittest.TestCase):
    def test_tally_and_no_parenthetical_without_verdicts_or_memory(self):
        fs, _, has = prep(
            [
                finding(id=1, level="Critical", title="a"),
                finding(id=2, level="High", title="b"),
                finding(id=3, level="High", title="c"),
            ]
        )
        self.assertEqual(rf.count_line(fs, has), "🔴 1  🟠 2  🟡 0  🟢 0")

    def test_memory_term_without_verdicts(self):
        fs, _, has = prep([finding(memory=True)])
        self.assertEqual(rf.count_line(fs, has), "🔴 0  🟠 0  🟡 1  🟢 0   (🧠 1)")

    def test_second_opinion_term(self):
        fs, _, has = prep(
            [finding(id=1, title="a"), finding(id=2, title="b", line=50)],
            [{"id": 1, "verdict": "CONFIRM"}, {"id": 2, "verdict": "DISPUTE"}],
        )
        self.assertIn("2nd opinion: ✅1 ⚠️1", rf.count_line(fs, has))

    def test_both_terms_joined(self):
        fs, _, has = prep([finding(memory=True)], [{"id": 1, "verdict": "CONFIRM"}])
        self.assertIn("(🧠 1 · 2nd opinion: ✅1)", rf.count_line(fs, has))


class TestTitleLine(unittest.TestCase):
    def test_badgeless_without_verdicts(self):
        fs, _, _ = prep([finding(level="Critical", title="Short title")])
        self.assertEqual(rf.title_line(fs[0]), "🔴 Critical — Short title")

    def test_with_verdict(self):
        fs, _, _ = prep(
            [finding(level="Critical", title="Short title")],
            [{"id": 1, "verdict": "CONFIRM"}],
        )
        self.assertEqual(rf.title_line(fs[0]), "🔴 Critical · ✅ CONFIRM — Short title")

    def test_memory_segment_between_level_and_badge(self):
        fs, _, _ = prep(
            [finding(level="High", title="Leak", memory=True)],
            [{"id": 1, "verdict": "ESCALATE", "note": "worse than stated"}],
        )
        self.assertEqual(
            rf.title_line(fs[0]), "🔴 Critical · 🧠 · ⏫ ESCALATE — Leak"
        )


class TestSorting(unittest.TestCase):
    def test_sorted_most_severe_first_after_escalation(self):
        fs, _, _ = prep(
            [
                finding(id=1, level="Low", title="a"),
                finding(id=2, level="Medium", title="b", line=50),
            ],
            [{"id": 1, "verdict": "ESCALATE"}, {"id": 2, "verdict": "CONFIRM"}],
        )
        # id=1 Low -> Medium; tie on level, so higher confidence/file/line orders them.
        self.assertEqual([rf.LEVELS[f["level"]][1] for f in fs], ["Medium", "Medium"])

    def test_escalated_finding_outranks_its_original_peer(self):
        fs, _, _ = prep(
            [
                finding(id=1, level="Medium", title="a"),
                finding(id=2, level="High", title="b", line=50),
            ],
            [{"id": 1, "verdict": "ESCALATE"}],
        )
        self.assertEqual([f["id"] for f in fs], [1, 2])
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "High")


class TestBadInput(unittest.TestCase):
    def test_non_object_finding_skipped(self):
        self.assertEqual(rf.normalize(["nope", finding()]), rf.normalize([finding()]))

    def test_verdict_without_id_ignored(self):
        fs, _, has = prep([finding()], [{"verdict": "ESCALATE"}])
        self.assertTrue(has)
        self.assertEqual(rf.LEVELS[fs[0]["level"]][1], "Medium")


if __name__ == "__main__":
    unittest.main(verbosity=2)
