#!/usr/bin/env python3
"""Create transactions in Organizze via REST v2 — the first WRITE path.

Mirrors the read path's contract (auth/headers via _http.py) and the
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
from _http import http_get, http_post, load_auth  # noqa: E402
from _paths import CACHE, migrate_legacy  # noqa: E402

migrate_legacy()

VALID_PERIODICITIES = {"daily", "weekly", "biweekly", "monthly", "bimonthly",
                       "quarterly", "semiannually", "yearly"}


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


def suggest_category(description: str, history: list[dict],
                     categories: list[dict]) -> list[dict]:
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
        payload["installments_attributes"] = {
            "periodicity": tx.get("periodicity", "monthly"),
            "total": int(tx["installments"]),
        }
    elif tx.get("recurrence"):
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
        if (abs(int(r.get("amount_cents", 0))) == amt
                and _norm(r.get("description", "")) == desc
                and (r.get("date") or "")[:10] == day):
            out.append(r)
    return out


def verify_created(resp: object, expected: dict) -> dict:
    """Confirm the POST result. Returns {'ok':True,'id':id[,'count':n]} on a
    matching create, else {'ok':False,'reason':...}.

    Installments return a list of rows → report the actual created count.
    """
    if isinstance(resp, list):
        rows = [r for r in resp if isinstance(r, dict) and r.get("id") is not None]
        if not rows:
            return {"ok": False, "reason": "no-id-in-list"}
        return {"ok": True, "id": rows[0]["id"], "count": len(rows)}
    if not isinstance(resp, dict):
        return {"ok": False, "reason": "non-dict"}
    if resp.get("id") is None:
        return {"ok": False, "reason": "missing-id"}
    if "amount_cents" in expected and resp.get("amount_cents") is not None \
            and int(resp["amount_cents"]) != int(expected["amount_cents"]):
        return {"ok": False, "reason": "amount-mismatch"}
    if expected.get("description") and resp.get("description") \
            and _norm(resp["description"]) != _norm(expected["description"]):
        return {"ok": False, "reason": "description-mismatch"}
    return {"ok": True, "id": resp["id"]}


def parse_free_text(text: str) -> dict:
    """Best-effort NL → partial fields (amount/date/description hint).

    The command layer owns rich NL parsing; this is a fallback so the script
    still works when handed raw free text. Returns only the fields it finds.
    """
    out: dict = {}
    if not text:
        return out
    m = re.search(r"\d+(?:[.,]\d{1,2})?", text)
    if m:
        out["amount"] = m.group(0)
    low = _norm(text)
    if "ontem" in low:
        out["date_rel"] = "yesterday"
    elif "hoje" in low:
        out["date_rel"] = "today"
    out["description"] = text.strip()
    return out


# --- network / resolution layer --------------------------------------------

def _mask(token: str) -> str:
    return f"{token[:3]}…{token[-3:]}" if len(token) > 6 else "org_…"


def fetch_accounts(auth) -> list[dict]:
    rows = http_get("/accounts", None, *auth) or []
    return [a for a in rows if not a.get("archived") and a.get("type")]


def fetch_credit_cards(auth) -> list[dict]:
    rows = http_get("/credit_cards", None, *auth) or []
    return [c for c in rows if not c.get("archived")]


def fetch_categories(auth) -> list[dict]:
    cached = _cache_get("categories.json", 7)
    if cached is not None:
        return cached
    rows = http_get("/categories", None, *auth) or []
    _cache_set("categories.json", rows)
    return rows


def fetch_invoices(card_id: int, auth) -> list[dict]:
    return http_get(f"/credit_cards/{card_id}/invoices", None, *auth) or []


def fetch_recent_transactions(auth, days: int = 90) -> list[dict]:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    return http_get("/transactions",
                    {"start_date": start.isoformat(), "end_date": today.isoformat()},
                    *auth) or []


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


def run(args: argparse.Namespace) -> int:
    auth = load_auth()
    email, token, _ua = auth
    _emit("auth", f"as {email} ({_mask(token)})")

    date_iso = args.data or _today_iso()
    free = parse_free_text(" ".join(args.text)) if args.text else {}
    description = args.text and " ".join(args.text) or args.descricao or free.get("description", "")
    paid = resolve_paid(args, date_iso)

    # ---- TRANSFER mode -----------------------------------------------------
    if args.transferencia:
        accounts = fetch_accounts(auth)
        card_ids = {c["id"] for c in fetch_credit_cards(auth)}
        src = _resolve_or_exit(args.de or "", accounts, "conta origem")
        dest = _resolve_or_exit(args.para or "", accounts, "conta destino")
        amount = normalize_amount(args.valor, "income")  # transfer uses positive
        tx = {
            "debit_account_id": src["id"],
            "credit_account_id": dest["id"],
            "amount_cents": amount,
            "date": date_iso,
            "paid": paid,
            "src_is_card": src["id"] in card_ids,
            "dest_is_card": dest["id"] in card_ids,
            "notes": args.nota,
        }
        payload = build_transfer_payload(tx)
        _emit("resolve", f"transfer {src['name']} -> {dest['name']} R$ {amount/100:.2f}")
        return _finish(args, auth, "/transfers", payload,
                       {"amount_cents": amount}, kind="transfer",
                       recent=fetch_recent_transactions(auth) if not args.force else [])

    # ---- TRANSACTION modes (account / card / invoice) ----------------------
    if not description.strip():
        sys.exit("err|validation|description vazia")
    kind = "income" if args.receita else "expense"
    amount = normalize_amount(args.valor, kind)

    category_id = None
    tx: dict = {"description": description, "amount_cents": amount, "date": date_iso,
                "paid": paid, "notes": args.nota}

    if args.transferencia is False and (args.cartao or args.fatura):
        cards = fetch_credit_cards(auth)
        card = _resolve_or_exit(args.cartao or "", cards, "cartao") if args.cartao else None
        if args.fatura:
            if card is None and len(cards) == 1:
                card = cards[0]
            if card is None:
                sys.exit("err|resolve|cartao obrigatorio com --fatura")
            tx.update(target="invoice", credit_card_id=card["id"],
                      credit_card_invoice_id=int(args.fatura))
            _emit("resolve", f"cartao {card['name']} fatura {args.fatura} (escolhida)")
        else:
            invoices = fetch_invoices(card["id"], auth)
            inv = resolve_invoice_for_date(date_iso, invoices)
            if inv is None:
                sys.exit(f"err|invoice-unresolved|{card['name']} para {date_iso}")
            tx.update(target="card", credit_card_id=card["id"],
                      credit_card_invoice_id=inv["id"])
            _emit("resolve", f"cartao {card['name']} -> fatura {inv.get('date', inv['id'])}")
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
    recent = fetch_recent_transactions(auth) if not args.force else []
    return _finish(args, auth, "/transactions", payload,
                   {"amount_cents": amount, "description": description},
                   kind="transaction", recent=recent)


def _finish(args, auth, endpoint: str, payload: dict, expected: dict,
            kind: str, recent: list[dict]) -> int:
    # DUP-CHK
    if recent:
        dups = find_duplicates({"amount_cents": payload.get("amount_cents", expected.get("amount_cents")),
                                "description": payload.get("description", ""),
                                "date": payload.get("date", "")}, recent)
        if dups and not args.force:
            d = dups[0]
            _emit("duplicate", f"{len(dups)} similar(es): id {d.get('id')} {d.get('date')}")
            if args.apply:
                sys.exit("err|duplicate|use --force para confirmar a criacao mesmo assim")

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
        print(f"err|verify|criado mas read-back falhou: {chk.get('reason')}", file=sys.stderr)
        return 2
    extra = f" ({chk['count']} parcelas)" if chk.get("count") else ""
    _emit("verify", f"ok id {chk['id']}{extra}")
    tag = "transfer" if kind == "transfer" else "created"
    print(f"ok|{tag}|{chk['id']}")
    return 0


def _render_payload(payload: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in payload.items())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create an Organizze transaction (dry-run by default).")
    p.add_argument("text", nargs="*", help="free-text description")
    p.add_argument("--descricao", help="explicit description (overrides free text join)")
    p.add_argument("--apply", action="store_true", help="actually POST (default: dry-run)")
    p.add_argument("--force", action="store_true", help="skip duplicate confirmation")
    # target
    p.add_argument("--conta", help="account name (account mode)")
    p.add_argument("--cartao", help="credit card name (card mode)")
    p.add_argument("--fatura", help="explicit invoice id (invoice mode, needs --cartao)")
    # amount + sign
    p.add_argument("--valor", help="amount in reais (e.g. 50 / 50,00)")
    p.add_argument("--receita", action="store_true", help="income (positive)")
    p.add_argument("--despesa", action="store_true", help="expense (negative, default)")
    p.add_argument("--data", help="YYYY-MM-DD (default today)")
    p.add_argument("--categoria", help="category name")
    p.add_argument("--parcelas", type=int, help="number of installments")
    p.add_argument("--periodicidade", help="periodicity for installments/recurrence")
    p.add_argument("--recorrente", action="store_true", help="fixed/recurring transaction")
    # transfer
    p.add_argument("--transferencia", action="store_true", help="transfer between accounts")
    p.add_argument("--de", help="source account (transfer)")
    p.add_argument("--para", help="destination account (transfer)")
    p.add_argument("--paga", action="store_true", help="force paid=true")
    p.add_argument("--nao-paga", dest="nao_paga", action="store_true",
                   help="force paid=false (pending); default infers from date")
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
