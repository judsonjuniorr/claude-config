"""Tests for sanitize.py."""
import json
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from sanitize import sanitize_snapshot, tokenize_account_id, strip_pii_from_text


def test_cpf_stripped():
    text = "Pagamento João 123.456.789-00"
    assert "[PII_REMOVED]" in strip_pii_from_text(text)
    assert "123.456.789-00" not in strip_pii_from_text(text)


def test_cnpj_stripped():
    text = "Empresa 12.345.678/0001-99"
    assert "[PII_REMOVED]" in strip_pii_from_text(text)


def test_account_id_tokenized():
    token = tokenize_account_id(12345)
    assert token.startswith("acct_")
    assert len(token) == len("acct_") + 8
    # deterministic
    assert token == tokenize_account_id(12345)


def test_account_id_different_for_different_ids():
    assert tokenize_account_id(111) != tokenize_account_id(222)


def test_sanitize_snapshot_removes_cpf():
    snapshot = {
        "transactions_past": [
            {"id": 1, "description": "Pagamento 123.456.789-00", "account_id": 42, "amount_cents": -1000}
        ],
        "transactions_future": [],
        "accounts": [{"id": 42, "name": "Minha Conta", "type": "checking"}],
        "credit_cards": [],
        "categories": [],
    }
    result = sanitize_snapshot(snapshot, id_map={})
    desc = result["transactions_past"][0]["description"]
    assert "123.456.789-00" not in desc
    assert "[PII_REMOVED]" in desc


def test_account_id_replaced_in_transactions():
    snapshot = {
        "transactions_past": [
            {"id": 1, "description": "Test", "account_id": 42, "amount_cents": -1000}
        ],
        "transactions_future": [],
        "accounts": [{"id": 42, "name": "Minha Conta", "type": "checking"}],
        "credit_cards": [],
        "categories": [],
    }
    result = sanitize_snapshot(snapshot, id_map={})
    assert result["transactions_past"][0]["account_id"] != 42
    assert result["transactions_past"][0]["account_id"].startswith("acct_")


def test_no_raw_account_id_in_prompt_body():
    """PII boundary: raw account IDs must not appear after sanitization."""
    raw_id = 99999
    snapshot = {
        "transactions_past": [
            {"id": 1, "description": "Test", "account_id": raw_id, "amount_cents": -500}
        ],
        "transactions_future": [],
        "accounts": [{"id": raw_id, "name": "Secret Account", "type": "checking"}],
        "credit_cards": [],
        "categories": [],
    }
    result = sanitize_snapshot(snapshot, id_map={})
    result_str = json.dumps(result)
    assert str(raw_id) not in result_str


def test_scrape_debug_fields_stripped():
    """Regression guard: apply_scrape.py writes _scrape_unreconciled with raw,
    untokenized account names and transaction descriptions that bypass every
    sanitize_snapshot() PII path (CPF/CNPJ stripping, medical masking, account
    tokenization) — nothing downstream reads these fields, so drop them rather
    than let raw text leak into the file meant to be safe for LLM consumption.
    """
    snapshot = {
        "transactions_past": [],
        "transactions_future": [],
        "accounts": [],
        "credit_cards": [],
        "categories": [],
        "_scrape_meta": {"applied_at": "2026-07-01T23:13:57", "slices": ["dashboard"], "warn": True},
        "_scrape_unreconciled": {
            "accounts": ["Conta Pessoal João 123.456.789-00"],
            "transactions": ["2026-07-09|Consulta Dra. Silva - Psiquiatria"],
            "invoices": [],
        },
    }
    result = sanitize_snapshot(snapshot, id_map={})
    assert "_scrape_meta" not in result
    assert "_scrape_unreconciled" not in result
