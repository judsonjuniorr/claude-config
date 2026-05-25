---
description: Puxa dados do Organizze via API REST e gera análise financeira consolidada (saldo, projeção, recomendações).
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_close
argument-hint: "[<texto livre> | --history-days N | --future-days N | --no-analyze]"
---

# /finance:organizze — Organizze → análise consolidada

> **Subagent recomendado (quando instalado):** o Passo 6 delega a análise ao subagent `financial-analyst` via tool `Agent`. Se o arquivo `~/.claude/agents/financial-analyst.md` não existir, o passo cai automaticamente para `general-purpose` — o comando continua funcionando. Para instalar o subagent dedicado, rode `install.sh` neste repo e selecione `financial-analyst`.

Quando o usuário invocar `/finance:organizze`, siga estes passos **exatamente**. Não pule nenhum. Não pré-inspecione (não rode `git status`, não liste diretórios, não cheque versões — vá direto aos scripts; eles são auto-contidos e fazem migração legacy sozinhos).

Argumentos opcionais (parseie de `$ARGUMENTS`):
- `--history-days N` (default 180)
- `--future-days N` (default 90)
- `--no-analyze` → só puxa e salva snapshot, não chama o subagent

**Paths absolutos**:
- Scripts globais (provider-agnósticos): `/Users/judson/sources/personal/claude-config/commands/finance/scripts/`
- Scripts Organizze: `/Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/`
- Storage global: `~/finance/` (`memory.md`, `plans.md`)
- Storage Organizze: `~/finance/organizze/` (`snapshots/`, `reports/`, `budget-suggestions/`, `.auth`, `.config`, `balances.json`)
- Framework de análise (lido por `analyze.py`): `/Users/judson/sources/personal/claude-config/analista-financeiro-claude-code.md`

---

## Passo 0 — Roteamento de intenção

Se `$ARGUMENTS` estiver vazio ou contiver apenas flags (`--history-days`, `--future-days`, `--no-analyze`), vá direto ao Passo 1 (fluxo normal de análise).

Se `$ARGUMENTS` contém texto em linguagem natural, **não rode pull/analyze para "ter contexto"** — eles são caros (minutos) e existem só pro fluxo de análise. Classifique:

- **Objetivo/meta financeira** (valor + prazo + algo a comprar/contratar/quitar/guardar — "viagem", "quitar X", "guardar R$ Y até Z", "reserva de emergência"): **redirecione para `/finance:goal`** dizendo ao usuário em 1 linha "Isso parece um objetivo — abrindo `/finance:goal`" e siga as instruções daquele comando passando `$ARGUMENTS` como texto.

- **Restrição/contexto** (declarações sobre o que **não** mudar, prescrições, inegociáveis — "não consigo diminuir X", "Y é prescrição médica", "Z é não-negociável"): **redirecione para `/finance:context`** com a mesma lógica.

- **Pedido de análise/dúvida** (qualquer outra coisa: "como estou", "o que cortar", "vou perder algo?"): siga ao Passo 1.

Em dúvida real entre objetivo e restrição, pergunte ao usuário com `AskUserQuestion` qual dos dois comandos quer abrir. Em dúvida entre registrar e analisar, pergunte.

---

## Passo 1 — Verificar auth

```bash
ls ~/finance/organizze/.auth 2>/dev/null
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

Após o primeiro `pull.py`, se `~/finance/organizze/balances.json` ainda não existir:

1. Mostre ao usuário, com `jq '.accounts | map(select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))) | map({id, name, calculado: (._balance_cents / 100)})' "$SNAP"`, o saldo calculado de cada conta principal.

2. Use `AskUserQuestion` para confirmar: "O saldo calculado bate com o que aparece no app Organizze para cada conta?" Se não bater, pergunte conta por conta o saldo real (em reais, ex: `801.74`).

3. Chame:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/reconcile.py --snapshot "$SNAP" <id>=<centavos> [<id>=<centavos> ...]
   ```
   Ex.: `1575443=80174 5044376=194746` (R$ 801,74 e R$ 1.947,46).

4. O script grava `~/finance/organizze/balances.json` com o offset por conta. Pulls futuros aplicam automaticamente — não precisa repetir.

5. Re-rode o `pull.py` (Passo 3) para validar.

Pule este passo se `balances.json` já existe.

## Passo 2.7 — Mapear conta pagadora de cada cartão (rodar quando faltar)

A projeção de fluxo por conta (Passo 5+) precisa saber **qual conta paga cada cartão** pra debitar a fatura na data certa. Sem isso, faturas não entram na projeção e estouros silenciosos podem passar.

Após o primeiro `pull.py` (Passo 3), rode:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py cards-missing --snapshot "$SNAP"
```

Saída: `<card_id>|<card_name>` linha a linha — só cartões sem mapeamento. Se vier vazio, pule este passo.

Para cada linha:

1. Mostre ao usuário as contas principais ativas:
   ```bash
   jq '[.accounts[] | select(.archived==false and .institution_id != "cofrinho" and (.type == "checking" or .type == "savings"))] | map({id, name})' "$SNAP"
   ```

2. `AskUserQuestion`: "De qual conta é debitada a fatura do cartão **<card_name>**?" — opções dinâmicas (uma por conta principal).

3. Grave:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py card-account <card_id> <account_id>
   ```

Opcional — threshold de alerta para dias críticos (default R$ 0, sem margem):
```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/config.py set CASHFLOW_THRESHOLD_CENTS 20000
```
(`20000` = R$ 200 de margem; saldo projetado abaixo disso vira "dia crítico".)

Mapeamentos vivem em `~/finance/organizze/.config` (formato `KEY=VALUE`, 0600). Edição manual permitida.

## Passo 3 — Pull do snapshot

```bash
SNAP=~/finance/organizze/snapshots/$(date +%F-%H%M).json
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/pull.py \
  --out "$SNAP" \
  --history-days <N ou 180> \
  --future-days <N ou 90>
```

O script imprime linhas `info|...` no stderr (contagens por endpoint) e uma linha final `ok|snapshot|<path>` no stdout. Em caso de erro: `err|<code>|<detail>`.

Tratamento de erros:
- `err|http-401|...` → token rejeitado. Apague `~/finance/organizze/.auth` e volte ao Passo 2.
- `err|http-400|...` → User-Agent rejeitado. Verifique `~/finance/organizze/.auth` (campo `ORGANIZZE_USER_AGENT`).
- `err|network|...` → falhe rápido, reporte ao usuário.

## Passo 4 — Se `--no-analyze`, pare aqui

Imprima o path do snapshot e os totais (use `jq '.meta.totais' "$SNAP"`). Não chame o subagent.

## Passo 5 — Renderizar prompt da análise

```bash
REPORT=~/finance/organizze/reports/$(date +%F-%H%M).md
PROMPT=$(python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/analyze.py --snapshot "$SNAP")
```

`analyze.py` lê o snapshot + a seção 4.1 do framework `analista-financeiro-claude-code.md` + injeta `memory.md` e `plans.md` (de `~/finance/`) e devolve um prompt único pronto para o subagent.

## Passo 6 — Delegar ao subagent `financial-analyst`

Use a tool `Agent`:
- `subagent_type`: `financial-analyst` se existir em `~/.claude/agents/financial-analyst.md`. Caso não exista, **avise o usuário** ("subagent não instalado — use `general-purpose` desta vez? Para instalar, rode `ln -sf <claude-config-root>/agents/financial-analyst/financial-analyst.md ~/.claude/agents/`") e prossiga com `general-purpose`.
- `description`: `Análise financeira mensal Organizze`
- `prompt`: o conteúdo de `$PROMPT` (renderizado no passo 5).

Salve a resposta do subagent em `$REPORT`.

## Passo 6.5 — Capturar nova memória/objetivo (opcional)

Após a análise, ofereça registrar contexto/objetivos novos. Cada bloco é independente; pule se o usuário não tiver nada.

**6.5a — Memória/restrição** — pergunte via `AskUserQuestion` (single-select com "Pular"):

> Quer registrar alguma restrição ou contexto para futuras análises? Exemplos: "não consigo diminuir parcela da casa", "Mounjaro é prescrição médica", "dízimo é não-negociável".

Se houver resposta, grave:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py add "<texto do usuário>" [--tag <opcional>]
```

(Ou diga ao usuário que pode rodar `/finance:context` depois.)

**6.5b — Objetivo financeiro** — pergunte via `AskUserQuestion` (single-select com "Pular"):

> Quer registrar algum objetivo financeiro? Ex.: "guardar R$ 5000 para viagem em dezembro", "quitar dívida X até junho", "construir reserva de emergência de R$ 20000".

Se houver resposta, faça perguntas curtas em sequência (cada uma com "Pular" para opcional):

1. **Texto descritivo**: já capturado.
2. **Valor-alvo (R$)**: pergunte e converta pra centavos (ex.: `5000` → `500000`).
3. **Prazo (YYYY-MM-DD)**: opcional. "dezembro" → último dia do mês informado.
4. **Conta-destino**: opcional. Mostre lista de contas principais + cofrinhos do snapshot.
5. **Prioridade**: `negociavel` (default) ou `inegociavel`.

Grave:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py add "<texto>" \
  --target-cents <N> \
  [--deadline <YYYY-MM-DD>] \
  [--account "<nome livre>"] \
  [--priority negociavel|inegociavel]
```

(Ou diga ao usuário que pode rodar `/finance:goal` depois.)

Memória e objetivos vivem em `~/finance/{memory,plans}.md` — provider-agnósticos. `analyze.py` injeta automaticamente nas próximas análises. Para gerenciar fora do fluxo de análise: `/finance:context` e `/finance:goal`.

## Passo 7 — Sugerir atualização de orçamento

Após a análise do subagent, rode:

```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/organizze-scripts/suggest_budgets.py \
  --snapshot "$SNAP" --top 20
```

O script:
- Calcula, por categoria, `max(mediana 3m, p75 6m)`, garante ≥ realizado do mês corrente, arredonda em R$ 10.
- Imprime tabela markdown: Atual | Realizado | Mediana 3m | p75 6m | **Sugerido** | Δ | Confiança.
- Grava JSON em `~/finance/organizze/budget-suggestions/YYYY-MM-DD-HHMM.json` com os payloads (current_month + next_month).

Apresente a tabela ao usuário e diga:

> A API REST do Organizze não permite atualizar orçamento via HTTP — aplique manualmente em https://app.organizze.com.br/orcamento. JSON com os valores está em `<path>` para referência.

Se `--history-days` no Passo 3 foi menor que 180, avise: "histórico curto, confiança baixa — sugiro re-rodar `/finance:organizze` com `--history-days 180` para sugestões mais sólidas".

## Passo 8 — Apresentar ao usuário

Imprima no chat, nesta ordem:

1. O conteúdo do relatório do subagent. Estrutura esperada:
   - TL;DR
   - Números-chave
   - Atrasadas — ação imediata
   - **Metas de categoria — status**
   - **Objetivos do usuário — viabilidade neste mês**
   - **Plano de transferências e poupança** (destaque visualmente — é o coração desta análise)
   - **Objetivos pausados neste ciclo** (se houver)
   - Parcelamentos — visão acionável
   - 3 recomendações priorizadas
   - Próximos passos verificáveis
   - Disclaimer
2. Linha final:
   ```
   📄 Snapshot: <path do SNAP>
   📊 Relatório: <path do REPORT>
   ```

Não invente números. Se o subagent não cobrir algum campo dos "Números-chave", marque `(sem dados)` em vez de chutar.

---

## Regras gerais

- **Não pré-inspecione** o filesystem antes do Passo 1. Vá direto.
- **Nunca commite** `~/finance/`. Está fora do repo.
- **Nunca exponha** o token em logs ou mensagens. Se precisar mostrar, mascare como `org_xxx…xxx`.
- Se o usuário rodar duas vezes seguidas, cada execução gera arquivos com timestamp distinto — sem corrupção.
- Migração legacy de `~/finance-organizze/` → `~/finance/{,organizze/}` é automática na primeira execução de qualquer script. Não rode nada manualmente.

## Comandos relacionados

- **`/finance:goal`** — CRUD de objetivos financeiros (`~/finance/plans.md`).
- **`/finance:context`** — CRUD de restrições/contexto (`~/finance/memory.md`).

Ambos são provider-agnósticos: qualquer provider futuro consome o mesmo storage.

## Subagents recomendados

Subagent deste repo (`agents/`) que aprimora o resultado quando instalado. O comando funciona sem ele — o Passo 6 cai automaticamente para `general-purpose`.

- **[`financial-analyst`](../../../agents/financial-analyst/)** — análise financeira pessoal calibrada (consome snapshots Organizze, respeita memórias do usuário, gera plano priorizado conforme o framework `analista-financeiro-claude-code.md`). Instale via `install.sh` selecionando `financial-analyst`.
