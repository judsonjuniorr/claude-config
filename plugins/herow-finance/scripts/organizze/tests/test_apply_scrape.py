"""Tests for apply_scrape.py merge logic."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

# Load apply_scrape module directly (no package install needed)
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import apply_scrape as _mod


def _snap(**overrides) -> dict:
    base: dict = {
        "accounts": [],
        "transactions_past": [],
        "transactions_future": [],
        "invoices": [],
    }
    base.update(overrides)
    return base


class TestAccountMatch(unittest.TestCase):
    def test_match_by_name_overwrites_balance(self):
        snap = _snap(accounts=[{"id": 1, "name": "Conta Corrente", "_balance_cents": 0}])
        scrape = {"accounts": [{"name": "Conta Corrente", "balance_cents": 55000}]}
        matched, unrec = _mod.apply_dashboard(snap, scrape)
        self.assertEqual(matched, 1)
        self.assertEqual(unrec, [])
        self.assertEqual(snap["accounts"][0]["_balance_cents"], 55000)

    def test_no_match_keeps_api_value(self):
        snap = _snap(accounts=[{"id": 1, "name": "Conta Corrente", "_balance_cents": 12345}])
        scrape = {"accounts": [{"name": "Conta Poupanca", "balance_cents": 99000}]}
        matched, unrec = _mod.apply_dashboard(snap, scrape)
        self.assertEqual(matched, 0)
        self.assertIn("Conta Poupanca", unrec)
        self.assertEqual(snap["accounts"][0]["_balance_cents"], 12345)

    def test_duplicate_name_in_scrape_does_not_match(self):
        snap = _snap(accounts=[{"id": 1, "name": "Conta", "_balance_cents": 0}])
        scrape = {
            "accounts": [
                {"name": "Conta", "balance_cents": 100},
                {"name": "Conta", "balance_cents": 200},
            ]
        }
        import io
        from contextlib import redirect_stderr
        buf = io.StringIO()
        with redirect_stderr(buf):
            matched, unrec = _mod.apply_dashboard(snap, scrape)
        self.assertEqual(matched, 0)
        self.assertGreater(len(unrec), 0)
        self.assertEqual(snap["accounts"][0]["_balance_cents"], 0)


class TestTransactionMatch(unittest.TestCase):
    def test_match_by_dom_id(self):
        snap = _snap(transactions_past=[
            {"id": 1, "dom_id": "tx-111", "date": "2026-05-01", "description": "Mercado", "amount_cents": -100}
        ])
        scrape = {
            "type": "tx", "month": "2026-05",
            "transactions": [{"dom_id": "tx-111", "date": "2026-05-01", "description": "Mercado", "amount_cents": -15000}]
        }
        matched, unrec = _mod.apply_transactions(snap, scrape)
        self.assertEqual(matched, 1)
        self.assertEqual(unrec, [])
        self.assertEqual(snap["transactions_past"][0]["amount_cents"], -15000)

    def test_fallback_date_desc_match(self):
        snap = _snap(transactions_past=[
            {"id": 2, "date": "2026-05-05", "description": "Padaria", "amount_cents": -500}
        ])
        scrape = {
            "type": "tx", "month": "2026-05",
            "transactions": [{"dom_id": None, "date": "2026-05-05", "description": "Padaria", "amount_cents": -600}]
        }
        matched, unrec = _mod.apply_transactions(snap, scrape)
        self.assertEqual(matched, 1)
        self.assertEqual(snap["transactions_past"][0]["amount_cents"], -600)

    def test_collision_matches_in_order(self):
        snap = _snap(transactions_past=[
            {"id": 10, "date": "2026-05-10", "description": "Loja", "amount_cents": -1000},
            {"id": 11, "date": "2026-05-10", "description": "Loja", "amount_cents": -2000},
        ])
        scrape = {
            "type": "tx", "month": "2026-05",
            "transactions": [
                {"dom_id": None, "date": "2026-05-10", "description": "Loja", "amount_cents": -111},
                {"dom_id": None, "date": "2026-05-10", "description": "Loja", "amount_cents": -222},
            ]
        }
        _mod.apply_transactions(snap, scrape)
        self.assertEqual(snap["transactions_past"][0]["amount_cents"], -111)
        self.assertEqual(snap["transactions_past"][1]["amount_cents"], -222)

    def test_unmatched_transaction_goes_to_unreconciled(self):
        snap = _snap(transactions_past=[])
        scrape = {
            "type": "tx", "month": "2026-05",
            "transactions": [{"dom_id": "tx-999", "date": "2026-05-20", "description": "Ghost", "amount_cents": -50}]
        }
        matched, unrec = _mod.apply_transactions(snap, scrape)
        self.assertEqual(matched, 0)
        self.assertEqual(len(unrec), 1)


class TestInvoiceMatch(unittest.TestCase):
    def test_match_by_card_id_and_month(self):
        snap = _snap(invoices=[
            {"_credit_card_id": 42, "date": "2026-05-15", "total_cents": 0}
        ])
        scrape = {"type": "invoice", "card_id": 42, "month": "2026-05", "total_cents": 45000, "transactions": []}
        matched, unrec = _mod.apply_invoice(snap, scrape)
        self.assertEqual(matched, 1)
        self.assertEqual(unrec, [])
        self.assertEqual(snap["invoices"][0]["total_cents"], 45000)


class TestShadowPaths(unittest.TestCase):
    def _run_apply(self, snapshot: dict, scrapes: list[dict]) -> tuple[dict, str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = pathlib.Path(tmpdir)
            scrape_dir = home_dir / "scrape"
            scrape_dir.mkdir()

            for scrape in scrapes:
                fname = scrape.pop("_filename", f"scrape_{id(scrape)}.json")
                (scrape_dir / fname).write_text(json.dumps(scrape))

            snap_path = home_dir / "snapshot.json"
            snap_path.write_text(json.dumps(snapshot))

            old_env = os.environ.get("ORGANIZZE_HOME")
            os.environ["ORGANIZZE_HOME"] = str(home_dir)
            try:
                import io
                from contextlib import redirect_stdout, redirect_stderr
                stdout_buf = io.StringIO()
                # Patch scrape_dir inside main by monkey-patching the env
                # We call main() directly — capture stdout
                import sys as _sys
                old_argv = _sys.argv[:]
                _sys.argv = ["apply_scrape.py", "--snapshot", str(snap_path)]
                try:
                    with redirect_stdout(stdout_buf):
                        try:
                            _mod.main()
                        except SystemExit:
                            pass
                finally:
                    _sys.argv = old_argv
            finally:
                if old_env is None:
                    os.environ.pop("ORGANIZZE_HOME", None)
                else:
                    os.environ["ORGANIZZE_HOME"] = old_env

            result_snapshot = json.loads(snap_path.read_text())
            return result_snapshot, stdout_buf.getvalue()

    def test_empty_scrape_warns(self):
        snap = _snap(accounts=[{"id": 1, "name": "X", "_balance_cents": 100}])
        result, out = self._run_apply(snap, [])
        self.assertIn("warn", out)

    def test_empty_scrape_object_keeps_snapshot_intact(self):
        snap = _snap(accounts=[{"id": 1, "name": "X", "_balance_cents": 100}])
        scrape = {"_filename": "dashboard.json", "type": "dashboard", "accounts": []}
        result, out = self._run_apply(snap, [scrape])
        self.assertEqual(result["accounts"][0]["_balance_cents"], 100)

    def test_idempotent_double_apply(self):
        snap = _snap(accounts=[{"id": 1, "name": "Conta", "_balance_cents": 0}])
        scrape1 = {"_filename": "dashboard.json", "type": "dashboard", "accounts": [{"name": "Conta", "balance_cents": 99000}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = pathlib.Path(tmpdir)
            scrape_dir = home_dir / "scrape"
            scrape_dir.mkdir()
            (scrape_dir / "dashboard.json").write_text(json.dumps({"type": "dashboard", "accounts": [{"name": "Conta", "balance_cents": 99000}]}))

            snap_path = home_dir / "snapshot.json"
            snap_path.write_text(json.dumps(snap))

            old_env = os.environ.get("ORGANIZZE_HOME")
            os.environ["ORGANIZZE_HOME"] = str(home_dir)
            import sys as _sys
            old_argv = _sys.argv[:]
            try:
                _sys.argv = ["apply_scrape.py", "--snapshot", str(snap_path)]
                try:
                    _mod.main()
                except SystemExit:
                    pass
                result1 = json.loads(snap_path.read_text())

                _sys.argv = ["apply_scrape.py", "--snapshot", str(snap_path)]
                try:
                    _mod.main()
                except SystemExit:
                    pass
                result2 = json.loads(snap_path.read_text())
            finally:
                _sys.argv = old_argv
                if old_env is None:
                    os.environ.pop("ORGANIZZE_HOME", None)
                else:
                    os.environ["ORGANIZZE_HOME"] = old_env

            self.assertEqual(result1["accounts"][0]["_balance_cents"], result2["accounts"][0]["_balance_cents"])

    def test_multiple_slices_consolidated(self):
        snap = _snap(
            accounts=[{"id": 1, "name": "Conta", "_balance_cents": 0}],
            transactions_past=[{"id": 5, "dom_id": "tx-5", "date": "2026-05-01", "description": "X", "amount_cents": 0}],
            invoices=[{"_credit_card_id": 7, "date": "2026-05-10", "total_cents": 0}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = pathlib.Path(tmpdir)
            scrape_dir = home_dir / "scrape"
            scrape_dir.mkdir()

            (scrape_dir / "dashboard.json").write_text(json.dumps({
                "type": "dashboard",
                "accounts": [{"name": "Conta", "balance_cents": 11111}],
            }))
            (scrape_dir / "tx_2026-05.json").write_text(json.dumps({
                "type": "tx", "month": "2026-05",
                "transactions": [{"dom_id": "tx-5", "date": "2026-05-01", "description": "X", "amount_cents": -500}],
            }))
            (scrape_dir / "invoice_7_2026-05.json").write_text(json.dumps({
                "type": "invoice", "card_id": 7, "month": "2026-05",
                "total_cents": 33000, "transactions": [],
            }))

            snap_path = home_dir / "snapshot.json"
            snap_path.write_text(json.dumps(snap))

            old_env = os.environ.get("ORGANIZZE_HOME")
            os.environ["ORGANIZZE_HOME"] = str(home_dir)
            import sys as _sys
            old_argv = _sys.argv[:]
            _sys.argv = ["apply_scrape.py", "--snapshot", str(snap_path)]
            try:
                try:
                    _mod.main()
                except SystemExit:
                    pass
            finally:
                _sys.argv = old_argv
                if old_env is None:
                    os.environ.pop("ORGANIZZE_HOME", None)
                else:
                    os.environ["ORGANIZZE_HOME"] = old_env

            result = json.loads(snap_path.read_text())
            self.assertEqual(result["accounts"][0]["_balance_cents"], 11111)
            self.assertEqual(result["transactions_past"][0]["amount_cents"], -500)
            self.assertEqual(result["invoices"][0]["total_cents"], 33000)
            self.assertIn("_scrape_meta", result)
            self.assertEqual(len(result["_scrape_meta"]["slices"]), 3)


class TestMalformedScrape(unittest.TestCase):
    def test_malformed_json_exits_with_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = pathlib.Path(tmpdir)
            scrape_dir = home_dir / "scrape"
            scrape_dir.mkdir()
            (scrape_dir / "bad.json").write_text("{not valid json")

            snap_path = home_dir / "snapshot.json"
            snap_path.write_text(json.dumps(_snap()))

            old_env = os.environ.get("ORGANIZZE_HOME")
            os.environ["ORGANIZZE_HOME"] = str(home_dir)
            import sys as _sys
            old_argv = _sys.argv[:]
            _sys.argv = ["apply_scrape.py", "--snapshot", str(snap_path)]
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            exit_code = None
            try:
                with redirect_stdout(buf):
                    try:
                        _mod.main()
                    except SystemExit as e:
                        exit_code = e.code
            finally:
                _sys.argv = old_argv
                if old_env is None:
                    os.environ.pop("ORGANIZZE_HOME", None)
                else:
                    os.environ["ORGANIZZE_HOME"] = old_env

            self.assertIn("err|malformed-scrape", buf.getvalue())
            # snapshot must not be corrupted
            snap_content = json.loads(snap_path.read_text())
            self.assertIn("accounts", snap_content)


if __name__ == "__main__":
    unittest.main()
