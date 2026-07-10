---
description: (herow) Executa um plano de .claude/plans/<slug>/ em uma worktree isolada — implementa, revisa, testa, commita/pusha e abre o PR
argument-hint: [caminho ou slug do plano — default: plano mais recente em .claude/plans/]
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
  - **Trocar para contexto padrão** (recomendado p/ este comando — roda sem créditos): `/model` → escolha um modelo **não-`[1m]`**, ou reinicie já executando o plano (substitua `<plano>` pelo argumento real resolvido acima):

    ```
    claude --model claude-sonnet-4-6 "/herow-dev:execute <plano>"
    ```
  - **Manter 1M** (só se o trabalho exige Opus + 1M de propósito): rode `/usage-credits` para ligar os créditos.
- Se o output for **vazio/indeterminado**: **não avise** (fail open — o check é só advisory; a maioria das sessões corretas cai aqui).
- Caso contrário (modelo de contexto padrão): siga sem avisar.

> Não bloqueie em nenhum caso. Este comando não fixa modelo no frontmatter — herda o modelo padrão da sessão; em contexto padrão roda normalmente. O aviso acima só importa quando a sessão está em 1M.

---

Você vai **executar** um plano já definido. Caminho/slug (vazio = resolva o plano mais recente, ver abaixo):

**$ARGUMENTS**

Roda no modelo padrão da sessão. Trate o plano como contrato: não invente escopo, não refatore além do listado.

## Resolução do caminho

O layout atual é **um diretório por plano**: `.claude/plans/<slug>/` com `plan.md`, `state.json`, `source.md` (opcional) e `artifacts/`. Resolva nesta ordem:

1. **Argumento explícito.** Se foi passado um argumento:
   - se for um diretório (`.claude/plans/<slug>/` ou `.claude/plans/<slug>`), o plano é `<dir>/plan.md`;
   - se for um slug simples, resolva para `.claude/plans/<slug>/plan.md`;
   - se for um caminho de arquivo, use-o literalmente.
2. **Sem argumento — plano mais recente:** liste os diretórios `.claude/plans/*/` que **contêm `plan.md`** (diretórios sem `plan.md` são blueprints em andamento — ignore) e escolha o de nome mais recente (o nome começa com o timestamp UTC, então ordenação por nome = ordem cronológica). Se houver mais de um candidato recente e ambíguo, **confirme com o usuário** (`AskUserQuestion`) antes de seguir.
3. **Fallback legado (somente leitura).** Se nada foi encontrado em `.claude/plans/`, procure o layout flat antigo em `.plans/`: use `.plans/latest.txt` se existir, senão o `.plans/*.md` mais recente por mtime **excluindo `*.source.md` e `*.state.json`**. Outros repos migram sob demanda; **planos novos são sempre gravados no layout novo** — nunca escreva de volta em `.plans/`.
4. Se nem o layout novo nem o legado tiverem um plano, **pare** e avise: "Nenhum plano encontrado. Rode `/herow-dev:blueprint` primeiro."
5. **Carregue o state.json correspondente:** `.claude/plans/<slug>/state.json` (layout novo) ou `.plans/<ID>.state.json` (fallback legado) — contém o registro (gerado pelo hook) de quais skills rodaram e quais artefatos cada uma criou. **Se não existir, não pare:** avise em 1 linha e siga usando o "Resumo executável" do plano como fonte.
6. Mostre em 1 linha qual plano + state foi escolhido antes de seguir.
7. **Mostre o checklist de cobertura do blueprint** (se o state.json existe): compare `skills[].skill` com a lista canônica — `office-hours`, `plan-ceo-review`, `plan-eng-review`, `plan-design-review` (condicional UI), `plan-devex-review` (condicional API/SDK/docs), `spec` (opcional) — e exiba cada etapa como ✅ executada / ⬜ não executada / ➖ não aplicável. **Apenas exibição**, sem perguntar nada: lacunas de review já foram oferecidas interativamente no `/herow-dev:blueprint`; aqui servem só pra deixar visível a cobertura do plano antes de implementar.

## Idioma dos artefatos gerados

All generated code, comments, commit messages, and documentation must be in English, even when the blueprint, questions, or user input are in Portuguese — unless the user explicitly requests otherwise.

## Integração graphify (busca/exploração)

As skills do gstack não usam graphify sozinhas — você é responsável por isso:

- **Exploração:** ao ler os arquivos de código a tocar, se `graphify-out/graph.json` existe na worktree, **prefira `graphify query "<pergunta>"`** e `graphify path "<A>" "<B>"` a grep amplo. Se não existe e o repo é grande, ofereça `/herow-extras:graphify-install`.
- **Após implementar (antes do gate de validação):** rode `graphify update .` na worktree para manter o grafo coerente.

## Isolamento em worktree (obrigatório)

Todo o desenvolvimento acontece numa **git worktree dedicada**, nunca no working tree principal.

1. **Branch base = branch atual do repositório.** Capture-a antes de tudo: `git rev-parse --abbrev-ref HEAD`. É contra ela que o PR será aberto no final. **Se a base for ambígua** (HEAD destacado, ou `git rev-parse` não retornar uma branch nomeada), use `AskUserQuestion` para confirmar a branch base — ofereça a detectada/`main` como opção recomendada.
2. **Defina o slug e o tipo** seguindo Conventional Commits:
   - O slug vem do **nome do diretório do plano** (`.claude/plans/<SLUG>/`), removendo o prefixo de timestamp `YYYYMMDD-HHMMSS-`. No fallback legado (`.plans/<ID>.md`), vem do nome do arquivo.
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
