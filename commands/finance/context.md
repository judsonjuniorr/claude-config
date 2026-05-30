---
description: Gerencia restrições/contexto financeiro que análises futuras devem respeitar.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<texto livre> | list | prune]"
---

# /finance:context — Restrições e contexto (provider-agnóstico)

> **REGRA GLOBAL — perguntas ao usuário:** toda pergunta que exija resposta do usuário deve ser feita via tool `AskUserQuestion`, com 2-4 opções estruturadas (o campo de texto livre "Outro" é automático). **Nunca** faça perguntas inline no texto.

Wrapper conversacional sobre `commands/finance/scripts/memory.py`. Os dados ficam em `~/finance/memory.md` e são injetados em qualquer análise (Organizze e futuros providers) como diretivas que **a IA não pode contradizer**.

Path absoluto do script:
`/Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py`

Quando o usuário invocar `/finance:context`, classifique `$ARGUMENTS` e siga o fluxo. Não pré-inspecione filesystem.

---

## Modo 1 — Sem args (gerenciar)

1. Liste as 20 mais recentes:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py list --recent 20
   ```

2. Mostre ao usuário e pergunte via `AskUserQuestion`:
   - **A) Adicionar nova restrição** — vá ao Modo 2 pedindo o texto.
   - **B) Ver tudo** — rode `memory.py list`.
   - **C) Podar antigas (> 365d)** — rode `memory.py prune --older-than 365`.
   - **D) Sair**.

## Modo 2 — Texto livre (registrar)

`$ARGUMENTS` traz uma restrição ou contexto (ex.: "remédio X é prescrição médica", "dízimo é não-negociável", "não consigo diminuir parcela da casa").

1. (Opcional) Sugira uma `--tag` inferida do texto (`saude`, `casa`, `dizimo`, `assinatura`, `dívida`, `metodologia`, ...) via `AskUserQuestion` com opção "Pular".

2. Grave:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/memory.py add "<texto>" [--tag <opcional>]
   ```

3. Confirme em 1 linha: o que foi gravado e onde (`~/finance/memory.md`). Diga: "Próximo `/finance:organizze` já considera."

## Modo 3 — Sub-comandos diretos

| Argumento              | Comando                                          |
|------------------------|--------------------------------------------------|
| `list`                 | `memory.py list` (aceita `--recent N` extra)     |
| `prune`                | `memory.py prune --older-than 365` (ou valor passado) |

Mostre a saída ao usuário.

---

## Regras

- **Não chame `/finance:organizze`** automaticamente. Apenas CRUD.
- O script roda migração legacy automaticamente na primeira execução (`~/finance-organizze/memory.md` → `~/finance/memory.md`).
- Storage é editável à mão (`~/finance/memory.md`).
