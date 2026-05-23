# Analista Financeiro com Claude Code — Deep Research Consolidado

Pesquisa sobre **prompts, skills, commands e subagents** existentes para transformar o Claude Code em um analista financeiro pessoal, com acesso a:

- **Histórico de transações** (CSV/OFX/MT940/SQLite/email)
- **Saldo atual** (por conta)
- **Transações futuras** (recorrentes, agendadas, projetadas)

…e capaz de **sugerir mudanças, melhorias, otimizações** (orçamento, dívida, poupança, cenários).

Documento gerado em **2026-05-23**.

---

## 1. Visão geral do ecossistema

O ecossistema do Claude Code oferece três primitivas relevantes:

| Primitiva | O que é | Onde mora | Quando usar |
|---|---|---|---|
| **Skill** | Pasta com `SKILL.md` (YAML frontmatter + instruções) + scripts/refs opcionais. Carregada sob demanda quando o `description` casa com o pedido do usuário. | `~/.claude/skills/<nome>/` ou `.claude/skills/` no projeto | Conhecimento de domínio + ferramentas reutilizáveis (parsers CSV, calculadoras DCF, dashboards). |
| **Subagent** | Markdown em `.claude/agents/<nome>.md` com `name`, `description`, `tools`, `model` no frontmatter + system prompt. Executa em janela de contexto isolada. | `.claude/agents/` | Delegação de tarefas pesadas (modelagem, análise de cenário) que não devem poluir o contexto principal. |
| **Slash command** | Markdown em `.claude/commands/<nome>.md`. Atalho de prompt parametrizável. | `.claude/commands/` | Fluxos repetitivos com argumentos (`/financial-health`, `/saas-health`). |

> **Token cost**: o Claude só carrega `name + description` de cada skill no contexto inicial (~100 tokens cada). O corpo do `SKILL.md` só entra quando há match — então o `description` precisa ser específico e cobrir os gatilhos (palavras-chave, intenções).

---

## 2. Skills/Agents públicos relevantes (mapa)

### 2.1 Skills oficiais Anthropic

- **`anthropics/financial-services`** — comps, DCF, LBO, 3-statement, deck QC, Excel audit. Foco institucional, mas os parsers de Excel e os geradores de tabela são reaproveitáveis.
- **`anthropics/claude-cookbooks` → `skills/notebooks/02_skills_financial_applications.ipynb`** — referência canônica para criar skills financeiras (loaders de CSV, geração de relatórios, sandbox Python).
- **Six skills for financial service professionals (Claude support)** — pacote oficial para profissionais financeiros.

### 2.2 Skills focadas em finanças pessoais (estado da arte)

| Repo | Diferencial para o nosso caso |
|---|---|
| **`googlarz/finance-assistant`** (taxde-skill) | **Mais próximo do alvo**. Profile-first, local-only, SQLite + JSON. 13 formatos de banco (CSV/MT940/OFX), Monte Carlo, avalanche vs. snowball, FIRE, rent vs. buy. Criptografia Fernet, `chmod 600`, git-guard. |
| **`chardigio/copilot-money-skill`** | Lê direto o SQLite do app Copilot Money no macOS. Padrão limpo para **plug em banco de dados existente**. |
| **`cjpatten/canadian-finance-planner-skill`** | Entrevista estruturada em 7 rodadas, dashboard HTML auto-contido com Chart.js, arquivos persistentes para pausar/retomar sessão. Modelo de "coaching contínuo". |
| **`alirezarezvani/claude-skills/finance`** | Coleção com `financial-analyst`, `saas-metrics-coach`, `business-investment-advisor`. Inclui `/financial-health` e `/saas-health`. Tools em Python puro (stdlib). |
| **`JoelLewis/finance_skills`** | 81 skills em 7 plugins (investment mgmt, compliance, advisory, trading, ops). Útil como cardápio. |
| **`OctagonAI/skills`** | Skills agênticas para research financeiro (SEC filings, cross-reference). |
| **`tradermonty/claude-trading-skills`** | Análise técnica, calendário econômico, screeners. Fora do escopo pessoal, mas o padrão de "skill de coach" é replicável. |

### 2.3 Subagents prontos

- **`VoltAgent/awesome-claude-code-subagents`** — coleção com 100+ subagents; o relevante é `categories/07-specialized-domains/quant-analyst.md` (modelagem quantitativa, VaR, backtesting).
- **Claude Cookbook → "The Chief of Staff Agent"** — padrão `financial-analyst` subagent com scripts `hiring_impact.py`, `financial_forecast.py`, `simple_calculation.py`. **Excelente template** de como um subagent delega cálculo para scripts Python locais.

---

## 3. Padrões extraídos da pesquisa

### 3.1 Frontmatter de skill (formato consagrado)

```yaml
---
name: analista-financeiro-pessoal
description: |
  Analisa transações, saldos e projeções financeiras pessoais. Use quando o
  usuário pedir análise de gastos, orçamento, projeção de saldo, otimização
  de dívida, simulação de cenário (FIRE, rent vs. buy, freelance), ou
  importação de extratos (CSV/OFX/MT940). Gatilhos: "como estou no mês",
  "quanto vou ter em X", "vale a pena", "meu saldo", "minha fatura".
license: MIT
compatibility:
  product: claude-code
  packages: [python>=3.10, sqlite3]
  network: false
---
```

### 3.2 Frontmatter de subagent (padrão Anthropic)

```yaml
---
name: financial-analyst
description: Use este agente para análise quantitativa de impacto financeiro — projeções de fluxo de caixa, modelagem de cenários (alta/base/baixa), variação orçamentária, runway pessoal, comparação avalanche vs snowball, simulação Monte Carlo de aposentadoria. Invoque sempre que a pergunta exigir cálculo numérico não-trivial sobre dados financeiros já carregados.
tools: Read, Write, Edit, Bash, Glob, Grep
model: opus
---
```

### 3.3 Arquitetura de dados (consenso entre repos)

```
~/.finance/
├── finance.db            # SQLite WAL, FKs ativas
├── profile.json          # perfil do usuário (locale, moeda, perfil de risco)
├── originals/            # cópia imutável dos extratos importados
├── exports/              # relatórios e dashboards gerados
└── audit.log             # trilha de auditoria timestamped
```

Tabelas mínimas: `accounts`, `transactions`, `categories`, `budgets`, `goals`, `debts`, `recurring`, `scenarios`.

### 3.4 Pipeline de importação (de `googlarz/finance-assistant`)

1. **Detecção de formato** por fingerprint do header (DKB, ING, N26, Wise, Revolut, MT940, OFX/QFX, CSV genérico).
2. **Preservar original** em `originals/` antes de parsear.
3. **Parse** → `(date, amount, payee, description)`.
4. **Preview** das 10 primeiras linhas para revisão humana.
5. **Auto-categorize** (~30 categorias) por regras keyword/payee.
6. **Deduplicate** por chave composta `merchant + date + amount + time`.
7. **Update** saldo da conta e actuals do orçamento.
8. **Learner** corrige regras a partir das reclassificações do usuário.

### 3.5 Motor de transações futuras

Três fontes que devem ser unificadas:

- **Recorrentes detectadas**: padrão de pagamento mensal no histórico (Netflix, aluguel, salário).
- **Agendadas explícitas**: input manual ou parse de fatura de cartão / boleto.
- **Projetadas**: extrapolação por categoria (média 3-6 meses) para orçamento forward-looking.

Saída esperada: `cashflow forecast` de 13 semanas (padrão FP&A) com p10/p50/p90 quando há ruído.

### 3.6 Conjunto mínimo de scripts Python (stdlib only)

| Script | Função |
|---|---|
| `import_statement.py` | Roteia para parser por fingerprint, devolve transações normalizadas. |
| `categorize.py` | Aplica regras + ML simples (Bayes/keyword) + aprende com correções. |
| `balance.py` | Saldo atual por conta + saldo consolidado + projetado em N dias. |
| `budget_variance.py` | Actual vs. budget vs. prior period, com pacing alert. |
| `cashflow_forecast.py` | 13 semanas forward, com recorrentes + agendadas + projeção. |
| `debt_optimizer.py` | Avalanche vs. snowball, payoff date, juros economizados. |
| `goal_tracker.py` | Projeção de data de conclusão por meta + contribuição mensal alvo. |
| `scenario_engine.py` | FIRE, rent vs. buy, freelance break-even, debt vs. invest. |
| `monte_carlo.py` | 10k simulações, p10/p50/p90 para portfólio/FIRE/payoff. |
| `dashboard.py` | Gera HTML auto-contido com Chart.js (sem deps externas). |

---

## 4. Catálogo de prompts/system prompts (copiar e adaptar)

### 4.1 System prompt — subagent `financial-analyst` (consolidado)

> Você é um analista financeiro pessoal sênior. Seu foco é converter dados brutos (transações, saldos, projeções) em **decisões acionáveis**: o que cortar, o que renegociar, quando o saldo cai abaixo do mínimo, qual estratégia de dívida economiza mais, se a meta é alcançável.
>
> **Regras invioláveis**:
> 1. **Nunca invente número.** Toda métrica deve sair de cálculo sobre dados reais ou ser marcada como `[estimado: <fonte>]`.
> 2. **Comprometa-se com a metodologia antes de calcular.** Diga "vou usar média móvel 6m das categorias variáveis + recorrentes confirmadas" antes de rodar, não no meio.
> 3. **Tudo local.** Nunca exfiltre dados financeiros. Sem chamadas externas exceto cotações públicas explicitamente autorizadas.
> 4. **PII off.** Ao gerar exemplo/exporte, remova nomes, números de conta, empregador.
> 5. **Disclaimer.** Toda recomendação termina com: "Isto não é aconselhamento financeiro licenciado."
> 6. **Crise primeiro.** Se detectar saldo negativo recorrente, juros rotativos, ou parcela > 30% da renda, ative protocolo de crise antes de qualquer otimização.
>
> **Saída padrão**: TL;DR de 3 linhas → tabela de números → 3 recomendações priorizadas (impacto × esforço) → próximos passos verificáveis.

### 4.2 Prompts conversacionais (gatilhos)

| Intenção do usuário | Resposta esperada |
|---|---|
| "Como estou indo no orçamento deste mês?" | Variância por categoria + alerta de overspend + pacing ("85% de Mercado com 50% do mês"). |
| "Gastei R$42 no mercado" | Transação auto-categorizada, actual do orçamento atualizado, confirmação curta. |
| "Quanto vou ter em 30 dias?" | Saldo atual + recorrentes futuras + agendadas + projeção média variável. Range p10/p50/p90. |
| "Vale a pena trocar de plano de celular?" | Cenário comparativo: custo atual × proposto × payback × impacto no orçamento anual. |
| "Melhor forma de quitar minhas dívidas?" | Avalanche vs. snowball lado a lado, debt-free date, juros economizados, recomendação. |
| "Posso me aposentar aos 50?" | Monte Carlo de 10k simulações, distribuição p10/p50/p90, taxa de sucesso, gatilhos de ajuste. |
| "Importa essa fatura aí" | Detecta formato → preview → categoriza → confirma → grava. |

### 4.3 Slash commands sugeridos

```
/saldo                  → snapshot atual + projeção 7/30/90 dias
/orcamento [mes]        → variance report + pacing
/gastos [categoria]     → top merchants, tendência 6m, anomalias
/dividas                → comparação avalanche vs snowball + plano
/projecao [horizonte]   → cashflow forecast 13w/6m/12m
/cenario <descricao>    → dispara scenario_engine
/importar <arquivo>     → roteia para pipeline de import
/dashboard              → gera HTML auto-contido em ~/.finance/exports/
/saude-financeira       → score consolidado + 3 ações prioritárias
```

### 4.4 Prompt de "entrevista inicial" (do canadian-finance-planner-skill)

Estrutura em **7 rodadas** que preenche o perfil:

1. Contexto de vida (idade, família, dependentes, cidade).
2. Renda (líquida, variável, paralelas).
3. Despesas fixas e variáveis (parse de extrato se houver).
4. Dívidas (taxa, saldo, parcela mínima, vencimento).
5. Ativos (conta, investimentos, imóvel, veículo).
6. Seguros e proteções.
7. Metas (curto/médio/longo prazo, com valor e prazo).

Cada rodada **grava em arquivo** (`profile.md`, `income.md`, …) para retomar entre sessões.

---

## 5. Estratégia de "transações futuras" (lacuna na maioria dos repos)

A maioria dos repos cobre histórico e saldo bem, mas **transações futuras** ficam fracas. Padrão recomendado, combinando o melhor de cada fonte:

```python
def future_transactions(horizon_days: int) -> list[Tx]:
    out = []
    out += scheduled_explicit()                 # boletos, agendamentos do banco
    out += recurring_detected(min_occurrences=3) # padrão mensal no histórico
    out += projected_by_category(
        method="rolling_median_6m",
        categories=variable_only(),
        confidence=("p10", "p50", "p90"),
    )
    return dedupe_by(out, key=("date", "amount", "payee"))
```

**Detecção de recorrentes** (heurística mínima):
- mesmo `payee` (após normalização)
- aparece em ≥3 dos últimos 6 meses
- variação de valor < 15%
- intervalo médio dentro de ±3 dias do esperado (mensal/anual)

Saída do forecast: tabela diária com `saldo_projetado_p50`, `saldo_projetado_p10`, e flag `alerta_saldo_minimo`.

---

## 6. Sugestões, melhorias e otimizações (capacidade requerida)

O analista deve produzir três tipos de recomendação:

### 6.1 Cortes e renegociações
- Subscriptions duplicadas/ociosas (mesma categoria, ≥2 ativas).
- Tarifas bancárias evitáveis (compara com contas digitais).
- Categorias acima da mediana de pares (se houver benchmark) ou acima do próprio histórico (>1.5σ).

### 6.2 Otimização estrutural
- **Dívida**: avalanche vs. snowball; consolidação; portabilidade.
- **Poupança**: alocação 50/30/20 com override por meta; reserva de emergência (3-6× despesas).
- **Investimento**: alocação por horizonte da meta; rebalanceamento; custo de oportunidade (debt vs. invest).

### 6.3 Decisões de ciclo de vida
- Comprar vs. alugar (NPV multi-ano, com IPTU, manutenção, custo de oportunidade).
- CLT vs. PJ break-even.
- Antecipação de 13º / FGTS / restituição IR.
- FIRE: anos para independência ao ritmo atual.

**Formato de cada recomendação**:

```
[ALTO IMPACTO · BAIXO ESFORÇO] Cancelar Spotify duplicado
  Economia: R$ 21,90/mês · R$ 262,80/ano
  Evidência: 2 cobranças "SPOTIFY" em 03/05 e 14/05
  Ação: cancelar conta antiga (terminada em ****1234)
```

---

## 7. Segurança e privacidade (não-negociável)

Consenso entre `finance-assistant`, `canadian-finance-planner-skill` e cookbook Anthropic:

- **Local-only por padrão**. Sem upload de dados financeiros para serviços externos.
- **Criptografia em repouso** (Fernet AES-128-CBC + HMAC-SHA256, PBKDF2 480k iterações).
- **Permissões**: `chmod 600` em arquivos, `700` em diretórios.
- **Git guard**: skill adiciona `.finance/` ao `.gitignore` na primeira execução.
- **Audit log**: toda leitura/escrita timestamped.
- **PII strip**: ao gerar export "para compartilhar", remover nomes próprios, números de conta, empregador, endereços.
- **Sem aconselhamento licenciado**: disclaimer fixo em toda recomendação.

---

## 8. Esqueleto recomendado para implementação local

Estrutura proposta a colocar em `~/.claude/skills/analista-financeiro/`:

```
analista-financeiro/
├── SKILL.md                      # frontmatter + instruções principais
├── README.md                     # docs humanas (opcional)
├── references/
│   ├── categorias.md             # taxonomia de 30 categorias
│   ├── regras-categorizacao.md   # keyword → categoria
│   ├── crise-financeira.md       # protocolo de crise
│   └── disclaimer.md             # texto legal padrão
├── scripts/
│   ├── import_statement.py
│   ├── categorize.py
│   ├── balance.py
│   ├── budget_variance.py
│   ├── cashflow_forecast.py
│   ├── debt_optimizer.py
│   ├── goal_tracker.py
│   ├── scenario_engine.py
│   ├── monte_carlo.py
│   └── dashboard.py
└── templates/
    ├── dashboard.html.j2         # template Chart.js
    ├── relatorio-mensal.md.j2
    └── plano-acao.md.j2
```

Subagent complementar em `~/.claude/agents/financial-analyst.md` para isolar cálculos pesados.

Slash commands em `~/.claude/commands/` (um arquivo por comando: `saldo.md`, `orcamento.md`, etc.).

---

## 9. Roadmap de implementação (sugestão)

1. **MVP (1-2 dias)**: `SKILL.md` + `import_statement.py` (CSV genérico + OFX) + `balance.py` + `/saldo`.
2. **Categorização (1 dia)**: `categorize.py` com regras + persistência de correções.
3. **Orçamento (1 dia)**: `budget_variance.py` + `/orcamento`.
4. **Forecast (2 dias)**: detecção de recorrentes + `cashflow_forecast.py` + `/projecao`.
5. **Otimizações (2 dias)**: `debt_optimizer.py` + `scenario_engine.py` + recomendações priorizadas.
6. **Dashboard (1 dia)**: `dashboard.py` com Chart.js inline.
7. **Subagent + Monte Carlo**: para perguntas pesadas (FIRE, cenário multi-variável).

---

## 10. Referências consultadas

- [Anthropic — Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Anthropic — Create custom subagents (docs)](https://code.claude.com/docs/en/sub-agents)
- [Anthropic — The Chief of Staff Agent (cookbook)](https://platform.claude.com/cookbook/claude-agent-sdk-01-the-chief-of-staff-agent)
- [Anthropic — Skills for financial applications (cookbook notebook)](https://platform.claude.com/cookbook/skills-notebooks-02-skills-financial-applications)
- [Anthropic — Six skills for financial service professionals](https://support.claude.com/en/articles/12663107-claude-for-financial-services-skills)
- [anthropics/financial-services (GitHub)](https://github.com/anthropics/financial-services/)
- [anthropics/claude-code — skill-development SKILL.md](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md)
- [googlarz/finance-assistant (taxde-skill)](https://github.com/googlarz/taxde-skill)
- [chardigio/copilot-money-skill](https://github.com/chardigio/copilot-money-skill)
- [cjpatten/canadian-finance-planner-skill](https://github.com/cjpatten/canadian-finance-planner-skill)
- [alirezarezvani/claude-skills — finance](https://github.com/alirezarezvani/claude-skills/blob/main/finance/CLAUDE.md)
- [alirezarezvani/claude-skills — financial-analyst](https://alirezarezvani.github.io/claude-skills/skills/finance/financial-analyst/)
- [JoelLewis/finance_skills](https://github.com/JoelLewis/finance_skills)
- [OctagonAI/skills](https://github.com/OctagonAI/skills)
- [VoltAgent/awesome-claude-code-subagents — quant-analyst](https://github.com/VoltAgent/awesome-claude-code-subagents/blob/main/categories/07-specialized-domains/quant-analyst.md)
- [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills)
- [Finance Manager skill (MCP Market)](https://mcpmarket.com/tools/skills/finance-manager)
- [Snyk — Top 8 Claude Skills for Finance & Quant Devs](https://snyk.io/articles/top-claude-skills-finance-quantitative-developers/)
- [CFO Connect — 25 Claude Prompts for Finance Teams](https://www.cfoconnect.eu/resources/finance-insights/25-claude-prompts-finance-teams-cowork-code-fpa/)
- [Sid Saladi — 100+ Prompts for Claude Financial Analysis](https://sidsaladi.substack.com/p/100-prompts-for-claude-financial)
- [linas.substack — Claude Sonnet 4.6 as Financial Analyst](https://linas.substack.com/p/claudeinfinance)
- [Medium — Personal Finance Tracker w/ Claude (Chathuranga, 2026)](https://medium.com/@shanakachathuranga/how-i-built-a-personal-finance-tracker-using-claude-with-almost-zero-effort-fc95f310fdd1)
- [joseparreogarcia.substack — What the docs don't tell you about Claude Code skills](https://joseparreogarcia.substack.com/p/claude-code-skills-explained)
- [Claude Directory — Finance Skills](https://www.claudedirectory.org/skills/claude-skills-finance-skills)
- [FastMCP — finance-skills](https://fastmcp.me/skills/details/2098/finance-skills)
- [gexijin.github.io/vibe — Create a Subagent in Claude Code](https://gexijin.github.io/vibe/Create_subagents)
- [ClaudSkills — Funding Trend Forecaster](https://claudskills.com/skills/funding-trend-forecaster/)
- [ginlix-ai/LangAlpha — Claude Code for Finance](https://github.com/ginlix-ai/langalpha)
