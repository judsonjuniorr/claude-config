"""Tests for audit.py — aggregation + graceful degradation. Spawns the real
sub-scripts as subprocesses, which inherit DOCTOR_HOME from the env."""

from __future__ import annotations

import json
import unittest

from _base import DoctorTestCase

import _doctor  # noqa: E402
import audit  # noqa: E402


class TestAudit(DoctorTestCase):
    def _run(self) -> dict:
        _rv, out = self.call(audit.main)
        return json.loads(out)

    def test_empty_home_all_pass_no_crash(self):
        report = self._run()
        self.assertEqual(report["summary"], {"fail": 0, "warn": 0, "pass": 8})
        self.assertEqual(len(report["checks"]), 8)
        # contract: every check line has the five fields
        for c in report["checks"]:
            self.assertEqual(set(c), {"check", "status", "detail", "diff", "fix_cmd"})

    def test_mixed_counts(self):
        # one FAIL (no permissions.deny) + one WARN (gstack.bak); rest PASS
        self.write_json(
            _doctor.settings_path(),
            {"permissions": {"allow": ["Bash(git:*)"], "defaultMode": "auto"}},
        )
        gb = self.claude_home / "skills" / "gstack.bak"
        gb.mkdir(parents=True)
        (gb / "f").write_bytes(b"y" * 1024)
        report = self._run()
        self.assertEqual(report["summary"]["fail"], 1)
        self.assertEqual(report["summary"]["warn"], 1)
        self.assertEqual(report["summary"]["pass"], 6)
        self.assertEqual(sum(report["summary"].values()), 8)

    def test_unparseable_settings_degrades(self):
        _doctor.settings_path().write_text("{ not valid json ")
        report = self._run()  # must not raise
        self.assertEqual(sum(report["summary"].values()), 8)


if __name__ == "__main__":
    unittest.main()
