"""Tests for create.py — Organizze write path. No network.

Pure functions are tested directly. The dry-run/apply contract is tested by
monkeypatching create's _cli read helpers (accounts_list/credit_cards_list/
categories_list/transactions_list) and create.http_post/load_auth — reads go
through the `organizze` CLI, writes stay on hand-rolled http_post.
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
            self._base(target="card", credit_card_id=3, credit_card_invoice_id=189)
        )
        self.assertEqual(p["credit_card_id"], 3)
        self.assertEqual(p["credit_card_invoice_id"], 189)
        self.assertNotIn("account_id", p)

    def test_invoice_mode_uses_picked_id(self):
        p = c.build_transaction_payload(
            self._base(target="invoice", credit_card_id=3, credit_card_invoice_id=777)
        )
        self.assertEqual(p["credit_card_invoice_id"], 777)
        self.assertNotIn("account_id", p)

    def test_installments(self):
        p = c.build_transaction_payload(
            self._base(
                target="card",
                credit_card_id=3,
                credit_card_invoice_id=189,
                installments=3,
            )
        )
        self.assertEqual(
            p["installments_attributes"], {"periodicity": "monthly", "total": 3}
        )

    def test_recurrence(self):
        p = c.build_transaction_payload(
            self._base(target="account", account_id=3, recurrence="monthly")
        )
        self.assertEqual(p["recurrence_attributes"], {"periodicity": "monthly"})

    def test_installments_recurrence_mutually_exclusive(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(
                self._base(
                    target="account", account_id=3, installments=2, recurrence="monthly"
                )
            )
        self.assertEqual(str(ctx.exception), "validation|installments-recurrence")

    def test_empty_description_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(
                self._base(description="  ", target="account", account_id=3)
            )
        self.assertEqual(str(ctx.exception), "validation|description")

    def test_category_and_paid_passthrough(self):
        p = c.build_transaction_payload(
            self._base(target="account", account_id=3, category_id=12, paid=True)
        )
        self.assertEqual(p["category_id"], 12)
        self.assertTrue(p["paid"])


# --- 6. build_transfer_payload ---------------------------------------------


class TestBuildTransferPayload(unittest.TestCase):
    def test_happy(self):
        p = c.build_transfer_payload(
            {
                "credit_account_id": 7,
                "debit_account_id": 3,
                "amount_cents": 50000,
                "date": "2026-06-14",
                "paid": True,
            }
        )
        self.assertEqual(p["credit_account_id"], 7)
        self.assertEqual(p["debit_account_id"], 3)
        self.assertEqual(p["amount_cents"], 50000)
        self.assertTrue(p["paid"])

    def test_rejects_card(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transfer_payload(
                {
                    "credit_account_id": 7,
                    "debit_account_id": 3,
                    "amount_cents": 100,
                    "date": "2026-06-14",
                    "src_is_card": True,
                }
            )
        self.assertEqual(str(ctx.exception), "validation|transfer-card")

    def test_rejects_nonpositive(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transfer_payload(
                {
                    "credit_account_id": 7,
                    "debit_account_id": 3,
                    "amount_cents": 0,
                    "date": "2026-06-14",
                }
            )
        self.assertEqual(str(ctx.exception), "validation|amount")


# --- 7. resolve_entity ------------------------------------------------------


class TestResolveEntity(unittest.TestCase):
    items = [
        {"id": 1, "name": "Nubank"},
        {"id": 2, "name": "Itaú"},
        {"id": 3, "name": "Nu Conta"},
    ]

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
        {
            "id": 100,
            "starting_date": "2026-05-20",
            "closing_date": "2026-06-19",
            "date": "2026-06-01",
        },
        {
            "id": 101,
            "starting_date": "2026-06-20",
            "closing_date": "2026-07-19",
            "date": "2026-07-01",
        },
    ]

    def test_in_period(self):
        self.assertEqual(
            c.resolve_invoice_for_date("2026-06-14", self.invoices)["id"], 100
        )

    def test_near_closing_next_period(self):
        self.assertEqual(
            c.resolve_invoice_for_date("2026-06-25", self.invoices)["id"], 101
        )

    def test_fallback_by_month(self):
        invs = [{"id": 5, "date": "2026-06-10"}]
        self.assertEqual(c.resolve_invoice_for_date("2026-06-30", invs)["id"], 5)

    def test_none(self):
        self.assertIsNone(c.resolve_invoice_for_date("2030-01-01", self.invoices))


# --- 9. find_duplicates -----------------------------------------------------


class TestFindDuplicates(unittest.TestCase):
    recent = [
        {
            "id": 1,
            "amount_cents": -5000,
            "description": "Mercado",
            "date": "2026-06-14",
        },
        {
            "id": 2,
            "amount_cents": -5000,
            "description": "Mercado",
            "date": "2026-06-10",
        },
        {"id": 3, "amount_cents": -9900, "description": "Posto", "date": "2026-06-14"},
    ]

    def test_match_same_amount_desc_date(self):
        dups = c.find_duplicates(
            {"amount_cents": -5000, "description": "mercado", "date": "2026-06-14"},
            self.recent,
        )
        self.assertEqual([d["id"] for d in dups], [1])

    def test_no_match_different_date(self):
        dups = c.find_duplicates(
            {"amount_cents": -5000, "description": "Mercado", "date": "2026-06-12"},
            self.recent,
        )
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
        r = c.verify_created(
            {"id": 99, "amount_cents": -5000, "description": "Mercado"},
            {"amount_cents": -5000, "description": "Mercado"},
        )
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
        r = c.verify_created(
            [{"id": 1}, {"id": 2}, {"id": 3}], {"amount_cents": -1, "installments": 3}
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 3)

    def test_installments_single_dict_total(self):
        # api-doc: installment create returns ONE dict with total_installments.
        r = c.verify_created(
            {"id": 97, "total_installments": 12, "amount_cents": 0},
            {"installments": 12},
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 12)

    def test_installments_count_mismatch(self):
        r = c.verify_created({"id": 97, "total_installments": 3}, {"installments": 12})
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "installment-count")


# --- kind guard + periodicity validation -----------------------------------


class TestKindGuard(unittest.TestCase):
    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            c.normalize_amount(10, "expanse")  # typo
        self.assertEqual(str(ctx.exception), "validation|kind")


class TestPeriodicityValidation(unittest.TestCase):
    def _tx(self, **kw):
        base = {
            "description": "X",
            "amount_cents": -1000,
            "date": "2026-06-14",
            "target": "account",
            "account_id": 3,
        }
        base.update(kw)
        return base

    def test_invalid_installment_periodicity(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(
                self._tx(installments=3, periodicity="quarterly")
            )
        self.assertEqual(str(ctx.exception), "validation|periodicity")

    def test_invalid_recurrence_periodicity(self):
        with self.assertRaises(ValueError) as ctx:
            c.build_transaction_payload(self._tx(recurrence="daily"))
        self.assertEqual(str(ctx.exception), "validation|periodicity")

    def test_valid_trimonthly(self):
        p = c.build_transaction_payload(
            self._tx(installments=2, periodicity="trimonthly")
        )
        self.assertEqual(p["installments_attributes"]["periodicity"], "trimonthly")


# --- 12. dry-run / apply contract (monkeypatched http) ----------------------


class _FakeCLI:
    """Routes the _cli read helpers create.py imported; counts http_post calls."""

    def __init__(self):
        self.posts = []

    def accounts_list(self, auth):
        return [{"id": 3, "name": "Nubank", "type": "checking"}]

    def credit_cards_list(self, auth):
        return []

    def categories_list(self, auth):
        return [{"id": 12, "name": "Mercado"}]

    def transactions_list(self, since, until, auth, all_pages=True):
        return []

    def post(self, path, body, *auth):
        self.posts.append((path, body))
        return {
            "id": 555,
            "amount_cents": body.get("amount_cents"),
            "description": body.get("description"),
        }


class TestDryRunApply(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeCLI()
        self._orig = (
            c.accounts_list,
            c.credit_cards_list,
            c.categories_list,
            c.transactions_list,
            c.http_post,
            c.load_auth,
        )
        c.accounts_list = self.fake.accounts_list
        c.credit_cards_list = self.fake.credit_cards_list
        c.categories_list = self.fake.categories_list
        c.transactions_list = self.fake.transactions_list
        c.http_post = self.fake.post
        c.load_auth = lambda: ("e@x", "tok123456", "ua")

    def tearDown(self):
        (
            c.accounts_list,
            c.credit_cards_list,
            c.categories_list,
            c.transactions_list,
            c.http_post,
            c.load_auth,
        ) = self._orig

    def test_dry_run_does_not_post(self):
        rc = c.main(
            [
                "--conta",
                "Nubank",
                "--despesa",
                "--valor",
                "10",
                "--data",
                "2026-06-14",
                "teste",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.posts, [], "dry-run must not POST")

    def test_apply_posts_once_and_verifies(self):
        rc = c.main(
            [
                "--apply",
                "--force",
                "--conta",
                "Nubank",
                "--despesa",
                "--valor",
                "10",
                "--data",
                "2026-06-14",
                "teste",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.fake.posts), 1)
        path, body = self.fake.posts[0]
        self.assertEqual(path, "/transactions")
        self.assertEqual(body["amount_cents"], -1000)
        self.assertEqual(body["account_id"], 3)
        self.assertTrue(body["paid"], "past-dated expense defaults paid")


# --- run-level: transfer direction, dup-abort, input-file, verify-fail ------


class _RunFake:
    """Two bank accounts + a card; routes reads, captures POST + a tunable response."""

    def __init__(self, recent=None, post_resp=None, invoices=None):
        self.posts = []
        self._recent = recent or []
        self._post_resp = post_resp
        self._invoices = (
            invoices
            if invoices is not None
            else [
                {
                    "id": 501,
                    "date": "2026-06-01",
                    "starting_date": "2026-05-20",
                    "closing_date": "2026-06-19",
                }
            ]
        )

    def accounts_list(self, auth):
        return [
            {"id": 3, "name": "Origem", "type": "checking"},
            {"id": 7, "name": "Destino", "type": "checking"},
        ]

    def credit_cards_list(self, auth):
        return [{"id": 9, "name": "Visa"}]

    def categories_list(self, auth):
        return [{"id": 12, "name": "Mercado"}]

    def invoices_list(self, credit_card_id, since, until, auth):
        return self._invoices

    def transactions_list(self, since, until, auth, all_pages=True):
        return self._recent

    def post(self, path, body, *auth):
        self.posts.append((path, body))
        if self._post_resp is not None:
            return self._post_resp
        return {
            "id": 99,
            "amount_cents": body.get("amount_cents", 0),
            "description": body.get("description"),
        }


class _RunPatch(unittest.TestCase):
    fake_kwargs: dict = {}

    def setUp(self):
        self.fake = _RunFake(**self.fake_kwargs)
        self._orig = (
            c.accounts_list,
            c.credit_cards_list,
            c.categories_list,
            c.invoices_list,
            c.transactions_list,
            c.http_post,
            c.load_auth,
        )
        c.accounts_list = self.fake.accounts_list
        c.credit_cards_list = self.fake.credit_cards_list
        c.categories_list = self.fake.categories_list
        c.invoices_list = self.fake.invoices_list
        c.transactions_list = self.fake.transactions_list
        c.http_post = self.fake.post
        c.load_auth = lambda: ("e@x", "tok123456", "ua")

    def tearDown(self):
        (
            c.accounts_list,
            c.credit_cards_list,
            c.categories_list,
            c.invoices_list,
            c.transactions_list,
            c.http_post,
            c.load_auth,
        ) = self._orig


class TestTransferRun(_RunPatch):
    def test_direction_de_is_credit_para_is_debit(self):
        rc = c.main(
            [
                "--apply",
                "--force",
                "--transferencia",
                "--de",
                "Origem",
                "--para",
                "Destino",
                "--valor",
                "100",
                "--data",
                "2026-06-14",
            ]
        )
        self.assertEqual(rc, 0)
        path, body = self.fake.posts[0]
        self.assertEqual(path, "/transfers")
        # --de (origem, money leaves) → credit_account_id per api-doc.
        self.assertEqual(body["credit_account_id"], 3)
        self.assertEqual(body["debit_account_id"], 7)
        self.assertEqual(body["amount_cents"], 10000)  # positive


class TestCardInvoiceResolution(_RunPatch):
    """--cartao without --fatura resolves the invoice via _cli.invoices_list."""

    def test_resolves_invoice_in_closing_window(self):
        rc = c.main(
            [
                "--apply",
                "--force",
                "--cartao",
                "Visa",
                "--despesa",
                "--valor",
                "50",
                "--data",
                "2026-06-14",  # falls inside the fake's 2026-05-20..2026-06-19 window
                "compra",
            ]
        )
        self.assertEqual(rc, 0)
        path, body = self.fake.posts[0]
        self.assertEqual(path, "/transactions")
        self.assertEqual(body["credit_card_id"], 9)
        self.assertEqual(body["credit_card_invoice_id"], 501)
        self.assertNotIn("account_id", body)


class TestCardInvoiceResolutionApprox(_RunPatch):
    """No starting/closing window on the invoice — falls back to date[:7] match, tagged approx."""

    fake_kwargs = {
        "invoices": [{"id": 502, "date": "2026-06-01"}],
    }

    def test_resolves_via_month_fallback(self):
        rc = c.main(
            [
                "--apply",
                "--force",
                "--cartao",
                "Visa",
                "--despesa",
                "--valor",
                "50",
                "--data",
                "2026-06-20",
                "compra",
            ]
        )
        self.assertEqual(rc, 0)
        path, body = self.fake.posts[0]
        self.assertEqual(body["credit_card_invoice_id"], 502)


class TestCardInvoiceUnresolved(_RunPatch):
    fake_kwargs = {"invoices": []}

    def test_no_matching_invoice_exits(self):
        with self.assertRaises(SystemExit) as ctx:
            c.main(
                [
                    "--apply",
                    "--force",
                    "--cartao",
                    "Visa",
                    "--despesa",
                    "--valor",
                    "50",
                    "--data",
                    "2026-06-14",
                    "compra",
                ]
            )
        self.assertIn("err|invoice-unresolved", str(ctx.exception))


class TestDuplicateAbort(_RunPatch):
    fake_kwargs = {
        "recent": [
            {
                "id": 1,
                "amount_cents": -1000,
                "description": "teste",
                "date": "2026-06-14",
            }
        ]
    }

    def test_apply_without_force_aborts_on_duplicate(self):
        with self.assertRaises(SystemExit) as ctx:
            c.main(
                [
                    "--apply",
                    "--conta",
                    "Origem",
                    "--despesa",
                    "--valor",
                    "10",
                    "--data",
                    "2026-06-14",
                    "teste",
                ]
            )
        self.assertIn("err|duplicate", str(ctx.exception))
        self.assertEqual(self.fake.posts, [], "must not POST when duplicate aborts")


class TestVerifyFailRun(_RunPatch):
    fake_kwargs = {"post_resp": {"amount_cents": -1000}}  # no id

    def test_missing_id_returns_rc2(self):
        rc = c.main(
            [
                "--apply",
                "--force",
                "--conta",
                "Origem",
                "--despesa",
                "--valor",
                "10",
                "--data",
                "2026-06-14",
                "teste",
            ]
        )
        self.assertEqual(rc, 2)


class TestInputFileInjectionSafe(_RunPatch):
    def test_free_text_from_file_not_shell(self):
        import json as _json
        import tempfile

        payload = {"description": "café `rm -rf`; $(whoami)", "notes": 'n8"o'}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            _json.dump(payload, f)
            path = f.name
        rc = c.main(
            [
                "--apply",
                "--force",
                "--input-file",
                path,
                "--conta",
                "Origem",
                "--despesa",
                "--valor",
                "10",
                "--data",
                "2026-06-14",
            ]
        )
        self.assertEqual(rc, 0)
        _, body = self.fake.posts[0]
        # literal text preserved verbatim — never shell-interpreted
        self.assertEqual(body["description"], "café `rm -rf`; $(whoami)")
        self.assertEqual(body["notes"], 'n8"o')


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
    md = (
        pathlib.Path(__file__).resolve().parents[3] / "commands" / "organizze-create.md"
    )

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
