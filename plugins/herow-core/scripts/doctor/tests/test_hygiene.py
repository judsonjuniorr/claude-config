"""Tests for hygiene.py — gstack.bak, CLAUDE.md backups, language-rules frontmatter,
legacy ~/.herow dirs, and settings.json ~/.herow permissions."""

from __future__ import annotations

import json
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


class TestLegacyHerowDirs(DoctorTestCase):
    def test_pass_when_none_present(self):
        self.assertEqual(
            self.run_check(hygiene.check_legacy_herow_dirs)["status"], "pass"
        )

    def test_warn_lists_all_three(self):
        (self.home / "finance").mkdir()
        (self.claude_home / "seo").mkdir()
        (self.claude_home / "herow-data").mkdir()
        r = self.run_check(hygiene.check_legacy_herow_dirs)
        self.assertEqual(r["status"], "warn")
        self.assertIn(str(self.home / "finance"), r["diff"])
        self.assertIn(str(self.claude_home / "seo"), r["diff"])
        self.assertIn(str(self.claude_home / "herow-data"), r["diff"])

    def test_symlinked_finance_not_flagged(self):
        target = self.home / "herow-finance-target"
        target.mkdir()
        (self.home / "finance").symlink_to(target)
        self.assertEqual(
            self.run_check(hygiene.check_legacy_herow_dirs)["status"], "pass"
        )

    def test_apply_is_informational_noop(self):
        (self.home / "finance").mkdir()
        self.assertFalse(hygiene.apply_legacy_herow_dirs())


class TestHerowPermissions(DoctorTestCase):
    def _settings(self, obj):
        return self.write_json(_doctor.settings_path(), obj)

    def test_warn_when_missing(self):
        self._settings({"permissions": {"allow": ["Bash(git:*)"]}})
        r = self.run_check(hygiene.check_herow_permissions)
        self.assertEqual(r["status"], "warn")
        self.assertIsNotNone(r["fix_cmd"])

    def test_apply_adds_both_and_preserves_existing(self):
        self._settings(
            {"permissions": {"allow": ["Bash(git:*)"], "defaultMode": "auto"}}
        )
        self.assertTrue(hygiene.apply_herow_permissions())
        s = json.loads(_doctor.settings_path().read_text())
        self.assertIn("Bash(git:*)", s["permissions"]["allow"])
        self.assertIn("Edit(~/.herow/**)", s["permissions"]["allow"])
        self.assertIn("~/.herow", s["permissions"]["additionalDirectories"])
        self.assertEqual(s["permissions"]["defaultMode"], "auto")  # preserved
        self.assertEqual(
            self.run_check(hygiene.check_herow_permissions)["status"], "pass"
        )
        self.assertFalse(hygiene.apply_herow_permissions())  # idempotent

    def test_apply_missing_settings_does_not_fabricate(self):
        self.assertFalse(hygiene.apply_herow_permissions())
        self.assertFalse(_doctor.settings_path().exists())

    def test_partial_missing_only_adds_what_is_needed(self):
        self._settings(
            {
                "permissions": {
                    "allow": ["Edit(~/.herow/**)"],
                    "additionalDirectories": [],
                }
            }
        )
        self.assertTrue(hygiene.apply_herow_permissions())
        s = json.loads(_doctor.settings_path().read_text())
        self.assertEqual(s["permissions"]["allow"].count("Edit(~/.herow/**)"), 1)
        self.assertIn("~/.herow", s["permissions"]["additionalDirectories"])

    def test_malformed_permissions_does_not_crash(self):
        self._settings({"permissions": ["Bash(git:*)"]})
        self.assertEqual(
            self.run_check(hygiene.check_herow_permissions)["status"], "warn"
        )
        self.assertFalse(hygiene.apply_herow_permissions())


class TestWriteJsonSymlink(DoctorTestCase):
    def test_writes_through_symlink(self):
        real = self.home / "dotfiles" / "settings.json"
        real.parent.mkdir()
        real.write_text("{}")
        link = _doctor.settings_path()
        link.symlink_to(real)
        _doctor.write_json(link, {"a": 1})
        self.assertTrue(link.is_symlink())
        self.assertEqual(json.loads(real.read_text()), {"a": 1})


if __name__ == "__main__":
    unittest.main()
