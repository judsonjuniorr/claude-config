---
description: Puxa dados do Organizze via API REST e gera análise financeira consolidada (saldo, projeção, recomendações).
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_close
argument-hint: "[--history-days N] [--future-days N] [--no-analyze]"
---

# /finance:organizze — Organizze → análise consolidada

Quando o usuário invocar `/finance:organizze`, siga estes passos **exatamente**. Não pule nenhum. Não pré-inspecione (não rode `git status`, não liste diretórios, não cheque versões — vá direto aos scripts; eles são auto-contidos).

Argumentos opcionais (parseie de `$ARGUMENTS`):
- `--history-days N` (default 180)
- `--future-days N` (default 90)
- `--no-analyze` → só puxa e salva snapshot, não chama o subagent

Paths absolutos:
- Scripts: `/Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/`
- Storage: `~/finance-organizze/`
- Framework de análise (lido por `analyze.py`): `/Users/judson/sources/personal/claude-config/analista-financeiro-claude-code.md`

---

## Passo 1 — Verificar auth

```bash
ls ~/finance-organizze/.auth 2>/dev/null
```

- **Arquivo existe** → pule para Passo 3.
- **Não existe** → execute Passo 2.

## Passo 2 — Onboarding (primeira execução)

1. Abra a página de tokens via Playwright headed (a sessão MCP já está autenticada):
   ```
   mcp__playwright__browser_navigate → https://app.organizze.com.br/configuracoes/api-keys
   ```

2. Mostre ao usuário em chat:
   > Abri a página de API keys do Organizze. Crie um novo token (botão "Gerar nova chave"), copie, e me passe abaixo.

3. Use `AskUserQuestion` com duas perguntas:
   - "Qual o email da sua conta Organizze?" (header: "Email")
   - "Cole o token gerado:" (header: "Token")

4. Grave as credenciais executando o script:
   ```bash
   printf '%s\n%s\n' "$EMAIL" "$TOKEN" | bash /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/setup_auth.sh
   ```
   Substitua `$EMAIL` e `$TOKEN` pelos valores reais (não exponha o token no histórico se possível — passe via heredoc).

5. O script valida via `GET /accounts`. Se retornar `ok|auth-saved|...`, prossiga. Se `err|bad-credentials|...`, avise e refaça o Passo 2.

6. Feche o browser:
   ```
   mcp__playwright__browser_close
   ```

## Passo 2.5 — Calibrar saldo inicial (apenas na 1ª execução)

A API `/accounts` do Organizze **não devolve saldo atual** — o `pull.py` calcula somando as transações pagas dos últimos 5 anos. O saldo inicial que o usuário informou ao criar a conta no app **não está exposto** e gera divergência.

Após o primeiro `pull.py`, se `~/finance-organizze/balances.json` ainda não existir:

1. Mostre ao usuário, com `jq '.accounts | map(select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))) | map({id, name, calculado: (._balance_cents / 100)})' "$SNAP"`, o saldo calculado de cada conta principal.

2. Use `AskUserQuestion` para confirmar: "O saldo calculado bate com o que aparece no app Organizze para cada conta?" Se não bater, pergunte conta por conta o saldo real (em reais, ex: `801.74`).

3. Chame:
   ```bash
   python3 commands/finance/organizze-scripts/reconcile.py --snapshot "$SNAP" <id>=<centavos> [<id>=<centavos> ...]
   ```
   Ex.: `1575443=80174 5044376=194746` (R$ 801,74 e R$ 1.947,46).

4. O script grava `~/finance-organizze/balances.json` com o offset por conta. Pulls futuros aplicam automaticamente — não precisa repetir.

5. Re-rode o `pull.py` (Passo 3) para validar.

Pule este passo se `balances.json` já existe.

## Passo 3 — Pull do snapshot

```bash
SNAP=~/finance-organizze/snapshots/$(date +%F-%H%M).json
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/pull.py \
  --out "$SNAP" \
  --history-days <N ou 180> \
  --future-days <N ou 90>
```

O script imprime linhas `info|...` no stderr (contagens por endpoint) e uma linha final `ok|snapshot|<path>` no stdout. Em caso de erro: `err|<code>|<detail>`.

Tratamento de erros:
- `err|http-401|...` → token rejeitado. Apague `~/finance-organizze/.auth` e volte ao Passo 2.
- `err|http-400|...` → User-Agent rejeitado. Verifique `~/finance-organizze/.auth` (campo `ORGANIZZE_USER_AGENT`).
- `err|network|...` → falhe rápido, reporte ao usuário.

## Passo 4 — Se `--no-analyze`, pare aqui

Imprima o path do snapshot e os totais (use `jq '.meta.totais' "$SNAP"`). Não chame o subagent.

## Passo 5 — Renderizar prompt da análise

```bash
REPORT=~/finance-organizze/reports/$(date +%F-%H%M).md
PROMPT=$(python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/analyze.py --snapshot "$SNAP")
```

`analyze.py` lê o snapshot + a seção 4.1 do framework `analista-financeiro-claude-code.md` e devolve um prompt único pronto para o subagent.

## Passo 6 — Delegar ao subagent `financial-analyst`

Use a tool `Agent`:
- `subagent_type`: `financial-analyst` se existir em `~/.claude/agents/financial-analyst.md`. Caso não exista, **avise o usuário** ("subagent não instalado — use `general-purpose` desta vez? Para instalar, rode `ln -sf <claude-config-root>/agents/financial-analyst/financial-analyst.md ~/.claude/agents/`") e prossiga com `general-purpose`.
- `description`: `Análise financeira mensal Organizze`
- `prompt`: o conteúdo de `$PROMPT` (renderizado no passo 5).

Salve a resposta do subagent em `$REPORT`.

## Passo 6.5 — Capturar nova memória (após apresentar a análise)

Antes de fechar a sessão, **pergunte ao usuário** via `AskUserQuestion` (single-select, opção "Pular" disponível):

> Quer registrar alguma restrição ou contexto para futuras análises? Exemplos: "não consigo diminuir parcela da casa", "Mounjaro é prescrição médica", "dízimo é não-negociável".

Se houver resposta, grave:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/memory.py add "<texto do usuário>" [--tag <opcional>]
```

A memória vai para `~/finance-organizze/memory.md` com timestamp; `analyze.py` injeta automaticamente nas próximas análises e o subagent é instruído a **não sugerir nada que a contradiga**.

Para consultar/limpar:
- `memory.py list [--recent N]`
- `memory.py prune --older-than 365`

## Passo 7 — Sugerir atualização de orçamento

Após a análise do subagent, rode:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/suggest_budgets.py \
  --snapshot "$SNAP" --top 20
```

O script:
- Calcula, por categoria, `max(mediana 3m, p75 6m)`, garante ≥ realizado do mês corrente, arredonda em R$ 10.
- Imprime tabela markdown: Atual | Realizado | Mediana 3m | p75 6m | **Sugerido** | Δ | Confiança.
- Grava JSON em `~/finance-organizze/budget-suggestions/YYYY-MM-DD-HHMM.json` com os payloads (current_month + next_month).

Apresente a tabela ao usuário e diga:

> A API REST do Organizze não permite atualizar orçamento via HTTP — aplique manualmente em https://app.organizze.com.br/orcamento. JSON com os valores está em `<path>` para referência.

Se `--history-days` no Passo 3 foi menor que 180, avise: "histórico curto, confiança baixa — sugiro re-rodar `/finance:organizze` com `--history-days 180` para sugestões mais sólidas".

## Passo 8 — Apresentar ao usuário

Imprima no chat, nesta ordem:

1. O conteúdo do relatório do subagent (TL;DR → Números-chave → 3 recomendações → próximos passos → disclaimer).
2. Linha final:
   ```
   📄 Snapshot: <path do SNAP>
   📊 Relatório: <path do REPORT>
   ```

Não invente números. Se o subagent não cobrir algum campo dos "Números-chave", marque `(sem dados)` em vez de chutar.

---

## Regras gerais

- **Não pré-inspecione** o filesystem antes do Passo 1. Vá direto.
- **Nunca commite** `~/finance-organizze/`. Está fora do repo.
- **Nunca exponha** o token em logs ou mensagens. Se precisar mostrar, mascare como `org_xxx…xxx`.
- Se o usuário rodar duas vezes seguidas, cada execução gera arquivos com timestamp distinto — sem corrupção.
