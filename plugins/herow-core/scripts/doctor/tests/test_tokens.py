"""Tests for tokens.py — MCP stash moves. No real config.

The MCP-move apply edits ~/.claude.json + mcp-stash.json directly (no shell-out),
backing up each first.
"""

from __future__ import annotations

import json
import unittest

from _base import DoctorTestCase

import _doctor  # noqa: E402
import tokens  # noqa: E402


class TestMcpStashMoves(DoctorTestCase):
    def _claude_json(self, servers, extra=None):
        obj = {"mcpServers": servers}
        if extra:
            obj.update(extra)
        return self.write_json(_doctor.claude_json_path(), obj)

    def test_playwright_warn_and_move(self):
        self._claude_json(
            {
                "playwright": {"command": "npx", "args": ["-y", "playwright"]},
                "playwright-headless": {"command": "npx", "args": ["--headless"]},
            },
            extra={"projects": {"/some/proj": {"x": 1}}},
        )
        self.assertEqual(
            self.run_check(tokens.check_playwright_headed_active)["status"], "warn"
        )
        rv, _ = self.call(tokens.apply_playwright_headed_active)
        self.assertTrue(rv)
        aj = json.loads(_doctor.claude_json_path().read_text())
        self.assertNotIn("playwright", aj["mcpServers"])  # removed from active
        self.assertIn("playwright-headless", aj["mcpServers"])  # sibling untouched
        self.assertEqual(
            aj["projects"], {"/some/proj": {"x": 1}}
        )  # other keys preserved
        stash = json.loads(_doctor.mcp_stash_path().read_text())
        self.assertIn("playwright", stash)  # now in stash
        # backup-first invariant: ~/.claude.json was backed up before the edit
        self.assertTrue(list(self.home.glob(".claude.json.bak.*")))
        # PASS + idempotent
        self.assertEqual(
            self.run_check(tokens.check_playwright_headed_active)["status"], "pass"
        )
        self.assertFalse(tokens.apply_playwright_headed_active())

    def test_malformed_hooks_and_servers_do_not_crash(self):
        # mcpServers as a list — checks must degrade, never raise
        self.write_json(_doctor.claude_json_path(), {"mcpServers": ["oops"]})
        self.assertEqual(self.run_check(tokens.check_grafana_active)["status"], "pass")
        self.assertFalse(tokens.apply_grafana_active())

    def test_grafana_warn_and_move(self):
        self._claude_json({"grafana": {"command": "uvx", "args": ["mcp-grafana"]}})
        self.assertEqual(self.run_check(tokens.check_grafana_active)["status"], "warn")
        rv, _ = self.call(tokens.apply_grafana_active)
        self.assertTrue(rv)
        self.assertEqual(self.run_check(tokens.check_grafana_active)["status"], "pass")

    def test_not_active_is_pass(self):
        self._claude_json({"other": {"command": "x"}})
        self.assertEqual(
            self.run_check(tokens.check_playwright_headed_active)["status"], "pass"
        )
        self.assertFalse(tokens.apply_playwright_headed_active())

    def test_missing_claude_json_is_pass(self):
        self.assertEqual(self.run_check(tokens.check_grafana_active)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
