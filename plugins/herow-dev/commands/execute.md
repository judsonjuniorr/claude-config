---
description: (herow) Executa um plano de .plans/ em uma worktree isolada — implementa, revisa, testa, commita/pusha e abre o PR
argument-hint: [caminho do plano — default .plans/latest]
model: sonnet
---

## Model check

```bash
python3 -c "
import json, os
model = os.environ.get('CLAUDE_MODEL', '')
if not model:
    try:
        s = json.load(open(os.path.expanduser('~/.claude/settings.json')))
        model = s.get('model', 'unknown')
    except: model = 'unknown'
print(model)
" 2>/dev/null
```

Se o output **não contém** `sonnet` e **não é** `opusplan`: avise em 1 linha que a sessão está em Opus e mostre o comando exato para reiniciar em Sonnet diretamente. Construa o comando substituindo `<plano>` pelo argumento real desta invocação (já resolvido acima):

```
claude --model claude-sonnet-4-6 "/herow-dev:execute <plano>"
```

O usuário copia, roda no terminal e o comando inicia uma nova sessão Sonnet já executando o plano.

> Não bloqueie. Este comando tem `model: sonnet` no frontmatter — esta invocação roda em Sonnet independente. O aviso é custo da sessão pai.

---

Você vai **executar** um plano já definido. Caminho:

**${ARGUMENTS:-.plans/latest}**

Pensado pra rodar em Sonnet (mais barato). Trate o plano como contrato: não invente escopo, não refatore além do listado.

## Resolução do caminho

1. Se foi passado argumento, use-o literalmente.
2. Se não foi passado:
   - Se `.plans/latest.txt` existe, leia o caminho dele.
   - Senão, liste `.plans/*.md` ordenado por mtime e use o mais recente.
   - Se `.plans/` não existe ou está vazio, **pare** e avise: "Nenhum plano encontrado. Rode `/herow-dev:blueprint` primeiro."
3. Carregue também o `.plans/<ID>.state.json` correspondente — contém o registro completo (gerado pelo hook) de quais skills rodaram e quais artefatos cada uma criou. **Se não existir, não pare:** avise em 1 linha e siga usando o "Resumo executável" do plano como fonte (mesmo fallback do passo 2 da sequência).
4. Mostre em 1 linha qual plano + state foi escolhido antes de seguir.
5. **Mostre o checklist de cobertura do blueprint** (se o state.json existe): compare `skills[].skill` com a lista canônica — `office-hours`, `plan-ceo-review`, `plan-eng-review`, `plan-design-review` (condicional UI), `plan-devex-review` (condicional API/SDK/docs), `spec` (opcional) — e exiba cada etapa como ✅ executada / ⬜ não executada / ➖ não aplicável. **Apenas exibição**, sem perguntar nada: lacunas de review já foram oferecidas interativamente no `/herow-dev:blueprint`; aqui servem só pra deixar visível a cobertura do plano antes de implementar.

## Integração graphify (busca/exploração)

As skills do gstack não usam graphify sozinhas — você é responsável por isso:

- **Exploração:** ao ler os arquivos de código a tocar, se `graphify-out/graph.json` existe na worktree, **prefira `graphify query "<pergunta>"`** e `graphify path "<A>" "<B>"` a grep amplo. Se não existe e o repo é grande, ofereça `/herow-extras:graphify-install`.
- **Após implementar (antes do gate de validação):** rode `graphify update .` na worktree para manter o grafo coerente.

## Isolamento em worktree (obrigatório)

Todo o desenvolvimento acontece numa **git worktree dedicada**, nunca no working tree principal.

1. **Branch base = branch atual do repositório.** Capture-a antes de tudo: `git rev-parse --abbrev-ref HEAD`. É contra ela que o PR será aberto no final. **Se a base for ambígua** (HEAD destacado, ou `git rev-parse` não retornar uma branch nomeada), use `AskUserQuestion` para confirmar a branch base — ofereça a detectada/`main` como opção recomendada.
2. **Defina o slug e o tipo** seguindo Conventional Commits:
   - O slug vem do nome do arquivo do plano.
   - O `<tipo>` é inferido do conteúdo do plano: `feat` (nova funcionalidade), `fix` (correção de bug), `refactor` (reestruturação sem mudança de comportamento), `chore` (manutenção/config), `docs` (documentação). Na dúvida entre dois, use o que melhor descreve o objetivo principal.
   - Ex: plano `dark-mode-eager-quilt` (nova feature) → tipo `feat`, branch `feat/dark-mode-eager-quilt`.
3. **Garanta que `.claude/worktree/` está no `.gitignore`** do repo (adicione a linha se faltar) — a worktree não deve ser versionada.
4. **Crie a worktree** em `.claude/worktree/<slug>` com uma branch nova baseada na branch atual:
   `git worktree add .claude/worktree/<slug> -b <tipo>/<slug> <branch-base>`
   - O `<slug>` do diretório é o mesmo slug do plano.
   - Se a worktree ou a branch já existem, **pare** e avise — outra execução pode estar em andamento.
5. **`cd` para `.claude/worktree/<slug>`** e faça toda a implementação, `/review` e `/qa` lá dentro.

Isso garante que execuções concorrentes nunca pisem no mesmo working tree e que a base do PR seja sempre a branch onde o `/herow-dev:execute` foi disparado.

## Sequência obrigatória

1. **Ler o plano** completo.
2. **Ler os artefatos do gstack referenciados** na seção "Artefatos do gstack" do plano (design doc, CEO/eng/design/devex reviews). Estes contêm o raciocínio completo por trás das decisões — não pule. Se algum não existir mais, use o "Resumo executável" do plano como fallback e siga.
3. **Confirmar entendimento em 3 linhas** (objetivo + nº de passos + subagent recomendado). Sem pedir aprovação.
4. **Implementar passo a passo:**
   - Para cada passo, execute a mudança e rode a **verificação** do passo.
   - Se falhar: corrija e re-rode (máx 3 tentativas). Se exceder, pare e reporte qual passo travou.
   - Use o subagent indicado no plano para a stack específica. Explore com graphify (ver acima).
   - Ao terminar a implementação, rode `graphify update .` na worktree.
5. **`/review`** — aplique auto-fixes. Máx 3 ciclos até zero findings críticos.
6. **`/qa`** — contra ambiente local/staging detectado. Corrija bugs. Máx 3 ciclos.
7. **Gate de validação** (garante que a branch sobe funcional; complementa o `/review` e `/qa`, não os substitui). Rode nesta ordem, **na worktree**, detectando os comandos pelo `package.json`/config da stack (npm/pnpm/yarn, Makefile, etc.):
   - **Lint com auto-fix** — ex.: `eslint --fix`, `biome check --write`, `ruff --fix`. Commite os fixes automáticos.
   - **Type-check** quando disponível — ex.: `tsc --noEmit`, `vue-tsc`, `mypy`.
   - **Tests** — a suíte do projeto (`vitest run`, `jest`, `pytest`, etc.).
   - **Build** — ex.: `next build`, `vite build`, `tsc -b`.
   - Pule de forma explícita (e registre no output) qualquer etapa que o projeto não tenha. Para etapas que existem: corrija e re-rode até passar (máx 3 ciclos por etapa). Se uma etapa continuar falhando, **não abra o PR** — pare e reporte qual etapa travou.
8. **Commit + push + PR** — só se o gate de validação passou inteiro (a partir da worktree, na branch `<tipo>/<slug>`):
   - Commit seguindo Conventional Commits, com push da branch.
   - Abra o PR **contra a branch base** capturada no passo 1 do isolamento.
   - Use o fluxo `github-ops` para commit/push/PR (não pré-inspecione com `git status`/`diff`/`log`).
9. **Limpeza da worktree** — só depois do PR aberto com sucesso:
   - Volte ao working tree principal (`cd` de volta ao repo raiz).
   - `git worktree remove .claude/worktree/<slug>` (use `--force` apenas se necessário; a branch permanece no PR).
   - Se a remoção falhar, reporte e deixe a worktree intacta — não force às cegas.

## Output final

- ✅ Passos completados (X de Y)
- 🌿 Branch: `<tipo>/<slug>` (base: `<branch-base>`)
- 🧪 Gate de validação — lint / type-check / tests / build (passou ou pulado, por etapa)
- 📋 Critérios de aceite — quais passam/falham
- 🔗 **PR aberto:** `<url>`
- 🧹 Worktree `.claude/worktree/<slug>` removida

## Regras

- **Não exceda o escopo** do plano. Anote pendências, siga.
- **Não modifique arquivos fora da lista** "Arquivos a tocar" sem necessidade óbvia.
- **Todo trabalho dentro da worktree** — nunca edite o working tree principal.
- **Não abra o PR com o gate vermelho.** Lint/type-check/tests/build que existem têm de passar; a revisão de código acontece no PR, não localmente.
- **Remova a worktree só depois do PR aberto.** Se algo falhar antes do PR, deixe a worktree para inspeção.
