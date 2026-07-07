"""Tests for _cli.py — the `organizze` CLI wrapper. No real subprocess/network."""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

# Hermetic data dir BEFORE importing _cli (AUTH derives from ORGANIZZE_HOME).
os.environ["ORGANIZZE_HOME"] = tempfile.mkdtemp(prefix="org-cli-test-")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import _cli as cli  # noqa: E402

AUTH = ("e@x.com", "tok123456", "ua/1.0 (e@x.com)")


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestCliJsonHappyPath(unittest.TestCase):
    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_parses_json_stdout(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(0, stdout=json.dumps([{"id": 1}]))
        data = cli.cli_json(["accounts", "list"], AUTH)
        self.assertEqual(data, [{"id": 1}])
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["organizze", "--json", "accounts", "list"])
        self.assertEqual(kwargs["env"]["ORGANIZZE_EMAIL"], "e@x.com")
        self.assertEqual(kwargs["env"]["ORGANIZZE_API_KEY"], "tok123456")
        self.assertEqual(kwargs["env"]["ORGANIZZE_USER_AGENT"], AUTH[2])

    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_empty_stdout_is_null(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(0, stdout="")
        self.assertIsNone(cli.cli_json(["status"], AUTH))


class TestCliJsonExitCodeMapping(unittest.TestCase):
    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_auth_error_exit_3(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(3, stderr="not logged in")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["accounts", "list"], AUTH)
        self.assertIn("err|auth|", str(ctx.exception))

    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_validation_error_exit_5_maps_to_http_422(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(5, stderr="field errors")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["transactions", "create"], AUTH)
        self.assertIn("err|http-422|", str(ctx.exception))

    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_network_error_exit_7(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(7, stderr="dns failure")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["status"], AUTH)
        self.assertIn("err|network|", str(ctx.exception))

    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_rate_limited_exit_6(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(6, stderr="too many requests")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["transactions", "list"], AUTH)
        self.assertIn("err|rate-limited|", str(ctx.exception))

    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_unknown_exit_code_falls_back(self, mock_run, mock_which):
        mock_run.return_value = _FakeProc(42, stderr="???")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["status"], AUTH)
        self.assertIn("err|exit-42|", str(ctx.exception))


class TestCliJsonMissingBinary(unittest.TestCase):
    @patch("_cli.shutil.which", return_value=None)
    def test_missing_binary_errors(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["status"], AUTH)
        self.assertIn("err|no-cli|", str(ctx.exception))


class TestCliJsonTimeout(unittest.TestCase):
    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_timeout_maps_to_network_error(self, mock_run, mock_which):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="organizze", timeout=60)
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["transactions", "list"], AUTH)
        self.assertIn("err|network|", str(ctx.exception))
        self.assertIn("timed out", str(ctx.exception))


class TestCliJsonBadOutput(unittest.TestCase):
    @patch("_cli.shutil.which", return_value="/usr/local/bin/organizze")
    @patch("_cli.subprocess.run")
    def test_non_json_stdout_on_success_exit_maps_to_bad_json(
        self, mock_run, mock_which
    ):
        # rc=0 but stdout isn't valid JSON (e.g. a crash/partial write past the exit check).
        mock_run.return_value = _FakeProc(0, stdout="not json {")
        with self.assertRaises(SystemExit) as ctx:
            cli.cli_json(["accounts", "list"], AUTH)
        self.assertIn("err|bad-json|", str(ctx.exception))


class TestTypedHelpers(unittest.TestCase):
    @patch("_cli.cli_json")
    def test_accounts_list_builds_correct_args(self, mock_cli_json):
        mock_cli_json.return_value = [{"id": 1}]
        result = cli.accounts_list(AUTH)
        mock_cli_json.assert_called_once_with(["accounts", "list"], AUTH)
        self.assertEqual(result, [{"id": 1}])

    @patch("_cli.cli_json")
    def test_account_get_builds_correct_args(self, mock_cli_json):
        mock_cli_json.return_value = {"id": 3, "balance": 12345}
        result = cli.account_get(3, AUTH)
        mock_cli_json.assert_called_once_with(["accounts", "get", "3"], AUTH)
        self.assertEqual(result["balance"], 12345)

    @patch("_cli.cli_json")
    def test_account_get_parses_real_brl_formatted_balance(self, mock_cli_json):
        # Per the REST v2 OpenAPI spec, GET /accounts/{id}'s `balance` is a
        # FORMATTED STRING ("R$ 1.234,56"), unlike every other money field in
        # the API (integer cents) — this is the real shape the CLI returns.
        mock_cli_json.return_value = {"id": 3, "balance": "R$ 1.234,56"}
        result = cli.account_get(3, AUTH)
        self.assertEqual(result["balance"], 123456)

    @patch("_cli.cli_json")
    def test_account_get_parses_negative_brl_balance(self, mock_cli_json):
        mock_cli_json.return_value = {"id": 3, "balance": "-R$ 50,00"}
        result = cli.account_get(3, AUTH)
        self.assertEqual(result["balance"], -5000)

    @patch("_cli.cli_json")
    def test_account_get_parses_zero_brl_balance(self, mock_cli_json):
        mock_cli_json.return_value = {"id": 3, "balance": "R$ 0,00"}
        result = cli.account_get(3, AUTH)
        self.assertEqual(result["balance"], 0)


class TestParseBrlCents(unittest.TestCase):
    def test_thousands_and_decimal(self):
        self.assertEqual(cli._parse_brl_cents("R$ 1.234,56"), 123456)

    def test_no_thousands_separator(self):
        self.assertEqual(cli._parse_brl_cents("R$ 50,00"), 5000)

    def test_negative_sign_before_symbol(self):
        self.assertEqual(cli._parse_brl_cents("-R$ 50,00"), -5000)

    def test_negative_sign_after_symbol(self):
        self.assertEqual(cli._parse_brl_cents("R$ -50,00"), -5000)

    def test_single_digit_cents_padded(self):
        self.assertEqual(cli._parse_brl_cents("R$ 10,5"), 1050)

    def test_zero(self):
        self.assertEqual(cli._parse_brl_cents("R$ 0,00"), 0)

    def test_large_value_multiple_thousands_separators(self):
        self.assertEqual(cli._parse_brl_cents("R$ 1.234.567,89"), 123456789)

    @patch("_cli.cli_json")
    def test_invoices_list_with_dates(self, mock_cli_json):
        mock_cli_json.return_value = []
        cli.invoices_list(9, "2026-01-01", "2026-01-31", AUTH)
        mock_cli_json.assert_called_once_with(
            ["invoices", "list", "9", "--since", "2026-01-01", "--until", "2026-01-31"],
            AUTH,
        )

    @patch("_cli.cli_json")
    def test_invoices_list_without_dates(self, mock_cli_json):
        mock_cli_json.return_value = []
        cli.invoices_list(9, None, None, AUTH)
        mock_cli_json.assert_called_once_with(["invoices", "list", "9"], AUTH)

    @patch("_cli.cli_json")
    def test_transactions_list_all_pages(self, mock_cli_json):
        mock_cli_json.return_value = []
        cli.transactions_list("2026-01-01", "2026-01-31", AUTH, all_pages=True)
        mock_cli_json.assert_called_once_with(
            [
                "transactions",
                "list",
                "--since",
                "2026-01-01",
                "--until",
                "2026-01-31",
                "--all",
            ],
            AUTH,
        )

    @patch("_cli.cli_json")
    def test_budgets_builds_correct_args(self, mock_cli_json):
        mock_cli_json.return_value = [{"category_id": 1}]
        cli.budgets(2026, 6, AUTH)
        mock_cli_json.assert_called_once_with(
            ["budgets", "--year", "2026", "--month", "6"], AUTH
        )

    @patch("_cli.cli_json")
    def test_non_list_response_normalized_to_empty(self, mock_cli_json):
        mock_cli_json.return_value = {"unexpected": "dict"}
        self.assertEqual(cli.accounts_list(AUTH), [])

    @patch("_cli.cli_json")
    def test_non_dict_response_normalized_to_empty(self, mock_cli_json):
        mock_cli_json.return_value = ["unexpected", "list"]
        self.assertEqual(cli.account_get(1, AUTH), {})


class TestLoadAuth(unittest.TestCase):
    def test_missing_auth_file_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cli, "AUTH", pathlib.Path(tmp) / "missing" / ".auth"):
                with self.assertRaises(SystemExit) as ctx:
                    cli.load_auth()
                self.assertIn("err|no-auth|", str(ctx.exception))

    def test_reads_valid_auth_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = pathlib.Path(tmp) / ".auth"
            auth_path.write_text(
                'ORGANIZZE_EMAIL="e@x.com"\nORGANIZZE_TOKEN="tok"\nORGANIZZE_USER_AGENT="ua"\n'
            )
            with patch.object(cli, "AUTH", auth_path):
                self.assertEqual(cli.load_auth(), ("e@x.com", "tok", "ua"))

    def test_missing_key_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = pathlib.Path(tmp) / ".auth"
            auth_path.write_text('ORGANIZZE_EMAIL="e@x.com"\n')
            with patch.object(cli, "AUTH", auth_path):
                with self.assertRaises(SystemExit) as ctx:
                    cli.load_auth()
                self.assertIn("err|bad-auth|", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
