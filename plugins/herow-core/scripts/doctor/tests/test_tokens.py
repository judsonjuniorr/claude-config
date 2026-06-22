"""Tests for tokens.py — headroom hook + MCP stash moves. No real config.

The MCP-move apply edits ~/.claude.json + mcp-stash.json directly (no shell-out),
backing up each first.
"""

from __future__ import annotations

import json
import unittest

from _base import DoctorTestCase

import _doctor  # noqa: E402
import tokens  # noqa: E402

HEADROOM = "/x/.local/bin/headroom init hook ensure --profile init-user --marker m"


def _settings_with_headroom(in_pre=True, in_session=True):
    pre = [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo graphify"}]},
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "rtk hook claude"}],
        },
    ]
    if in_pre:
        pre.append(
            {"matcher": "Bash", "hooks": [{"type": "command", "command": HEADROOM}]}
        )
    session = []
    if in_session:
        session.append(
            {
                "matcher": "startup|resume",
                "hooks": [{"type": "command", "command": HEADROOM}],
            }
        )
    return {"hooks": {"PreToolUse": pre, "SessionStart": session}}


class TestHeadroomRedundancy(DoctorTestCase):
    def _settings(self, obj):
        return self.write_json(_doctor.settings_path(), obj)

    def test_warn_when_in_both(self):
        self._settings(_settings_with_headroom(in_pre=True, in_session=True))
        self.assertEqual(
            self.run_check(tokens.check_headroom_hook_redundancy)["status"], "warn"
        )

    def test_apply_removes_pre_keeps_others_and_session(self):
        self._settings(_settings_with_headroom(in_pre=True, in_session=True))
        self.assertTrue(tokens.apply_headroom_hook_redundancy())
        s = json.loads(_doctor.settings_path().read_text())
        pre = s["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 2)  # graphify + rtk survive
        cmds = [h["command"] for m in pre for h in m["hooks"]]
        self.assertNotIn(HEADROOM, cmds)
        # SessionStart copy intact
        self.assertEqual(len(s["hooks"]["SessionStart"]), 1)
        # now PASS + idempotent
        self.assertEqual(
            self.run_check(tokens.check_headroom_hook_redundancy)["status"], "pass"
        )
        self.assertFalse(tokens.apply_headroom_hook_redundancy())

    def test_sole_copy_in_pre_is_pass_and_apply_refuses(self):
        self._settings(_settings_with_headroom(in_pre=True, in_session=False))
        self.assertEqual(
            self.run_check(tokens.check_headroom_hook_redundancy)["status"], "pass"
        )
        self.assertFalse(
            tokens.apply_headroom_hook_redundancy()
        )  # never delete the only copy

    def test_absent_is_pass(self):
        self._settings(_settings_with_headroom(in_pre=False, in_session=True))
        self.assertEqual(
            self.run_check(tokens.check_headroom_hook_redundancy)["status"], "pass"
        )


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
        # hooks as a list, mcpServers as a list — checks must degrade, never raise
        self.write_json(_doctor.settings_path(), {"hooks": ["oops"]})
        self.assertEqual(
            self.run_check(tokens.check_headroom_hook_redundancy)["status"], "pass"
        )
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
