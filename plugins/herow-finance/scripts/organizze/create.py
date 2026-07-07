#!/usr/bin/env python3
"""Create transactions in Organizze via REST v2 — the first WRITE path.

Reads (account/card/category/invoice/recent-tx lookups) go through the official
`organizze` CLI (see _cli.py) — same rationale as pull.py. Writes stay on the
hand-rolled REST POST in _http.py: the CLI's write surface can't express
credit_card_invoice_id, installments_attributes, recurrence_attributes, or
transfers, all of which this script needs.

Mirrors the read path's contract (auth via _cli.py, writes via _http.py) and the
apply_budgets.py safety spine: DRY-RUN is the default, `--apply` is the only
state that POSTs, and every write is read-back verified.

This script is NON-INTERACTIVE. It resolves names → ids, builds the payload,
checks for duplicates and either prints the dry-run or performs the POST. When
it cannot resolve a name or map an invoice it emits `err|resolve|<hint>` /
`err|invoice-unresolved|<card>` and the command layer (organizze-create.md)
turns that into an AskUserQuestion. Pure helpers below are unit-tested with no
network.

Protocol:
  stderr: info|<state>|...   err|<code>|<detail>     (token never printed)
  stdout: ok|created|<id>    ok|transfer|<id>        (on a real --apply write)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _http import http_post  # noqa: E402
from _cli import (  # noqa: E402
    load_auth,
    accounts_list,
    credit_cards_list,
    categories_list,
    invoices_list,
    transactions_list,
)
from _paths import CACHE, migrate_legacy  # noqa: E402

migrate_legacy()

# Per api-doc §"Cria uma movimentação recorrente (parcelada)".
VALID_PERIODICITIES = {
    "monthly",
    "yearly",
    "weekly",
    "biweekly",
    "bimonthly",
    "trimonthly",
}


# --- text normalization (pure) ---------------------------------------------


def _norm(s: str) -> str:
    """Casefold + accent-fold + collapse whitespace. Used for all fuzzy match."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold().strip())


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", _norm(s)) if len(t) > 2}


# --- pure functions (unit-tested core) -------------------------------------


def normalize_amount(value: float | int | str, kind: str) -> int:
    """Reais → cents int. expense → negative, income → positive.

    Accepts '50', '50.00', '50,00', 50, 50.0. Rejects 0 / non-numeric with
    ValueError('validation|amount').
    """
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "")
        # "1.234,56" (pt) or "1234.56" (en) — drop thousands sep, normalize decimal.
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            reais = float(cleaned)
        except ValueError as e:
            raise ValueError("validation|amount") from e
    else:
        reais = float(value)
    cents = round(abs(reais) * 100)
    if cents == 0:
        raise ValueError("validation|amount")
    if kind not in ("expense", "income"):
        raise ValueError("validation|kind")
    return -cents if kind == "expense" else cents


def resolve_entity(hint: str, items: list[dict], key: str = "name") -> dict:
    """Fuzzy-match `hint` against items[key]. Never raises.

    Exact (normalized) match wins outright. Otherwise substring matches; one →
    match, many → ambiguous, none → none.
    """
    if not hint:
        return {"status": "none"}
    nh = _norm(hint)
    exact = [it for it in items if _norm(str(it.get(key, ""))) == nh]
    if len(exact) == 1:
        return {"status": "match", "item": exact[0]}
    if len(exact) > 1:
        return {"status": "ambiguous", "items": exact}
    subs = [it for it in items if nh in _norm(str(it.get(key, "")))]
    if len(subs) == 1:
        return {"status": "match", "item": subs[0]}
    if len(subs) > 1:
        return {"status": "ambiguous", "items": subs}
    return {"status": "none"}


def resolve_invoice_for_date(date_iso: str, invoices: list[dict]) -> dict | None:
    """Pick the invoice whose period contains `date_iso` (YYYY-MM-DD).

    Prefer starting_date/closing_date when both present; otherwise fall back to
    the invoice 'date' month. Returns the invoice dict or None.
    """
    day = (date_iso or "")[:10]
    if not day:
        return None
    for inv in invoices:
        start = (inv.get("starting_date") or "")[:10]
        close = (inv.get("closing_date") or "")[:10]
        if start and close and start <= day <= close:
            return inv
    # Fallback: match the invoice whose 'date' shares the same year-month.
    ym = day[:7]
    for inv in invoices:
        if (inv.get("date") or "")[:7] == ym:
            return inv
    return None


def suggest_category(
    description: str, history: list[dict], categories: list[dict]
) -> list[dict]:
    """Most-frequent category among history txs whose description shares a token
    with `description`. Returns category dicts ranked by frequency; [] when
    history is empty or nothing overlaps.
    """
    want = _tokens(description)
    if not want or not history:
        return []
    counts: Counter[int] = Counter()
    for tx in history:
        cid = tx.get("category_id")
        if cid is None:
            continue
        if _tokens(tx.get("description", "")) & want:
            counts[cid] += 1
    if not counts:
        return []
    by_id = {c.get("id"): c for c in categories}
    ranked = []
    for cid, _ in counts.most_common():
        if cid in by_id:
            ranked.append(by_id[cid])
    return ranked


def build_transaction_payload(tx: dict) -> dict:
    """Build a POST /transactions body from a resolved tx dict.

    target: 'account' → account_id only; 'card'/'invoice' → credit_card_id +
    credit_card_invoice_id (no account_id). installments XOR recurrence.
    """
    desc = (tx.get("description") or "").strip()
    if not desc:
        raise ValueError("validation|description")
    if tx.get("installments") and tx.get("recurrence"):
        raise ValueError("validation|installments-recurrence")

    payload: dict = {
        "description": desc,
        "amount_cents": tx["amount_cents"],
        "date": tx["date"],
    }
    target = tx.get("target")
    if target == "account":
        payload["account_id"] = tx["account_id"]
    elif target in ("card", "invoice"):
        payload["credit_card_id"] = tx["credit_card_id"]
        payload["credit_card_invoice_id"] = tx["credit_card_invoice_id"]
    else:
        raise ValueError("validation|target")

    if tx.get("category_id") is not None:
        payload["category_id"] = tx["category_id"]
    if tx.get("notes"):
        payload["notes"] = tx["notes"]
    if tx.get("paid") is not None:
        payload["paid"] = bool(tx["paid"])

    if tx.get("installments"):
        per = tx.get("periodicity", "monthly")
        if per not in VALID_PERIODICITIES:
            raise ValueError("validation|periodicity")
        payload["installments_attributes"] = {
            "periodicity": per,
            "total": int(tx["installments"]),
        }
    elif tx.get("recurrence"):
        if tx["recurrence"] not in VALID_PERIODICITIES:
            raise ValueError("validation|periodicity")
        payload["recurrence_attributes"] = {"periodicity": tx["recurrence"]}
    return payload


def build_transfer_payload(tx: dict) -> dict:
    """Build a POST /transfers body. amount must be POSITIVE; src/dest must be
    bank accounts (reject card ids locally before POST).
    """
    if tx.get("src_is_card") or tx.get("dest_is_card"):
        raise ValueError("validation|transfer-card")
    amount = int(tx["amount_cents"])
    if amount <= 0:
        raise ValueError("validation|amount")
    payload: dict = {
        "credit_account_id": tx["credit_account_id"],
        "debit_account_id": tx["debit_account_id"],
        "amount_cents": amount,
        "date": tx["date"],
        "paid": bool(tx.get("paid", True)),
    }
    if tx.get("notes"):
        payload["notes"] = tx["notes"]
    return payload


def find_duplicates(tx: dict, recent: list[dict]) -> list[dict]:
    """Recent txs matching abs(amount) AND normalized description AND date[:10]."""
    amt = abs(int(tx.get("amount_cents", 0)))
    desc = _norm(tx.get("description", ""))
    day = (tx.get("date") or "")[:10]
    out = []
    for r in recent:
        if (
            abs(int(r.get("amount_cents", 0))) == amt
            and _norm(r.get("description", "")) == desc
            and (r.get("date") or "")[:10] == day
        ):
            out.append(r)
    return out


def verify_created(resp: object, expected: dict) -> dict:
    """Confirm the POST result. Returns {'ok':True,'id':id[,'count':n]} on a
    matching create, else {'ok':False,'reason':...}.

    Installments: per api-doc the create returns a SINGLE dict carrying
    `total_installments` (and `amount_cents` is often 0), so we assert the
    created total matches the request and skip the amount check. Some responses
    instead return a list of rows — handle both.
    """
    want_installments = expected.get("installments")
    if isinstance(resp, list):
        rows = [r for r in resp if isinstance(r, dict) and r.get("id") is not None]
        if not rows:
            return {"ok": False, "reason": "no-id-in-list"}
        if want_installments and len(rows) != int(want_installments):
            return {"ok": False, "reason": "installment-count", "id": rows[0]["id"]}
        return {"ok": True, "id": rows[0]["id"], "count": len(rows)}
    if not isinstance(resp, dict):
        return {"ok": False, "reason": "non-dict"}
    if resp.get("id") is None:
        return {"ok": False, "reason": "missing-id"}
    if want_installments:
        total = resp.get("total_installments")
        if total is not None and int(total) != int(want_installments):
            return {"ok": False, "reason": "installment-count", "id": resp["id"]}
        return {
            "ok": True,
            "id": resp["id"],
            "count": int(total) if total is not None else None,
        }
    if (
        "amount_cents" in expected
        and resp.get("amount_cents") is not None
        and int(resp["amount_cents"]) != int(expected["amount_cents"])
    ):
        return {"ok": False, "reason": "amount-mismatch"}
    if (
        expected.get("description")
        and resp.get("description")
        and _norm(resp["description"]) != _norm(expected["description"])
    ):
        return {"ok": False, "reason": "description-mismatch"}
    return {"ok": True, "id": resp["id"]}


# --- network / resolution layer --------------------------------------------


def _mask(token: str) -> str:
    return f"{token[:3]}…" if len(token) > 3 else "org…"


def fetch_accounts(auth) -> list[dict]:
    rows = accounts_list(auth) or []
    return [a for a in rows if not a.get("archived") and a.get("type")]


def fetch_credit_cards(auth) -> list[dict]:
    rows = credit_cards_list(auth) or []
    return [c for c in rows if not c.get("archived")]


def fetch_categories(auth) -> list[dict]:
    cached = _cache_get("categories.json", 7)
    if cached is not None:
        return cached
    rows = categories_list(auth) or []
    _cache_set("categories.json", rows)
    return rows


def fetch_invoices(card_id: int, auth) -> list[dict]:
    return invoices_list(card_id, None, None, auth) or []


def fetch_recent_transactions(auth, days: int = 90) -> list[dict]:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    return (
        transactions_list(start.isoformat(), today.isoformat(), auth, all_pages=True)
        or []
    )


def _cache_get(name: str, max_age_days: int) -> object | None:
    p = CACHE / name
    if not p.exists():
        return None
    age = dt.datetime.now().timestamp() - p.stat().st_mtime
    if age > max_age_days * 86400:
        return None
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return None


def _cache_set(name: str, data: object) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / name).write_text(json.dumps(data, ensure_ascii=False))


# --- state machine ----------------------------------------------------------


def _emit(state: str, detail: str = "") -> None:
    print(f"info|{state}|{detail}", file=sys.stderr)


def _resolve_or_exit(hint: str, items: list[dict], label: str) -> dict:
    res = resolve_entity(hint, items)
    if res["status"] == "match":
        return res["item"]
    if res["status"] == "ambiguous":
        names = "; ".join(str(i.get("name")) for i in res["items"])
        sys.exit(f"err|resolve|{label} '{hint}' ambiguo: {names}")
    sys.exit(f"err|resolve|{label} '{hint}' nao encontrado")


def _today_iso() -> str:
    return dt.date.today().isoformat()


def resolve_paid(args: argparse.Namespace, date_iso: str) -> bool:
    """Explicit flag wins; otherwise default by date: a past/today-dated entry
    is assumed already paid, a future-dated one is pending. The command layer
    asks 'já paga?' for past dates and passes --paga/--nao-paga accordingly.
    """
    if getattr(args, "nao_paga", False):
        return False
    if args.paga:
        return True
    return date_iso[:10] <= _today_iso()


def _load_input_file(path: str) -> dict:
    """Read free-text fields (description, notes) from a JSON file.

    The command layer writes user free text here via the Write tool so it never
    enters a shell-parsed command line (injection-safe). Structured flags stay
    on argv where argparse type-coerces them.
    """
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"err|input-file|{e}")
    if not isinstance(data, dict):
        sys.exit("err|input-file|esperado objeto JSON")
    return data


def run(args: argparse.Namespace) -> int:
    auth = load_auth()
    email, token, _ua = auth
    _emit("auth", f"as {email} ({_mask(token)})")

    extra = _load_input_file(args.input_file) if args.input_file else {}
    date_iso = args.data or _today_iso()
    if args.text:
        argv_desc = " ".join(args.text)
    else:
        argv_desc = args.descricao or ""
    description = extra.get("description") or argv_desc
    notes = extra.get("notes") if extra.get("notes") is not None else args.nota
    paid = resolve_paid(args, date_iso)

    # ---- TRANSFER mode -----------------------------------------------------
    if args.transferencia:
        accounts = fetch_accounts(auth)
        card_ids = {c["id"] for c in fetch_credit_cards(auth)}
        src = _resolve_or_exit(args.de or "", accounts, "conta origem")
        dest = _resolve_or_exit(args.para or "", accounts, "conta destino")
        amount = normalize_amount(args.valor, "income")  # transfer uses positive
        # Organizze: credit_account_id = ORIGEM (saída), debit_account_id =
        # DESTINO (entrada). Verified vs api-doc §Transfers (the -amount record
        # lands on account_id == credit_account_id).
        tx = {
            "credit_account_id": src["id"],
            "debit_account_id": dest["id"],
            "amount_cents": amount,
            "date": date_iso,
            "paid": paid,
            "src_is_card": src["id"] in card_ids,
            "dest_is_card": dest["id"] in card_ids,
            "notes": notes,
        }
        payload = build_transfer_payload(tx)
        _emit(
            "resolve",
            f"transfer {src['name']} (origem) -> {dest['name']} (destino) R$ {amount / 100:.2f}",
        )
        # Transfer read-back verifies id presence only: the POST response is the
        # signed outflow record, so an amount match would compare +req vs -resp.
        return _finish(
            args,
            auth,
            "/transfers",
            payload,
            {},
            kind="transfer",
            recent=fetch_recent_transactions(auth) if not args.force else [],
        )

    # ---- TRANSACTION modes (account / card / invoice) ----------------------
    if not description.strip():
        sys.exit("err|validation|description vazia")
    kind = "income" if args.receita else "expense"
    amount = normalize_amount(args.valor, kind)

    category_id = None
    tx: dict = {
        "description": description,
        "amount_cents": amount,
        "date": date_iso,
        "paid": paid,
        "notes": notes,
    }

    if args.cartao or args.fatura:
        cards = fetch_credit_cards(auth)
        card = (
            _resolve_or_exit(args.cartao or "", cards, "cartao")
            if args.cartao
            else None
        )
        if args.fatura:
            if card is None and len(cards) == 1:
                card = cards[0]
            if card is None:
                sys.exit("err|resolve|cartao obrigatorio com --fatura")
            tx.update(
                target="invoice",
                credit_card_id=card["id"],
                credit_card_invoice_id=int(args.fatura),
            )
            _emit("resolve", f"cartao {card['name']} fatura {args.fatura} (escolhida)")
        else:
            invoices = fetch_invoices(card["id"], auth)
            inv = resolve_invoice_for_date(date_iso, invoices)
            if inv is None:
                sys.exit(f"err|invoice-unresolved|{card['name']} para {date_iso}")
            start = (inv.get("starting_date") or "")[:10]
            close = (inv.get("closing_date") or "")[:10]
            approx = not (start and close and start <= date_iso[:10] <= close)
            tx.update(
                target="card",
                credit_card_id=card["id"],
                credit_card_invoice_id=inv["id"],
            )
            tag = " [APROXIMADA: sem janela de fechamento, confirme]" if approx else ""
            _emit(
                "resolve",
                f"cartao {card['name']} -> fatura {inv.get('date', inv['id'])}{tag}",
            )
    elif args.conta:
        accounts = fetch_accounts(auth)
        acct = _resolve_or_exit(args.conta, accounts, "conta")
        tx.update(target="account", account_id=acct["id"])
        _emit("resolve", f"conta {acct['name']}")
    else:
        sys.exit("err|validation|alvo: use --conta, --cartao ou --transferencia")

    # category: explicit flag wins; else cheap historical suggestion (warn, never block)
    categories = fetch_categories(auth)
    if args.categoria:
        cat = _resolve_or_exit(args.categoria, categories, "categoria")
        category_id = cat["id"]
        _emit("category", f"{cat['name']} (escolhida)")
    else:
        history = fetch_recent_transactions(auth)
        ranked = suggest_category(description, history, categories)
        if ranked:
            category_id = ranked[0]["id"]
            _emit("category", f"sugerida {ranked[0]['name']}")
        else:
            _emit("category", "nenhuma sugestao (criando sem categoria)")
    if category_id is not None:
        tx["category_id"] = category_id

    if args.parcelas:
        tx["installments"] = int(args.parcelas)
        tx["periodicity"] = args.periodicidade or "monthly"
    if args.recorrente:
        tx["recurrence"] = args.periodicidade or "monthly"

    payload = build_transaction_payload(tx)
    expected = {"amount_cents": amount, "description": description}
    if args.parcelas:
        expected["installments"] = int(args.parcelas)
        _emit(
            "installments",
            f"{args.parcelas}x — semantica do valor NAO verificada "
            "contra conta real; confira o total no app apos --apply",
        )
    recent = fetch_recent_transactions(auth) if not args.force else []
    return _finish(
        args,
        auth,
        "/transactions",
        payload,
        expected,
        kind="transaction",
        recent=recent,
    )


def _finish(
    args,
    auth,
    endpoint: str,
    payload: dict,
    expected: dict,
    kind: str,
    recent: list[dict],
) -> int:
    # DUP-CHK — always emit a signal so "no dups" is distinguishable from "not checked".
    if args.force:
        _emit("dup-check", "pulado (--force)")
    elif kind == "transfer":
        # Transfer payloads carry no description; find_duplicates can't match them
        # reliably, so we skip rather than give a false all-clear.
        _emit("dup-check", "pulado (transferencia)")
    elif not recent:
        _emit("dup-check", "pulado (sem historico recente)")
    else:
        dups = find_duplicates(
            {
                "amount_cents": payload.get(
                    "amount_cents", expected.get("amount_cents")
                ),
                "description": payload.get("description", ""),
                "date": payload.get("date", ""),
            },
            recent,
        )
        if dups:
            d = dups[0]
            _emit(
                "duplicate",
                f"{len(dups)} similar(es): id {d.get('id')} {d.get('date')}",
            )
            if args.apply:
                sys.exit(
                    "err|duplicate|use --force para confirmar a criacao mesmo assim"
                )
        else:
            _emit("dup-check", "0 similar")

    # DRY-RUN (default)
    if not args.apply:
        _emit("dry-run", f"POST {endpoint}")
        _emit("payload", _render_payload(payload))
        return 0

    # APPLY
    _emit("apply", f"POST {endpoint}")
    resp = http_post(endpoint, payload, *auth)

    # VERIFY
    chk = verify_created(resp, expected)
    if not chk["ok"]:
        _emit("verify", f"FALHOU: {chk.get('reason')}")
        print(
            f"err|verify|criado mas read-back falhou: {chk.get('reason')}",
            file=sys.stderr,
        )
        return 2
    extra = f" ({chk['count']} parcelas)" if chk.get("count") else ""
    _emit("verify", f"ok id {chk['id']}{extra}")
    tag = "transfer" if kind == "transfer" else "created"
    print(f"ok|{tag}|{chk['id']}")
    return 0


def _render_payload(payload: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in payload.items())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Create an Organizze transaction (dry-run by default)."
    )
    p.add_argument("text", nargs="*", help="free-text description")
    p.add_argument(
        "--descricao", help="explicit description (overrides free text join)"
    )
    p.add_argument(
        "--input-file",
        dest="input_file",
        help="JSON file with free-text fields (description, notes) — "
        "injection-safe path for user text (no shell parsing)",
    )
    p.add_argument(
        "--apply", action="store_true", help="actually POST (default: dry-run)"
    )
    p.add_argument("--force", action="store_true", help="skip duplicate confirmation")
    # target
    p.add_argument("--conta", help="account name (account mode)")
    p.add_argument("--cartao", help="credit card name (card mode)")
    p.add_argument(
        "--fatura", help="explicit invoice id (invoice mode, needs --cartao)"
    )
    # amount + sign
    p.add_argument("--valor", help="amount in reais (e.g. 50 / 50,00)")
    p.add_argument("--receita", action="store_true", help="income (positive)")
    p.add_argument("--despesa", action="store_true", help="expense (negative, default)")
    p.add_argument("--data", help="YYYY-MM-DD (default today)")
    p.add_argument("--categoria", help="category name")
    p.add_argument("--parcelas", type=int, help="number of installments")
    p.add_argument("--periodicidade", help="periodicity for installments/recurrence")
    p.add_argument(
        "--recorrente", action="store_true", help="fixed/recurring transaction"
    )
    # transfer
    p.add_argument(
        "--transferencia", action="store_true", help="transfer between accounts"
    )
    p.add_argument("--de", help="source account (transfer)")
    p.add_argument("--para", help="destination account (transfer)")
    p.add_argument("--paga", action="store_true", help="force paid=true")
    p.add_argument(
        "--nao-paga",
        dest="nao_paga",
        action="store_true",
        help="force paid=false (pending); default infers from date",
    )
    p.add_argument("--nota", help="optional note")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.parcelas and args.recorrente:
        sys.exit("err|validation|installments-recurrence")
    if args.valor is None and not args.transferencia:
        sys.exit("err|validation|--valor obrigatorio")
    if args.transferencia and args.valor is None:
        sys.exit("err|validation|--valor obrigatorio")
    try:
        return run(args)
    except ValueError as e:
        sys.exit(f"err|{e}")


if __name__ == "__main__":
    raise SystemExit(main())
