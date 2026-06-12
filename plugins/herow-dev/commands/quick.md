---
description: (herow) Pipeline gstack ponta-a-ponta para mudança simples (worktree → autoplan → implementar → review → qa → ship)
argument-hint: <descrição curta da mudança>
model: sonnet
---

## Model check

```bash
python3 -c "
import json, os, sys
model = os.environ.get('CLAUDE_MODEL', '')
if not model:
    try:
        s = json.load(open(os.path.expanduser('~/.claude/settings.json')))
        model = s.get('model', 'unknown')
    except: model = 'unknown'
print(model)
" 2>/dev/null
```

Se o output **não contém** `sonnet`: avise em 1 linha e mostre o comando abaixo sem executar — o usuário pode copiar e iniciar uma sessão Sonnet diretamente:

```
claude --model claude-sonnet-4-6
```

> Não bloqueie a execução. Este comando já tem `model: sonnet` no frontmatter. O aviso é sobre o custo da sessão pai.

---

Você vai executar uma mudança pequena/média de ponta a ponta usando o pipeline gstack. A descrição da mudança é:

**$ARGUMENTS**

## Regras de execução

1. **Não pare para perguntar** a menos que o pedido seja genuinamente ambíguo (múltiplas interpretações incompatíveis). Em caso de dúvida menor, tome a decisão razoável e siga.
2. **Auto-fix em falhas:** se `/review` ou `/qa` acharem problemas, corrija automaticamente e re-rode a etapa até passar (máx 3 tentativas por etapa; se exceder, pare e reporte).
3. **Não pule etapas.** A ordem importa para evitar retrabalho.
4. **Todo o desenvolvimento acontece numa worktree isolada** (ver abaixo) — nunca edite o working tree principal.

## Integração graphify (busca/exploração)

As skills do gstack não usam graphify sozinhas — você é responsável por isso:

- **Exploração:** quando precisar entender o código antes de mudar, se `graphify-out/graph.json` existe, **prefira `graphify query "<pergunta>"`** (subgrafo escopado) a grep/leitura ampla. Se não existe e o repo é grande, ofereça bootstrapar com `/herow-extras:graphify-install` (1 vez por repo).
- **Após implementar:** rode `graphify update .` (AST-only, sem custo de API) na worktree para manter o grafo coerente com o código novo.

## Isolamento em worktree (obrigatório)

A implementação, `/review`, `/qa` e `/ship` rodam todos numa **git worktree dedicada** em `.claude/worktree/<slug>`, nunca no working tree principal.

1. **Branch base = branch atual do repositório.** Capture-a antes de tudo: `git rev-parse --abbrev-ref HEAD`. É contra ela que o PR será aberto. **Se a base for ambígua** (HEAD destacado, ou `git rev-parse` não retornar uma branch nomeada), use `AskUserQuestion` para confirmar a branch base — ofereça a detectada/`main` como opção recomendada.
2. **Slug + tipo (Conventional Commits).** Slug kebab-case da descrição (máx 40 chars). `<tipo>` inferido da descrição: `feat` (nova funcionalidade), `fix` (correção), `refactor`, `chore`, `docs`.
3. **Garanta `.claude/worktree/` no `.gitignore`** do repo (adicione a linha se faltar) — a worktree não é versionada.
4. **Crie a worktree:** `git worktree add .claude/worktree/<slug> -b <tipo>/<slug> <branch-base>`. Se a worktree ou a branch já existem, **pare** e avise — pode haver outra execução em andamento.
5. **`cd` para `.claude/worktree/<slug>`** e faça toda a implementação lá dentro.

## Sequência obrigatória

1. **Planejamento rápido** — invoque `/autoplan` com a descrição acima (pode rodar no tree principal). Surfacie apenas decisões críticas (não me pergunte coisas óbvias).
2. **Worktree** — execute o "Isolamento em worktree" acima e entre na worktree.
3. **Implementação** — execute o plano. Use graphify para explorar (ver acima) e o subagent apropriado (`fullstack-developer`, `python-pro`, `mobile-developer`, etc.) conforme a stack tocada. Ao terminar, rode `graphify update .`.
4. **Review** — rode `/review`. Aplique auto-fixes. Re-rode até zero findings críticos.
5. **QA** — rode `/qa` apontando para o ambiente local/staging detectado. Corrija bugs encontrados. Re-rode até passar.
6. **Ship** — rode `/ship` para abrir o PR **contra a branch base** capturada no passo 1 do isolamento.
7. **Limpeza da worktree** — só depois do PR aberto: volte ao repo raiz (`cd`) e `git worktree remove .claude/worktree/<slug>` (a branch permanece no PR). Se a remoção falhar, reporte e deixe a worktree intacta — não force às cegas.

## Output final

Reporte em até 6 linhas: o que foi feito, branch (`<tipo>/<slug>`, base), link do PR, qualquer pendência conhecida, e o status das etapas gstack em 1 linha — `autoplan / review / qa / ship`, cada uma marcada ✅ executada, ⬜ pulada (com motivo) ou ❌ falhou.
