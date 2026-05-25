#!/usr/bin/env python3
"""Render the financial-analyst prompt from a snapshot.

Usage:
  analyze.py --snapshot PATH [--framework PATH] [--out PATH]

Output: prints a single prompt to stdout (and optionally writes to --out)
that injects the snapshot summary + the system prompt extracted from the
framework markdown. The caller (slash command) delegates this prompt to
the financial-analyst subagent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _paths import migrate_legacy  # noqa: E402

migrate_legacy()

DEFAULT_FRAMEWORK = pathlib.Path(__file__).resolve().parents[3] / "analista-financeiro-claude-code.md"


def cents_to_brl(c: int | float | None) -> str:
    if c is None:
        return "R$ 0,00"
    v = int(c) / 100.0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def extract_system_prompt(framework_md: str) -> str:
    """Extract section 4.1 (system prompt) verbatim from the framework doc."""
    lines = framework_md.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("### 4.1"):
            inside = True
            continue
        if inside and (line.startswith("### 4.2") or line.startswith("## ")):
            break
        if inside:
            out.append(line)
    # strip leading blank lines + leading "> " quote markers
    text = "\n".join(out).strip()
    text = "\n".join(
        ln[2:] if ln.startswith("> ") else (ln[1:] if ln.startswith(">") else ln)
        for ln in text.splitlines()
    ).strip()
    return text or "Você é um analista financeiro pessoal sênior."


def top_categories(snapshot: dict, month: dt.date | None = None) -> list[tuple[str, int]]:
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    totals: dict[str, int] = defaultdict(int)
    target_month = (month or dt.date.today()).strftime("%Y-%m")
    for t in snapshot.get("transactions_past") or []:
        if (t.get("date") or "")[:7] != target_month:
            continue
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue  # apenas despesas
        name = cats.get(t.get("category_id")) or "Sem categoria"
        totals[name] += -amt
    return sorted(totals.items(), key=lambda x: -x[1])[:10]


def category_delta(snapshot: dict) -> list[tuple[str, int, int, float]]:
    """(categoria, mes_atual_cents, mes_anterior_cents, variacao_pct)"""
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1))
    cur_key = today.strftime("%Y-%m")
    prev_key = prev.strftime("%Y-%m")
    cur: dict[str, int] = defaultdict(int)
    prv: dict[str, int] = defaultdict(int)
    for t in snapshot.get("transactions_past") or []:
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue
        name = cats.get(t.get("category_id")) or "Sem categoria"
        key = (t.get("date") or "")[:7]
        if key == cur_key:
            cur[name] += -amt
        elif key == prev_key:
            prv[name] += -amt
    rows = []
    for name in set(list(cur.keys()) + list(prv.keys())):
        c = cur.get(name, 0)
        p = prv.get(name, 0)
        delta = ((c - p) / p * 100.0) if p else (100.0 if c else 0.0)
        rows.append((name, c, p, delta))
    rows.sort(key=lambda x: -x[1])
    return rows[:10]


def summarize(snapshot: dict) -> str:
    m = snapshot.get("meta", {})
    t = m.get("totais", {})
    accounts = snapshot.get("accounts") or []
    invoices = snapshot.get("invoices") or []
    today = dt.date.today()

    out: list[str] = []
    out.append(f"# Snapshot Organizze — {m.get('pulled_at', '')}")
    out.append(f"Período: {m.get('periodo', {}).get('history_start')} → {m.get('periodo', {}).get('future_end')}")
    out.append("")
    out.append("## Saldo consolidado e projeção")
    out.append(f"- Saldo atual: **{cents_to_brl(t.get('saldo_cents'))}**")
    out.append(f"- Projeção +7d: {cents_to_brl(t.get('saldo_proj_7d_cents'))}")
    out.append(f"- Projeção +30d: {cents_to_brl(t.get('saldo_proj_30d_cents'))}")
    out.append(f"- Projeção +90d: {cents_to_brl(t.get('saldo_proj_90d_cents'))}")
    out.append("")
    def is_principal(a):
        return (not a.get("archived")
                and a.get("type") in ("checking", "savings", "other"))

    out.append("## Saldo por conta principal (entra no consolidado)")
    for a in accounts:
        if not is_principal(a):
            continue
        bal = a.get("_balance_cents") or 0
        out.append(f"- {a.get('name')} ({a.get('type')}): {cents_to_brl(bal)}")

    out.append("")
    out.append("## Outras contas (não somam no consolidado: caixinhas, contas auxiliares)")
    for a in accounts:
        if a.get("archived") or is_principal(a):
            continue
        bal = a.get("_balance_cents") or 0
        kind = a.get("institution_id") or a.get("type") or "?"
        out.append(f"- {a.get('name')} ({kind}): {cents_to_brl(bal)}")
    out.append("")

    out.append("## Faturas a vencer (próximos 7 dias)")
    n = 0
    for inv in invoices:
        d = (inv.get("date") or "")[:10]
        try:
            due = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if today <= due <= today + dt.timedelta(days=7):
            out.append(f"- {inv.get('_credit_card_name')} · vence {d} · {cents_to_brl(inv.get('total_cents'))}")
            n += 1
    if n == 0:
        out.append("- (nenhuma)")
    out.append("")

    out.append("## Top 10 categorias — mês corrente")
    tops = top_categories(snapshot)
    if not tops:
        out.append("- (sem despesas no mês corrente)")
    else:
        for name, amt in tops:
            out.append(f"- {name}: {cents_to_brl(amt)}")
    out.append("")

    out.append("## Variação por categoria — mês atual vs. anterior")
    for name, c, p, delta in category_delta(snapshot):
        sign = "+" if delta >= 0 else ""
        out.append(f"- {name}: {cents_to_brl(c)} (anterior {cents_to_brl(p)}, {sign}{delta:.1f}%)")
    out.append("")

    out.append("## Transações recorrentes detectadas")
    rec = [t for t in (snapshot.get("transactions_past") or []) if t.get("is_recurring")]
    by_payee: dict[str, tuple[int, int]] = {}  # payee -> (count, soma)
    for t in rec:
        p = t.get("description") or "?"
        c, s = by_payee.get(p, (0, 0))
        by_payee[p] = (c + 1, s + int(t.get("amount_cents") or 0))
    for payee, (c, s) in sorted(by_payee.items(), key=lambda x: -x[1][0])[:15]:
        out.append(f"- {payee}: {c}x · total {cents_to_brl(s)}")
    if not by_payee:
        out.append("- (nenhuma identificada)")
    out.append("")

    # === Transações passadas NÃO PAGAS (atrasadas) ===
    out.append("## ⚠️ Transações atrasadas (passadas, NÃO pagas)")
    overdue = [t for t in (snapshot.get("transactions_past") or [])
               if not t.get("paid") and t.get("credit_card_id") is None]
    overdue.sort(key=lambda x: (x.get("date") or ""))
    if not overdue:
        out.append("- (nenhuma)")
    else:
        for t in overdue[:40]:
            d = (t.get("date") or "")[:10]
            amt = int(t.get("amount_cents") or 0)
            tag = "RECEITA atrasada" if amt > 0 else "DESPESA atrasada"
            out.append(f"- {d} · {tag} · {t.get('description') or '?'} · {cents_to_brl(amt)}")
        tot = snapshot.get("meta", {}).get("totais", {})
        out.append(
            f"\nResumo: {tot.get('n_atrasadas_despesa',0)} despesas (total {cents_to_brl(-tot.get('soma_atrasadas_despesa_cents',0))}), "
            f"{tot.get('n_atrasadas_receita',0)} receitas (total {cents_to_brl(tot.get('soma_atrasadas_receita_cents',0))}) — devem ser pagas/recebidas o quanto antes."
        )
    out.append("")

    # === Parcelamentos em curso ===
    out.append("## Parcelamentos em curso")
    insts = snapshot.get("installments") or []
    if not insts:
        out.append("- (nenhum)")
    else:
        out.append("| Descrição | Progresso | Parcela média | Faltam | Restante | Fim previsto | Status |")
        out.append("|---|:---:|---:|:---:|---:|:---:|:---|")
        for r in insts[:25]:
            status_parts = []
            if r.get("almost_done"):
                status_parts.append("**acabando**")
            if r.get("long_way"):
                status_parts.append("**longe do fim**")
            status = ", ".join(status_parts) or "—"
            out.append(
                f"| {r['description'][:50]} "
                f"| {r['paid']}/{r['total_installments']} ({r['progress_pct']}%) "
                f"| {cents_to_brl(r['avg_amount_cents'])} "
                f"| {r['remaining']} "
                f"| {cents_to_brl(r['remaining_amount_cents'])} "
                f"| {r.get('expected_end_date') or '?'} "
                f"| {status} |"
            )
    out.append("")

    out.append("## Lançamentos futuros confirmados (próximos 30 dias)")
    n = 0
    for t in (snapshot.get("transactions_future") or [])[:50]:
        d = (t.get("date") or "")[:10]
        try:
            td = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if today < td <= today + dt.timedelta(days=30):
            out.append(f"- {d}: {t.get('description') or '?'} · {cents_to_brl(t.get('amount_cents'))}")
            n += 1
    if n == 0:
        out.append("- (nenhum)")
    out.append("")

    # === Fluxo por conta — projeção diária + dias críticos ===
    cf_block = render_cashflow_block(snapshot)
    if cf_block:
        out.append(cf_block)
        out.append("")

    out.append("## Orçamento do mês corrente (metas vs. realizado)")
    cur_key_y = today.year
    cur_key_m = today.month
    cats = {c.get("id"): c.get("name") for c in snapshot.get("categories") or []}
    rows = []
    for b in (snapshot.get("budgets") or []):
        if b.get("_year") != cur_key_y or b.get("_month") != cur_key_m:
            continue
        name = cats.get(b.get("category_id")) or b.get("name") or "?"
        budget = int(b.get("amount_in_cents") or b.get("amount_cents") or 0)
        spent = int(b.get("total_in_cents") or b.get("total_cents") or 0)
        if budget == 0 and spent == 0:
            continue
        pct = (spent / budget * 100.0) if budget else 0.0
        rows.append((name, spent, budget, pct))
    for name, spent, budget, pct in sorted(rows, key=lambda x: -x[3])[:15]:
        out.append(f"- {name}: {cents_to_brl(spent)} / {cents_to_brl(budget)} ({pct:.0f}%)")
    if not rows:
        out.append("- (sem metas definidas)")

    return "\n".join(out)


_SHARED_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def load_memory_block() -> str:
    """Lê ~/finance/memory.md e devolve um bloco renderizado para injeção."""
    mem_path = pathlib.Path.home() / "finance" / "memory.md"
    if not mem_path.exists():
        return ""
    import subprocess
    script = _SHARED_SCRIPTS / "memory.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "render"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def load_plans_block() -> str:
    """Lê ~/finance/plans.md e devolve um bloco renderizado para injeção."""
    plans_path = pathlib.Path.home() / "finance" / "plans.md"
    if not plans_path.exists():
        return ""
    import subprocess
    script = _SHARED_SCRIPTS / "plans.py"
    try:
        r = subprocess.run(
            ["python3", str(script), "render"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def render_cashflow_block(snapshot: dict) -> str:
    """Roda cashflow.per_account_projection e devolve markdown pronto."""
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from cashflow import per_account_projection, render_markdown
        from config import threshold_cents
        proj = per_account_projection(snapshot, threshold_cents=threshold_cents(), horizon_days=90)
        return render_markdown(proj).strip()
    except Exception as e:
        return f"## Fluxo por conta\n_(erro ao computar projeção: {e})_"


def render_prompt(snapshot: dict, framework_md: str) -> str:
    system = extract_system_prompt(framework_md)
    summary = summarize(snapshot)
    memory_block = load_memory_block()
    plans_block = load_plans_block()
    memory_section = f"\n---\n\n{memory_block}\n" if memory_block else ""
    plans_section = f"\n---\n\n{plans_block}\n" if plans_block else ""

    # Lista de nomes de contas existentes (para guardrail de transferências)
    existing_accounts = [a.get("name") for a in (snapshot.get("accounts") or [])
                         if not a.get("archived") and a.get("type")]
    accounts_hint = ", ".join(f"`{n}`" for n in existing_accounts if n) or "(nenhuma)"

    return f"""{system}
{memory_section}{plans_section}
---

# Dados consolidados (Organizze)

{summary}

---

# Diretrizes obrigatórias

1. **Metas por categoria**: o Organizze já define orçamento por categoria (seção "Orçamento do mês corrente"). Sua análise DEVE priorizar atingir essas metas — destaque categorias acima de 80% do orçamento como risco e categorias bem abaixo como oportunidade de realocação.

2. **Objetivos do usuário** (seção acima, se houver): avalie ad-hoc se há espaço no mês para cada objetivo a partir do **saldo atual + tx_future**, sem pressupor aporte mensal fixo. Para cada objetivo `active` diga claramente: "viável neste mês: SIM/NÃO/PARCIAL — R$ X possível", com justificativa numérica.

3. **Conflito objetivo vs. débito iminente**: se algum dia crítico aparece em qualquer conta principal (seção "Fluxo por conta"), **pause objetivos com priority=negociavel neste ciclo** e nomeie-os explicitamente em "Objetivos pausados". Objetivos com priority=inegociavel devem ser mantidos cortando gastos em outras categorias.

4. **Transferências inter-contas (GUARDRAIL ESTRITO)**: contas que EXISTEM neste snapshot: {accounts_hint}. Toda sugestão de transferência deve nomear **duas dessas contas** e cobrir débito específico com data. Se o objetivo do usuário cita uma conta-alvo que NÃO está na lista acima, NÃO invente: diga "reserve R$ X para Y" sem nomear conta.

5. **Saldo dia-a-dia da origem (REGRA CRÍTICA)**: ao sugerir transferência da conta A para a conta B na data D, **a conta A precisa ter saldo ≥ valor sugerido em D**. Use a seção "Fluxo por conta" para validar — se o dia D aparece com `❌ nenhuma conta principal com folga suficiente` ou se a lista `contas com folga nesse dia` não inclui A com valor suficiente, **NÃO sugira essa transferência**. Em vez disso:
   (a) adie a transferência para a primeira data em que A tem folga (ex.: após entrada salário/receita confirmada);
   (b) proponha renegociar/postergar o débito da conta destino para depois da próxima entrada;
   (c) sugira reordenar pagamentos do mês para encaixar no fluxo.
   Sempre cite o saldo de origem na data ("Santander em DD/MM: R$ X") como evidência.

6. **Renegociação de vencimentos (use quando o fluxo não fecha)**: se um débito recorrente cai sistematicamente em data sem caixa (ex.: assinatura dia 5 quando salário cai dia 6), recomende **alterar a data de vencimento** ou **mudar a forma de pagamento** (débito em conta → cartão, antecipa boleto, etc.). Inclua no formato:
   `[RENEGOCIAR · <credor>] Mover vencimento de <data atual> para <data sugerida> — motivo: caixa em <data atual> é R$ X, insuficiente para débito de R$ Y`.

7. **Tom**: sem floreio, sem hedge. Números primeiro, recomendação depois.

---

# Tarefa — produza EXATAMENTE este formato

**TL;DR** (3 linhas): situação atual + risco mais próximo + maior oportunidade.

**Números-chave** (tabela markdown): saldo atual, projeção 7/30/90d, % comprometido com recorrentes,
parcelamentos em curso (total restante), atrasadas (despesa/receita), maior categoria do mês, fatura mais próxima, nº de dias críticos por conta.

**Atrasadas — ação imediata** (≤3 bullets): para cada transação atrasada relevante, indique
"pagar/cobrar até <data>".

**Metas de categoria — status** (≤5 bullets): categorias em risco (>80% gasto) e categorias com folga relevante. Use os números da seção "Orçamento do mês corrente".

**Objetivos do usuário — viabilidade neste mês** (1 bullet por objetivo ativo): nome curto · viável SIM/NÃO/PARCIAL · valor possível neste mês · justificativa em 1 linha. Se não há objetivos ativos, escreva "(sem objetivos ativos)".

**Plano de transferências e poupança** (≤5 bullets): para cada dia crítico relevante OU objetivo viável, formato:
```
[CRÍTICO · em <data>] Transferir R$ X de "<conta origem>" para "<conta destino>"
  Saldo origem em <data>: R$ Y  ← obrigatório, deve ser ≥ X
  Motivo: <débito específico em <data> deixa destino em <valor>>
```
ou
```
[RENEGOCIAR · <credor>] Mover vencimento/forma de pagamento de <data atual> para <data sugerida>
  Caixa em <data atual>: R$ Y (insuficiente p/ débito R$ Z)
  Alvo: encaixar débito em data com folga ≥ R$ Z
```
ou
```
[POUPANÇA · neste mês] Reservar R$ X para "<conta destino se existe>" OU "<objetivo Y>" se conta não cadastrada
  Origem: <conta com folga ou sobra mensal>
```
**Regras**: (a) apenas use contas da lista de existentes; (b) nunca sugira transferência da conta A em data D se a seção "Fluxo por conta" indica que A não tem folga em D; (c) quando nenhuma conta tem folga no dia crítico, prefira `[RENEGOCIAR]` em vez de `[CRÍTICO]`. Se não há ação clara, escreva "(sem ações de transferência necessárias)".

**Objetivos pausados neste ciclo** (≤3 bullets, omita se vazio): nome do objetivo + razão (dia crítico em <data> ou meta de categoria em risco).

**Parcelamentos — visão acionável** (≤5 bullets): destaque as que estão "acabando" e as "longe do fim". Não sugira renegociar parcelas que a memória do usuário explicitamente exclui.

**3 recomendações priorizadas** no formato:
```
[ALTO/MÉDIO IMPACTO · BAIXO/MÉDIO ESFORÇO] <título curto>
  Economia/ganho: <valor mensal · anual>
  Evidência: <transações/categorias específicas dos dados acima>
  Ação: <passo concreto>
```
Nunca proponha algo que contradiga a memória do usuário nem que crie nova conta.

**Próximos passos verificáveis** (≤3 bullets).

Termine com o disclaimer: "Isto não é aconselhamento financeiro licenciado."
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--framework", default=str(DEFAULT_FRAMEWORK))
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true", help="apenas imprime o prompt")
    args = ap.parse_args()

    snap = json.loads(pathlib.Path(args.snapshot).read_text())
    fw = pathlib.Path(args.framework).read_text() if pathlib.Path(args.framework).exists() else ""
    prompt = render_prompt(snap, fw)

    if args.out:
        pathlib.Path(args.out).write_text(prompt)
        print(f"ok|prompt|{args.out}")
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
