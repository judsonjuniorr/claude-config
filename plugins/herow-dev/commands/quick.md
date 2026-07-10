---
description: (herow) Pipeline gstack ponta-a-ponta para mudança simples (worktree → autoplan → implementar → review → qa → ship)
argument-hint: <descrição curta da mudança>
effort: medium
---

## Model check (contexto 1M)

O blocker real não é o *tier* (Sonnet vs Opus) e sim o **contexto 1M**: o toggle de 1M é global da sessão e herdado por comandos/subagents. Este comando **não fixa modelo** — herda o modelo padrão da sessão; numa sessão 1M ele roda como `<modelo>[1m]` e falha com `API Error: Usage credits required for 1M context` se não houver créditos. Detecte isso pelo sufixo `[1m]`:

```bash
python3 -c "
import json, os
model = os.environ.get('CLAUDE_MODEL', '')
if not model:
    try:
        s = json.load(open(os.path.expanduser('~/.claude/settings.json')))
        model = s.get('model') or ''
    except: model = ''
print(model)
" 2>/dev/null
```

- Se o output **termina em `[1m]`** (ex.: `claude-sonnet-4-6[1m]`): a sessão está em contexto 1M (cobrado). Avise em 1 linha que esta invocação herda 1M e vai falhar por falta de créditos, e ofereça os dois caminhos:
  - **Trocar para contexto padrão** (recomendado p/ este comando — roda sem créditos): `/model` → escolha um modelo **não-`[1m]`**, ou reinicie já executando a tarefa (substitua `<descrição>` pelo argumento real resolvido acima):

    ```
    claude --model claude-sonnet-4-6 "/herow-dev:quick <descrição>"
    ```
  - **Manter 1M** (só se o trabalho exige Opus + 1M de propósito): rode `/usage-credits` para ligar os créditos.
- Se o output for **vazio/indeterminado**: **não avise** (fail open — o check é só advisory; a maioria das sessões corretas cai aqui).
- Caso contrário (modelo de contexto padrão): siga sem avisar.

> Não bloqueie em nenhum caso. Este comando não fixa modelo no frontmatter — herda o modelo padrão da sessão; em contexto padrão roda normalmente. O aviso acima só importa quando a sessão está em 1M.

---

Você vai executar uma mudança pequena/média de ponta a ponta usando o pipeline gstack. A descrição da mudança é:

**$ARGUMENTS**

## Regras de execução

1. **Não pare para perguntar** a menos que o pedido seja genuinamente ambíguo (múltiplas interpretações incompatíveis). Em caso de dúvida menor, tome a decisão razoável e siga.
2. **Auto-fix em falhas:** se `/review` ou `/qa` acharem problemas, corrija automaticamente e re-rode a etapa até passar (máx 3 tentativas por etapa; se exceder, pare e reporte).
3. **Não pule etapas.** A ordem importa para evitar retrabalho.
4. **Todo o desenvolvimento acontece numa worktree isolada** (ver abaixo) — nunca edite o working tree principal.

## Idioma dos artefatos gerados

All generated code, comments, commit messages, and documentation must be in English, even when the blueprint, questions, or user input are in Portuguese — unless the user explicitly requests otherwise.

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
