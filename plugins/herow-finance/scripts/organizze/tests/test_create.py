"""Tests for create.py — Organizze write path. No network.

Pure functions are tested directly. The dry-run/apply contract is tested by
monkeypatching create.http_get/http_post (no real requests).
"""
import importlib
import pathlib
import sys
import tempfile
import unittest

# Hermetic data dir BEFORE importing create (CACHE derives from ORGANIZZE_HOME).
import os
os.environ["ORGANIZZE_HOME"] = tempfile.mkdtemp(prefix="org-create-test-")

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import create as c  # noqa: E402

importlib.reload(c)


# --- 1. normalize_amount sign matrix ---------------------------------------

class TestNormalizeAmount(unittest.TestCase):
    def test_expense_negative(self):
        self.assertEqual(c.normalize_amount(50, "expense"), -5000)

    def test_income_positive(self):
        self.assertEqual(c.normalize_amount(50, "income"), 5000)

    def test_string_pt_decimal(self):
        self.assertEqual(c.normalize_amount("50,00", "expense"), -5000)
        self.assertEqual(c.normalize_amount("1.234,56", "income"), 123456)

    def test_string_en_decimal(self):
        self.assertEqual(c.normalize_amount("50.00", "expense"), -5000)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            c.normalize_amount(0, "expense")
        self.assertEqual(str(ctx.exception), "validation|amount")

    def test_garbage_rejected(self):
        with self.assertRaises(ValueError):
            c.normalize_amount("abc", "expense")


# --- 2/3/4/5. build_transaction_payload ------------------------------------

class TestBuildTransactionPayload(unittest.TestCase):
    def _base(self, **kw):
        base = {"description": "Mercado", "amount_cents": -5000, "date": "2026-06-14"}
        base.update(kw)
        return base

    def test_account_mode(self):
        p = c.build_transaction_payload(self._base(target="account", account_id=3))
        self.assertEqual(p["account_id"], 3)
        self.assertNotIn("credit_card_id", p)
        self.assertNotIn("credit_card_invoice_id", p)

    def test_card_mode(self):
        p = c.build_transaction_payload(
            self._base(target="card", credit_card_id=3, credit_card_invoice_id=189))
        self.assertEqual(p["credit_card_id"], 3)
        self.assertEqual(p["credit_card_invoice_id"], 189)
        self.assertNotIn("account_id", p)

    def test_invoice_mode_uses_picked_id(self):
        p = c.build_transaction_payload(
            self._base(target="invoice", credit_card_id=3, credit_card_invoice_id=777))
        self.assertEqual(p["credit_card_invoice_id"], 777)
        self.assertNotIn("account_id", p)

    def test_installments(self):
        p = c.build_transaction_payload(
            self._base(target="card", credit_card_id=3, credit_card_invoice_id=189,
                       installments=3))
        self.assertEqual(p["installments_attributes"], {"periodicity": "monthly", "total": 3})

    def test_recurrence(self):
        p = c.build_transaction_payload(
            self._base(target="account", account_id=3, recurrence="monthly"))
        self.assertEqual(p["recurrence_attributes"], {"periodicity": "monthly"})

    def test_installments_recurrence_mutually_exclusive(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(
                self._base(target="account", account_id=3, installments=2, recurrence="monthly"))
        self.assertEqual(str(ctx.exception), "validation|installments-recurrence")

    def test_empty_description_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(self._base(description="  ", target="account", account_id=3))
        self.assertEqual(str(ctx.exception), "validation|description")

    def test_category_and_paid_passthrough(self):
        p = c.build_transaction_payload(
            self._base(target="account", account_id=3, category_id=12, paid=True))
        self.assertEqual(p["category_id"], 12)
        self.assertTrue(p["paid"])


# --- 6. build_transfer_payload ---------------------------------------------

class TestBuildTransferPayload(unittest.TestCase):
    def test_happy(self):
        p = c.build_transfer_payload({
            "credit_account_id": 7, "debit_account_id": 3,
            "amount_cents": 50000, "date": "2026-06-14", "paid": True})
        self.assertEqual(p["credit_account_id"], 7)
        self.assertEqual(p["debit_account_id"], 3)
        self.assertEqual(p["amount_cents"], 50000)
        self.assertTrue(p["paid"])

    def test_rejects_card(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transfer_payload({
                "credit_account_id": 7, "debit_account_id": 3, "amount_cents": 100,
                "date": "2026-06-14", "src_is_card": True})
        self.assertEqual(str(ctx.exception), "validation|transfer-card")

    def test_rejects_nonpositive(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transfer_payload({
                "credit_account_id": 7, "debit_account_id": 3, "amount_cents": 0,
                "date": "2026-06-14"})
        self.assertEqual(str(ctx.exception), "validation|amount")


# --- 7. resolve_entity ------------------------------------------------------

class TestResolveEntity(unittest.TestCase):
    items = [{"id": 1, "name": "Nubank"}, {"id": 2, "name": "Itaú"},
             {"id": 3, "name": "Nu Conta"}]

    def test_unique_match(self):
        r = c.resolve_entity("itau", self.items)
        self.assertEqual(r["status"], "match")
        self.assertEqual(r["item"]["id"], 2)

    def test_exact_wins_over_substring(self):
        r = c.resolve_entity("Nubank", self.items)
        self.assertEqual(r["status"], "match")
        self.assertEqual(r["item"]["id"], 1)

    def test_ambiguous(self):
        r = c.resolve_entity("nu", self.items)
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(len(r["items"]), 2)

    def test_none(self):
        self.assertEqual(c.resolve_entity("xyz", self.items)["status"], "none")


# --- 8. resolve_invoice_for_date -------------------------------------------

class TestResolveInvoice(unittest.TestCase):
    invoices = [
        {"id": 100, "starting_date": "2026-05-20", "closing_date": "2026-06-19", "date": "2026-06-01"},
        {"id": 101, "starting_date": "2026-06-20", "closing_date": "2026-07-19", "date": "2026-07-01"},
    ]

    def test_in_period(self):
        self.assertEqual(c.resolve_invoice_for_date("2026-06-14", self.invoices)["id"], 100)

    def test_near_closing_next_period(self):
        self.assertEqual(c.resolve_invoice_for_date("2026-06-25", self.invoices)["id"], 101)

    def test_fallback_by_month(self):
        invs = [{"id": 5, "date": "2026-06-10"}]
        self.assertEqual(c.resolve_invoice_for_date("2026-06-30", invs)["id"], 5)

    def test_none(self):
        self.assertIsNone(c.resolve_invoice_for_date("2030-01-01", self.invoices))


# --- 9. find_duplicates -----------------------------------------------------

class TestFindDuplicates(unittest.TestCase):
    recent = [
        {"id": 1, "amount_cents": -5000, "description": "Mercado", "date": "2026-06-14"},
        {"id": 2, "amount_cents": -5000, "description": "Mercado", "date": "2026-06-10"},
        {"id": 3, "amount_cents": -9900, "description": "Posto", "date": "2026-06-14"},
    ]

    def test_match_same_amount_desc_date(self):
        dups = c.find_duplicates(
            {"amount_cents": -5000, "description": "mercado", "date": "2026-06-14"}, self.recent)
        self.assertEqual([d["id"] for d in dups], [1])

    def test_no_match_different_date(self):
        dups = c.find_duplicates(
            {"amount_cents": -5000, "description": "Mercado", "date": "2026-06-12"}, self.recent)
        self.assertEqual(dups, [])


# --- 10. suggest_category ---------------------------------------------------

class TestSuggestCategory(unittest.TestCase):
    cats = [{"id": 12, "name": "Mercado"}, {"id": 20, "name": "Transporte"}]
    history = [
        {"description": "Mercado Extra", "category_id": 12},
        {"description": "Mercado Pão", "category_id": 12},
        {"description": "Uber centro", "category_id": 20},
    ]

    def test_most_frequent_for_fuzzy(self):
        out = c.suggest_category("mercado dia", self.history, self.cats)
        self.assertTrue(out)
        self.assertEqual(out[0]["id"], 12)

    def test_empty_history(self):
        self.assertEqual(c.suggest_category("mercado", [], self.cats), [])

    def test_no_overlap(self):
        self.assertEqual(c.suggest_category("farmacia", self.history, self.cats), [])


# --- 11. verify_created -----------------------------------------------------

class TestVerifyCreated(unittest.TestCase):
    def test_ok_match(self):
        r = c.verify_created({"id": 99, "amount_cents": -5000, "description": "Mercado"},
                             {"amount_cents": -5000, "description": "Mercado"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["id"], 99)

    def test_missing_id(self):
        r = c.verify_created({"amount_cents": -5000}, {"amount_cents": -5000})
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "missing-id")

    def test_amount_mismatch(self):
        r = c.verify_created({"id": 1, "amount_cents": -1}, {"amount_cents": -5000})
        self.assertFalse(r["ok"])

    def test_non_dict(self):
        self.assertFalse(c.verify_created("oops", {})["ok"])

    def test_installments_list_count(self):
        r = c.verify_created([{"id": 1}, {"id": 2}, {"id": 3}], {"amount_cents": -1})
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 3)


# --- 12. dry-run / apply contract (monkeypatched http) ----------------------

class _FakeHTTP:
    """Routes http_get by path; counts http_post calls."""
    def __init__(self):
        self.posts = []

    def get(self, path, params, *auth):
        if path == "/accounts":
            return [{"id": 3, "name": "Nubank", "type": "checking"}]
        if path == "/credit_cards":
            return []
        if path == "/categories":
            return [{"id": 12, "name": "Mercado"}]
        if path == "/transactions":
            return []
        return []

    def post(self, path, body, *auth):
        self.posts.append((path, body))
        return {"id": 555, "amount_cents": body.get("amount_cents"),
                "description": body.get("description")}


class TestDryRunApply(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeHTTP()
        self._orig_get, self._orig_post, self._orig_auth = c.http_get, c.http_post, c.load_auth
        c.http_get = self.fake.get
        c.http_post = self.fake.post
        c.load_auth = lambda: ("e@x", "tok123456", "ua")

    def tearDown(self):
        c.http_get, c.http_post, c.load_auth = self._orig_get, self._orig_post, self._orig_auth

    def test_dry_run_does_not_post(self):
        rc = c.main(["--conta", "Nubank", "--despesa", "--valor", "10",
                     "--data", "2026-06-14", "teste"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.posts, [], "dry-run must not POST")

    def test_apply_posts_once_and_verifies(self):
        rc = c.main(["--apply", "--force", "--conta", "Nubank", "--despesa",
                     "--valor", "10", "--data", "2026-06-14", "teste"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.fake.posts), 1)
        path, body = self.fake.posts[0]
        self.assertEqual(path, "/transactions")
        self.assertEqual(body["amount_cents"], -1000)
        self.assertEqual(body["account_id"], 3)
        self.assertTrue(body["paid"], "past-dated expense defaults paid")


# --- resolve_paid: date-aware default + explicit override ------------------

class TestResolvePaid(unittest.TestCase):
    def _ns(self, **kw):
        import argparse
        base = {"paga": False, "nao_paga": False}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_past_defaults_paid(self):
        self.assertTrue(c.resolve_paid(self._ns(), "2020-01-01"))

    def test_future_defaults_pending(self):
        self.assertFalse(c.resolve_paid(self._ns(), "2999-01-01"))

    def test_explicit_paga_wins(self):
        self.assertTrue(c.resolve_paid(self._ns(paga=True), "2999-01-01"))

    def test_explicit_nao_paga_wins(self):
        self.assertFalse(c.resolve_paid(self._ns(nao_paga=True), "2020-01-01"))


# --- 13. command file contract ---------------------------------------------

class TestCommandFile(unittest.TestCase):
    md = (pathlib.Path(__file__).resolve().parents[3]
          / "commands" / "organizze-create.md")

    def test_exists(self):
        self.assertTrue(self.md.exists())

    def test_frontmatter(self):
        text = self.md.read_text()
        self.assertIn("argument-hint:", text)
        self.assertIn("allowed-tools: Bash, Read, AskUserQuestion", text)

    def test_onboarding_fallback(self):
        self.assertIn("onboarding", self.md.read_text().lower())


if __name__ == "__main__":
    unittest.main()
