"""Tests for cashflow.normalize_transfers — repairing corrupt transfer pairs.

A transfer is a linked pair (oposite_transaction_id) that MUST net to zero:
one negative leg (source), one positive leg (destination). Organizze sometimes
emits an occurrence of a recurring transfer where BOTH legs share the same sign,
throwing the destination account's forecast off by 2x the amount. The repair
takes the correct per-account direction from the healthy sibling occurrences of
the same recurrence_id.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from cashflow import normalize_transfers


def _leg(tid, acct, amt, opp, rid):
    return {
        "id": tid,
        "account_id": acct,
        "amount_cents": amt,
        "oposite_transaction_id": opp,
        "oposite_account_id": None,
        "recurrence_id": rid,
        "date": "2026-07-06",
        "description": "Transferência",
    }


def _pair(base, acct_src, acct_dst, amt, rid, date="2026-08-06", both_negative=False):
    """A healthy transfer pair src(-amt) -> dst(+amt), unless both_negative."""
    src = _leg(base, acct_src, -amt, base + 1, rid)
    dst = _leg(base + 1, acct_dst, (-amt if both_negative else amt), base, rid)
    src["date"] = dst["date"] = date
    return [src, dst]


def test_repairs_corrupt_leg_from_recurrence_consensus():
    # rec 99: healthy Aug/Sep (dst +5500), corrupt Jul (dst -5500).
    txs = []
    txs += _pair(
        100, 1, 2, 5500, rid=99, date="2026-07-06", both_negative=True
    )  # corrupt
    txs += _pair(200, 1, 2, 5500, rid=99, date="2026-08-06")  # healthy
    txs += _pair(300, 1, 2, 5500, rid=99, date="2026-09-06")  # healthy
    snap = {"transactions_future": txs, "transactions_past": []}

    fixed = normalize_transfers(snap)
    assert fixed == 1, f"expected 1 leg repaired, got {fixed}"

    jul_dst = next(t for t in txs if t["id"] == 101)
    jul_src = next(t for t in txs if t["id"] == 100)
    assert jul_dst["amount_cents"] == 5500, "destination leg must become +5500"
    assert jul_src["amount_cents"] == -5500, "source leg stays -5500"
    assert jul_src["amount_cents"] + jul_dst["amount_cents"] == 0, (
        "pair must net to zero"
    )


def test_healthy_pairs_untouched_idempotent():
    txs = _pair(400, 1, 2, 3000, rid=None, date="2026-07-06")  # already opposite signs
    snap = {"transactions_future": txs, "transactions_past": []}
    before = [t["amount_cents"] for t in txs]
    assert normalize_transfers(snap) == 0
    assert [t["amount_cents"] for t in txs] == before
    # running twice changes nothing
    assert normalize_transfers(snap) == 0
    assert [t["amount_cents"] for t in txs] == before


def test_undeterminable_oneoff_left_untouched():
    # One-off corrupt transfer, no recurrence siblings -> cannot determine, skip.
    txs = _pair(500, 1, 2, 1000, rid=None, date="2026-07-06", both_negative=True)
    snap = {"transactions_future": txs, "transactions_past": []}
    assert normalize_transfers(snap) == 0
    assert all(t["amount_cents"] == -1000 for t in txs), (
        "untouched when direction unknown"
    )


def test_derives_second_leg_when_only_one_has_consensus():
    # Only the source account (acct 1) has a healthy sibling; destination (acct 2)
    # has none. The destination leg is derived via the net-zero invariant.
    txs = []
    txs += _pair(
        600, 1, 2, 5500, rid=77, date="2026-07-06", both_negative=True
    )  # corrupt
    # sibling that only establishes acct-1 sign (a transfer 1 -> 3 on same rec)
    txs += _pair(700, 1, 3, 5500, rid=77, date="2026-08-06")  # healthy, acct1 = -
    snap = {"transactions_future": txs, "transactions_past": []}

    fixed = normalize_transfers(snap)
    jul_src = next(t for t in txs if t["id"] == 600)  # acct 1
    jul_dst = next(t for t in txs if t["id"] == 601)  # acct 2
    assert jul_src["amount_cents"] == -5500, "acct-1 source stays negative (consensus)"
    assert jul_dst["amount_cents"] == 5500, (
        "acct-2 destination derived positive (net-zero)"
    )
    assert fixed == 1


if __name__ == "__main__":
    import traceback

    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
