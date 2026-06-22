"""Tests for security.py — permissions_deny + plaintext_secrets. No real config."""

from __future__ import annotations

import json
import unittest

from _base import DoctorTestCase

import _doctor  # noqa: E402
import security  # noqa: E402


class TestLooksLikeSecret(unittest.TestCase):
    def test_literal_token_flagged(self):
        self.assertTrue(
            security.looks_like_secret(
                "GITHUB_PERSONAL_ACCESS_TOKEN", "gho_aB3xY9zQ1mN7kL2pR5tV8w0dE4fG"
            )
        )
        self.assertTrue(
            security.looks_like_secret("FIRECRAWL_API_KEY", "fc-0123456789abcdef0123")
        )

    def test_var_ref_not_flagged(self):
        self.assertFalse(security.looks_like_secret("X_TOKEN", "${X_TOKEN}"))
        self.assertFalse(security.looks_like_secret("API_KEY", "${SOME_KEY}"))

    def test_config_values_not_flagged(self):
        self.assertFalse(security.looks_like_secret("MCP_MODE", "stdio"))
        self.assertFalse(security.looks_like_secret("LOG_LEVEL", "error"))
        self.assertFalse(security.looks_like_secret("DISABLE_CONSOLE_OUTPUT", "true"))

    def test_urls_not_flagged(self):
        self.assertFalse(
            security.looks_like_secret("N8N_API_URL", "https://n8n.example.com/api/v1")
        )
        self.assertFalse(
            security.looks_like_secret("GRAFANA_URL", "https://grafana.example.com/")
        )

    def test_short_value_under_plain_key_not_flagged(self):
        self.assertFalse(security.looks_like_secret("REGION", "us-east-1"))

    def test_long_opaque_value_fallback_flagged(self):
        self.assertTrue(
            security.looks_like_secret("SOMEFIELD", "abcdefghij1234567890ABCDEFXYZ")
        )

    def test_non_string_not_flagged(self):
        self.assertFalse(security.looks_like_secret("FLAG", True))


class TestDeriveVarName(unittest.TestCase):
    def test_unique_key_verbatim(self):
        self.assertEqual(
            security.derive_var_name(
                "github",
                "GITHUB_PERSONAL_ACCESS_TOKEN",
                {"GITHUB_PERSONAL_ACCESS_TOKEN": 1},
            ),
            "GITHUB_PERSONAL_ACCESS_TOKEN",
        )

    def test_collision_prefixed(self):
        self.assertEqual(
            security.derive_var_name("firecrawl-mcp", "API_KEY", {"API_KEY": 2}),
            "FIRECRAWL_MCP__API_KEY",
        )


class TestPermissionsDeny(DoctorTestCase):
    def _settings(self, obj):
        return self.write_json(_doctor.settings_path(), obj)

    def test_fail_when_no_deny(self):
        self._settings(
            {"permissions": {"allow": ["Bash(git:*)"], "defaultMode": "auto"}}
        )
        r = self.run_check(security.check_permissions_deny)
        self.assertEqual(r["status"], "fail")
        self.assertIsNotNone(r["fix_cmd"])

    def test_apply_creates_block_and_preserves_allow(self):
        self._settings(
            {"permissions": {"allow": ["Bash(git:*)"], "defaultMode": "auto"}}
        )
        changed = security.apply_permissions_deny()
        self.assertTrue(changed)
        s = json.loads(_doctor.settings_path().read_text())
        self.assertEqual(s["permissions"]["allow"], ["Bash(git:*)"])  # preserved
        self.assertEqual(s["permissions"]["defaultMode"], "auto")  # preserved
        self.assertIn("Read(**/*secret*)", s["permissions"]["deny"])
        # now PASS + second apply is a noop
        self.assertEqual(
            self.run_check(security.check_permissions_deny)["status"], "pass"
        )
        self.assertFalse(security.apply_permissions_deny())

    def test_apply_missing_settings_does_not_fabricate(self):
        self.assertFalse(security.apply_permissions_deny())
        self.assertFalse(_doctor.settings_path().exists())

    def test_backup_written_on_apply(self):
        self._settings({"permissions": {"allow": []}})
        security.apply_permissions_deny()
        baks = list(self.claude_home.glob("settings.json.bak.*"))
        self.assertEqual(len(baks), 1)


class TestPlaintextSecrets(DoctorTestCase):
    def _stash(self, obj):
        return self.write_json(_doctor.mcp_stash_path(), obj)

    def test_fail_on_literal(self):
        self._stash(
            {
                "github": {
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "gho_abcdef0123456789abcd"}
                }
            }
        )
        r = self.run_check(security.check_plaintext_secrets)
        self.assertEqual(r["status"], "fail")

    def test_apply_rewrites_to_var_ref_and_preserves_value_only_in_bak(self):
        secret = "gho_abcdef0123456789abcdEFGH"
        self._stash(
            {
                "github": {"env": {"GITHUB_PERSONAL_ACCESS_TOKEN": secret}},
                "n8n": {
                    "env": {
                        "MCP_MODE": "stdio",
                        "N8N_API_URL": "https://n8n.example.com",
                    }
                },
            }
        )
        rv, out = self.call(security.apply_plaintext_secrets)
        self.assertTrue(rv)
        patched = json.loads(_doctor.mcp_stash_path().read_text())
        # secret replaced with ${VAR}; config + url untouched
        self.assertEqual(
            patched["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"],
            "${GITHUB_PERSONAL_ACCESS_TOKEN}",
        )
        self.assertEqual(patched["n8n"]["env"]["MCP_MODE"], "stdio")
        self.assertEqual(
            patched["n8n"]["env"]["N8N_API_URL"], "https://n8n.example.com"
        )
        # the real value must NOT leak to the patched file nor to stdout
        self.assertNotIn(secret, _doctor.mcp_stash_path().read_text())
        self.assertNotIn(secret, out)
        self.assertIn("info|export-needed|GITHUB_PERSONAL_ACCESS_TOKEN", out)
        # the real value survives ONLY in the chmod-600 .bak
        baks = list(self.claude_home.glob("mcp-stash.json.bak.*"))
        self.assertEqual(len(baks), 1)
        self.assertIn(secret, baks[0].read_text())

    def test_apply_then_noop(self):
        self._stash(
            {
                "github": {
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "gho_abcdef0123456789abcd"}
                }
            }
        )
        self.call(security.apply_plaintext_secrets)
        self.assertEqual(
            self.run_check(security.check_plaintext_secrets)["status"], "pass"
        )
        rv, _ = self.call(security.apply_plaintext_secrets)
        self.assertFalse(rv)

    def test_no_stash_passes(self):
        self.assertEqual(
            self.run_check(security.check_plaintext_secrets)["status"], "pass"
        )

    def test_malformed_env_does_not_crash(self):
        # env as a list / a non-dict server must degrade, never raise
        self._stash({"a": {"env": ["oops"]}, "b": "not-a-dict"})
        self.assertEqual(
            self.run_check(security.check_plaintext_secrets)["status"], "pass"
        )
        self.assertFalse(security.apply_plaintext_secrets())


class TestMalformedSettings(DoctorTestCase):
    def test_permissions_as_list_does_not_crash(self):
        # permissions as a list (malformed) must not raise; deny treated as absent
        self.write_json(_doctor.settings_path(), {"permissions": ["Bash(git:*)"]})
        self.assertEqual(
            self.run_check(security.check_permissions_deny)["status"], "fail"
        )
        # apply refuses to clobber a non-dict permissions block
        self.assertFalse(security.apply_permissions_deny())


if __name__ == "__main__":
    unittest.main()
