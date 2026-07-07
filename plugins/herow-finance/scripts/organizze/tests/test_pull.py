"""Tests for pull.py's CLI-backed read path — no network.

fetch_account_balances and fetch_history_5y are the core behavioral change of
the urllib->CLI migration (real balance vs 5-year-summation reconstruction);
these tests monkeypatch pull's _cli imports (account_get, transactions_list)
to verify them with no subprocess/network.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

# Hermetic data dir BEFORE importing pull (HOME/CACHE derive from ORGANIZZE_HOME).
os.environ["ORGANIZZE_HOME"] = tempfile.mkdtemp(prefix="org-pull-test-")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pull as p  # noqa: E402

AUTH = ("e@x.com", "tok123456", "ua/1.0 (e@x.com)")


class TestFetchAccountBalances(unittest.TestCase):
    def setUp(self):
        self._orig_account_get = p.account_get
        self._balances_path = p.HOME / "balances.json"

    def tearDown(self):
        p.account_get = self._orig_account_get
        if self._balances_path.exists():
            self._balances_path.unlink()

    def test_reads_real_balance_per_account(self):
        detail_by_id = {1: {"id": 1, "balance": 80174}, 2: {"id": 2, "balance": -5000}}
        p.account_get = lambda acc_id, auth: detail_by_id[acc_id]
        result = p.fetch_account_balances(
            [{"id": 1, "name": "Nubank"}, {"id": 2, "name": "Itau"}], AUTH
        )
        self.assertEqual(result, {1: 80174, 2: -5000})

    def test_skips_accounts_without_id(self):
        p.account_get = lambda acc_id, auth: {"balance": 100}
        result = p.fetch_account_balances([{"name": "no-id-account"}], AUTH)
        self.assertEqual(result, {})

    def test_missing_balance_field_defaults_zero(self):
        p.account_get = lambda acc_id, auth: {"id": acc_id}
        result = p.fetch_account_balances([{"id": 3}], AUTH)
        self.assertEqual(result, {3: 0})

    def test_manual_offset_added_on_top_of_real_balance(self):
        p.account_get = lambda acc_id, auth: {"id": acc_id, "balance": 10000}
        self._balances_path.write_text(json.dumps({"1": 500}))
        result = p.fetch_account_balances([{"id": 1}], AUTH)
        self.assertEqual(result, {1: 10500})

    def test_offset_for_unknown_account_id_still_applied(self):
        # An offset can exist for an account not passed in (e.g. archived) —
        # matches the old reconstruction's offset-merge behavior.
        p.account_get = lambda acc_id, auth: {"id": acc_id, "balance": 100}
        self._balances_path.write_text(json.dumps({"1": 500, "99": 250}))
        result = p.fetch_account_balances([{"id": 1}], AUTH)
        self.assertEqual(result, {1: 600, 99: 250})

    def test_corrupt_offsets_file_does_not_crash(self):
        p.account_get = lambda acc_id, auth: {"id": acc_id, "balance": 100}
        self._balances_path.write_text("not json")
        result = p.fetch_account_balances([{"id": 1}], AUTH)
        self.assertEqual(result, {1: 100})

    def test_one_account_cli_error_aborts_whole_pull(self):
        # Documents current all-or-nothing behavior: cli_json's SystemExit on a
        # CLI error (e.g. one bad/edge account id) propagates and aborts the
        # entire balance fetch rather than degrading gracefully per-account.
        def flaky_account_get(acc_id, auth):
            if acc_id == 2:
                sys.exit("err|not-found|/accounts/2")
            return {"id": acc_id, "balance": 100}

        p.account_get = flaky_account_get
        with self.assertRaises(SystemExit) as ctx:
            p.fetch_account_balances([{"id": 1}, {"id": 2}], AUTH)
        self.assertIn("err|not-found", str(ctx.exception))


class TestFetchHistory5y(unittest.TestCase):
    def setUp(self):
        self._orig_transactions_list = p.transactions_list

    def tearDown(self):
        p.transactions_list = self._orig_transactions_list

    def test_dedupes_by_id(self):
        def fake_transactions_list(since, until, auth, all_pages=True):
            self.assertTrue(all_pages)
            return [
                {"id": 1, "description": "a"},
                {"id": 1, "description": "a-dup"},
                {"id": 2, "description": "b"},
            ]

        p.transactions_list = fake_transactions_list
        result = p.fetch_history_5y(AUTH)
        self.assertEqual(len(result), 2)
        self.assertEqual({t["id"] for t in result}, {1, 2})

    def test_ignores_rows_without_id(self):
        p.transactions_list = lambda since, until, auth, all_pages=True: [
            {"description": "no id"},
            {"id": 5, "description": "has id"},
        ]
        result = p.fetch_history_5y(AUTH)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 5)

    def test_empty_history(self):
        p.transactions_list = lambda since, until, auth, all_pages=True: []
        self.assertEqual(p.fetch_history_5y(AUTH), [])


if __name__ == "__main__":
    unittest.main()
