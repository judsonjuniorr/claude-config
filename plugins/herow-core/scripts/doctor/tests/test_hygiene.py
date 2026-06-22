"""Tests for hygiene.py — gstack.bak, CLAUDE.md backups, language-rules frontmatter."""

from __future__ import annotations

import unittest

from _base import DoctorTestCase

import _doctor  # noqa: E402
import hygiene  # noqa: E402


class TestGstackBak(DoctorTestCase):
    def _make(self):
        d = self.claude_home / "skills" / "gstack.bak"
        d.mkdir(parents=True)
        (d / "blob.bin").write_bytes(b"x" * 2048)
        return d

    def test_warn_then_apply_then_pass(self):
        self._make()
        r = self.run_check(hygiene.check_gstack_bak)
        self.assertEqual(r["status"], "warn")
        self.assertTrue(hygiene.apply_gstack_bak())
        self.assertFalse((self.claude_home / "skills" / "gstack.bak").exists())
        self.assertEqual(self.run_check(hygiene.check_gstack_bak)["status"], "pass")
        self.assertFalse(hygiene.apply_gstack_bak())  # idempotent

    def test_absent_pass(self):
        self.assertEqual(self.run_check(hygiene.check_gstack_bak)["status"], "pass")


class TestClaudeMdBackups(DoctorTestCase):
    def test_warn_lists_all_then_apply(self):
        self.write_text(self.claude_home / "CLAUDE.md.bak.20260101-000000", "old")
        self.write_text(self.claude_home / "CLAUDE.md.pre-omega", "older")
        r = self.run_check(hygiene.check_claude_md_backups)
        self.assertEqual(r["status"], "warn")
        self.assertIn("CLAUDE.md.bak.20260101-000000", r["diff"])
        self.assertIn("CLAUDE.md.pre-omega", r["diff"])
        self.assertTrue(hygiene.apply_claude_md_backups())
        self.assertEqual(
            self.run_check(hygiene.check_claude_md_backups)["status"], "pass"
        )
        self.assertFalse(hygiene.apply_claude_md_backups())  # idempotent

    def test_keeps_live_claude_md(self):
        self.write_text(self.claude_home / "CLAUDE.md", "real")
        self.write_text(self.claude_home / "CLAUDE.md.pre-omega", "older")
        hygiene.apply_claude_md_backups()
        self.assertTrue((self.claude_home / "CLAUDE.md").exists())  # untouched

    def test_none_pass(self):
        self.assertEqual(
            self.run_check(hygiene.check_claude_md_backups)["status"], "pass"
        )


class TestLanguageRulesPaths(DoctorTestCase):
    def _pointer(self):
        return self.claude_home / "rules" / "language-rules-pointer.md"

    def test_warn_when_no_frontmatter_then_apply_prepends(self):
        body = "## Language-specific rules\n\nTypeScript -> ...\nPython -> ...\n"
        self.write_text(self._pointer(), body)
        self.assertEqual(
            self.run_check(hygiene.check_language_rules_paths)["status"], "warn"
        )
        self.assertTrue(hygiene.apply_language_rules_paths())
        text = self._pointer().read_text()
        self.assertTrue(text.startswith("---"))
        self.assertIn("paths:", text)
        self.assertIn(body, text)  # original body preserved verbatim
        self.assertEqual(
            self.run_check(hygiene.check_language_rules_paths)["status"], "pass"
        )
        self.assertFalse(hygiene.apply_language_rules_paths())  # idempotent

    def test_existing_frontmatter_pass(self):
        self.write_text(self._pointer(), "---\npaths:\n  - '**/*.py'\n---\nbody\n")
        self.assertEqual(
            self.run_check(hygiene.check_language_rules_paths)["status"], "pass"
        )
        self.assertFalse(hygiene.apply_language_rules_paths())

    def test_missing_file_pass(self):
        self.assertEqual(
            self.run_check(hygiene.check_language_rules_paths)["status"], "pass"
        )


if __name__ == "__main__":
    unittest.main()
