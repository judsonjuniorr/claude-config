---
description: Gerencia objetivos financeiros (metas de poupança/economia) consumidos por qualquer provider de análise.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<texto livre> | list | done <ts> | pause <ts> | cancel <ts> | activate <ts> | prune]"
---

# /finance:goal — Objetivos financeiros (provider-agnóstico)

Wrapper conversacional sobre `commands/finance/scripts/plans.py`. Os dados ficam em `~/finance/plans.md` e são consumidos por `/finance:organizze` (e futuros providers) automaticamente.

Path absoluto do script:
`/Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py`

Quando o usuário invocar `/finance:goal`, **classifique `$ARGUMENTS`** e siga o fluxo correspondente. Não pré-inspecione filesystem.

---

## Modo 1 — Sem args (gerenciar)

1. Liste objetivos ativos:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py list --status active
   ```
2. Mostre a saída ao usuário (curta, 1 linha por objetivo) e pergunte via `AskUserQuestion` o que fazer:
   - **A) Adicionar novo objetivo** — vá ao Modo 2 pedindo o texto.
   - **B) Marcar um como concluído** — pergunte o `ts` (header completo) e rode `plans.py done "<ts>"`.
   - **C) Pausar / cancelar / reativar** — pergunte `ts` e novo status, rode `plans.py status "<ts>" paused|cancelled|active`.
   - **D) Ver histórico completo (incluindo done/cancelled)** — rode `plans.py list` sem filtro.
   - **E) Podar concluídos antigos** — rode `plans.py prune --older-than-done 365`.
   - **F) Sair**.

## Modo 2 — Texto livre (registrar)

`$ARGUMENTS` traz a descrição de um novo objetivo (ex.: "guardar R$ 5000 para viagem em dezembro").

1. **Pré-preencha o que dá pra inferir do texto** (valor, prazo, conta). Pergunte só o que faltar via `AskUserQuestion` (cada uma com "Pular" quando opcional):
   - **Valor-alvo (R$)** — obrigatório. Faixa ("9~12k") → proponha a média. Converta para centavos.
   - **Prazo (YYYY-MM-DD)** — opcional. "dezembro" → último dia do mês informado. "junho/julho desse ano" → último mês mencionado.
   - **Conta-destino** — opcional. Texto livre.
   - **Prioridade** — `negociavel` (default — pausa em dia crítico) ou `inegociavel` (mantém cortando outras categorias).

2. Grave:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/plans.py add "<texto>" \
     --target-cents <N> \
     [--deadline <YYYY-MM-DD>] \
     [--account "<texto>"] \
     [--priority negociavel|inegociavel]
   ```

3. Confirme em 1-2 linhas: o que foi registrado e onde (`~/finance/plans.md`). Diga: "Próximo `/finance:organizze` já considera."

## Modo 3 — Sub-comandos diretos

Se `$ARGUMENTS` começa com uma das palavras abaixo, repasse direto para o script:

| Argumento                | Comando                                                            |
|--------------------------|--------------------------------------------------------------------|
| `list`                   | `plans.py list` (aceita `--status` / `--recent` extras)            |
| `done <ts>`              | `plans.py done "<ts>"`                                             |
| `pause <ts>`             | `plans.py status "<ts>" paused`                                    |
| `cancel <ts>`            | `plans.py status "<ts>" cancelled`                                 |
| `activate <ts>`          | `plans.py status "<ts>" active`                                    |
| `prune`                  | `plans.py prune --older-than-done 365` (ou usa `--older-than-done` informado) |

Mostre a saída do script ao usuário.

---

## Regras

- **Não chame `/finance:organizze`** automaticamente. Este comando é CRUD; análise é separada.
- O script roda migração legacy automaticamente (`~/finance-organizze/` → `~/finance/`) na primeira execução. Não precisa fazer nada manualmente.
- Storage é editável à mão (`~/finance/plans.md`).
