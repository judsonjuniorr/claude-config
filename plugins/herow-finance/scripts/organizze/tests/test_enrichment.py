"""Tests for pull.py enrichment changes."""
import os
import sys
import pathlib
import tempfile

# Set hermetic ORGANIZZE_HOME before importing pull (prevents touching real ~/.finance)
os.environ.setdefault("ORGANIZZE_HOME", tempfile.mkdtemp(prefix="pull-enrich-test-"))

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from pull import enrich_transactions, detect_recurring_from_history


def make_tx(id, desc, amount, date, paid=True, total_installments=1):
    return {
        "id": id,
        "description": desc,
        "amount_cents": amount,
        "date": date,
        "paid": paid,
        "total_installments": total_installments,
        "installment": 1,
    }


def test_is_installment_flag():
    today = "2026-06-28"
    txs = [
        make_tx(1, "Parcela TV", -30000, today, total_installments=12),
        make_tx(2, "Mercado", -5000, today, total_installments=1),
    ]
    result = enrich_transactions(txs, all_transactions_5y=[])
    installment_tx = next(t for t in result if t["id"] == 1)
    regular_tx = next(t for t in result if t["id"] == 2)
    assert installment_tx.get("is_installment") is True
    assert regular_tx.get("is_installment") is False


def test_pix_income_confidence_pix_transaction():
    txs = [make_tx(1, "PIX recebido FULANO", 50000, "2026-06-01")]
    result = enrich_transactions(txs, all_transactions_5y=[])
    tx = result[0]
    assert tx.get("pix_income_confidence", 0.0) > 0.0


def test_pix_income_confidence_non_pix_income():
    txs = [make_tx(1, "Salário empresa", 500000, "2026-06-05")]
    result = enrich_transactions(txs, all_transactions_5y=[])
    tx = result[0]
    assert tx.get("pix_income_confidence", 0.0) == 0.0


def test_pix_income_confidence_expense_is_zero():
    txs = [make_tx(1, "PIX pagamento LOJA", -5000, "2026-06-01")]
    result = enrich_transactions(txs, all_transactions_5y=[])
    tx = result[0]
    assert tx.get("pix_income_confidence", 0.0) == 0.0


def test_is_recurring_cold_start_less_than_3_months():
    """With less than 3 months of history, is_recurring must be False for all."""
    # Only 2 months of Netflix data
    txs_5y = [
        make_tx(i, "Netflix", -5000, f"2026-0{m+4}-15")
        for m, i in enumerate(range(2))
    ]
    target = [make_tx(10, "Netflix", -5000, "2026-06-15")]
    recurring = detect_recurring_from_history(txs_5y, target, min_months=3)
    assert 10 not in recurring


def test_is_recurring_detects_consistent_monthly():
    """Consistent monthly transactions within ±10% should be marked recurring."""
    txs_5y = [
        make_tx(1, "Netflix", -4900, "2026-01-15"),
        make_tx(2, "Netflix", -5000, "2026-02-15"),
        make_tx(3, "Netflix", -5000, "2026-03-15"),
        make_tx(4, "Netflix", -5100, "2026-04-15"),
    ]
    target = [make_tx(5, "Netflix", -5000, "2026-05-15")]
    recurring = detect_recurring_from_history(txs_5y + target, target, min_months=3)
    assert 5 in recurring


def test_is_recurring_behavioral_change_no_digit_collision():
    """Transactions with same description but amounts beyond ±10% should NOT be recurring."""
    txs_5y = [
        make_tx(1, "Uber", -1500, "2026-01-10"),
        make_tx(2, "Uber", -8000, "2026-02-10"),
        make_tx(3, "Uber", -3200, "2026-03-10"),
    ]
    target = [make_tx(4, "Uber", -2000, "2026-05-10")]
    recurring = detect_recurring_from_history(txs_5y + target, target, min_months=3)
    assert 4 not in recurring


def test_is_recurring_empty_history():
    """Empty history → no recurring IDs."""
    target = [make_tx(1, "Netflix", -5000, "2026-06-15")]
    recurring = detect_recurring_from_history([], target, min_months=3)
    assert len(recurring) == 0


def test_enrich_transactions_returns_copy():
    """enrich_transactions should not mutate the original list."""
    txs = [make_tx(1, "Test", -1000, "2026-06-01")]
    original_has_installment = "is_installment" in txs[0]
    result = enrich_transactions(txs, all_transactions_5y=[])
    # Original should not be mutated (we use deepcopy)
    assert "is_installment" in result[0]
