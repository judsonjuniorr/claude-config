---
description: (herow) Fase de planejamento completa do gstack — persistência via hook, .claude/plans/<slug>/ local (não commitado)
argument-hint: <descrição da feature/mudança>
effort: medium
---

Você está na fase de **PLANEJAMENTO PURO**. **NÃO escreva código de produção** e **NÃO crie worktree** — o blueprint roda no tree principal e gera apenas um plano no diretório do plano `.claude/plans/<slug>/` (pasta local, gitignored) que referencia os artefatos gerados pelas skills do gstack. O isolamento em worktree (`.claude/worktree`, base = branch atual) acontece depois, no `/herow-dev:execute`.

> **Layout (um diretório por plano):** cada plano vive em `.claude/plans/<slug>/`, contendo `plan.md`, `state.json`, `source.md` (opcional) e uma subpasta `artifacts/` com **todos** os dados que a orquestração deste plano produzir (notas de pesquisa, saídas de subagents, arquivos de rascunho). Nada solto na raiz `.claude/plans/`, nunca em `/tmp`.

Descrição:

**$ARGUMENTS**

## Setup inicial (faça primeiro, em ordem)

1. `mkdir -p .claude/plans`
2. **Garanta que `.claude/plans/` está gitignored (idempotente).** Rode o guard abaixo — ele acrescenta `.claude/plans/` ao excludesfile global do git (só se faltar) e ao `.gitignore` do repo (só se faltar), **mantendo** a linha legada `.plans/`:

   ```bash
   GI="$(git config --global core.excludesfile)"; GI="${GI:-$HOME/.gitignore}"
   [ -f "$GI" ] || : > "$GI"
   grep -qxF '.claude/plans/' "$GI" || printf '%s\n' '.claude/plans/' >> "$GI"
   if [ -f .gitignore ] && ! grep -qxF '.claude/plans/' .gitignore; then
     printf '%s\n' '.claude/plans/' >> .gitignore
   fi
   ```
3. Gere o slug do plano: `TS=$(date -u +%Y%m%d-%H%M%S)`, slug kebab-case da descrição (máx 40 chars), `SLUG="${TS}-<slug>"`. Esse `SLUG` é o nome do **diretório** do plano.
4. **Reivindique o diretório do plano como claim de unicidade atômico** — `mkdir` **sem** `-p`:

   ```bash
   until mkdir ".claude/plans/$SLUG" 2>/dev/null; do SLUG="${SLUG}-2"; done
   mkdir -p ".claude/plans/$SLUG/artifacts"
   ```
   `mkdir` é atômico no filesystem: se o diretório já existe (colisão de mesmo segundo + mesmo slug em sessões paralelas), o loop escolhe um novo sufixo. **Nunca** use `mkdir -p` para o claim.
5. **Ative o tracker do harness (marcador com escopo de sessão):**

   ```bash
   echo "$SLUG" > ".claude/plans/.active-$CLAUDE_SESSION_ID"
   ```
   O marcador é vinculado à **sua** sessão (`$CLAUDE_SESSION_ID`), então blueprints paralelos no mesmo repo **não colidem** e o hook nunca registra skills de outra sessão neste plano. A partir daqui, o hook `PostToolUse:Skill` do plugin herow-dev (`blueprint-track.sh`) registra automaticamente em `.claude/plans/$SLUG/state.json` cada skill executada; artefatos são detectados por diff de mtimes **dentro de `.claude/plans/$SLUG/artifacts/`** — escreva ali qualquer saída de orquestração que queira rastrear. Você **não** precisa fazer snapshots manuais.
6. **Não crie `plan.md` agora.** O `plan.md` é escrito uma única vez na consolidação final — sua ausência marca um plano ainda em andamento, então um blueprint abortado nunca é resolvido pelo `/herow-dev:execute`.

## Idioma dos artefatos gerados

All generated code, comments, commit messages, and documentation must be in English, even when the blueprint, questions, or user input are in Portuguese — unless the user explicitly requests otherwise.

## Sequência obrigatória das skills

Apenas execute na ordem — o hook cuida da persistência:

1. **`/office-hours`** — design doc inicial
2. **`/plan-ceo-review`** — desafio estratégico
3. **`/plan-eng-review`** — arquitetura, dados, testes, edge cases
4. **Se tocar UI:** `/plan-design-review`
5. **Se tocar API/SDK/docs:** `/plan-devex-review`
6. **Opcional:** `/spec` — refina em spec executável

## Consolidação final

A ordem importa — o tracker (`.claude/plans/.active-$CLAUDE_SESSION_ID`) fica ativo até o passo 7, para que skills disparadas no passo 4 também sejam registradas.

1. **Leia o state.json:** `cat .claude/plans/$SLUG/state.json` — contém lista de skills executadas (`skills[].skill`, já normalizado sem namespace/barra inicial: ex. `office-hours`) e artefatos detectados.
   - **Se o state.json não existir** (hook não registrado ou falhou): avise explicitamente, monte a seção "Artefatos do gstack" manualmente a partir dos outputs que você observou cada skill produzir, e marque como ✅ no checklist abaixo as etapas que você sabe que rodaram nesta sessão.
2. **Checklist de cobertura (sempre exiba ao usuário):** compare o state.json com a lista canônica e mostre cada etapa com um destes estados:
   - ✅ executada — presente no state.json
   - ⬜ não executada — aplicável, mas não rodou
   - ➖ não aplicável — condição não se aplica (ex.: `/plan-design-review` sem UI, `/plan-devex-review` sem API/SDK/docs) — inclua o motivo em 1 linha

   Lista canônica: `office-hours`, `plan-ceo-review`, `plan-eng-review`, `plan-design-review` (condicional UI), `plan-devex-review` (condicional API/SDK/docs), `spec` (opcional).
3. **Ofereça disparar as etapas faltantes** — `AskUserQuestion` com `multiSelect: true`:
   - Uma opção por etapa não executada (inclua as ➖ também, rotuladas como "não aplicável"), com descrição de 1 linha do que a skill agrega.
   - Se só **uma** etapa estiver faltando, adicione uma segunda opção "Nenhuma — finalizar o plano" (a pergunta exige ≥2 opções).
   - Se **zero** etapas estiverem faltando, pule a pergunta.
4. **Execute as skills selecionadas** (o tracker continua ativo, então entram no mesmo state.json) e **releia o state.json**.
5. Use a lista final de artefatos pra preencher a seção "Artefatos do gstack" do plano (caminhos + papel de cada um). Se houve material de origem, grave-o em `.claude/plans/$SLUG/source.md`.
6. **Escreva o plano** em `.claude/plans/$SLUG/plan.md` (uma única vez — é o que marca o plano como pronto para o `/herow-dev:execute`). **Não** existe mais `latest.txt`: o `/herow-dev:execute` resolve o plano mais recente pelo diretório e você imprime o comando exato no reporte final.
7. **Desative o tracker e limpe os snapshots:** `rm -f ".claude/plans/.active-$CLAUDE_SESSION_ID"` e `rm -rf ".claude/plans/$SLUG/.snap"` (importante — senão skills futuras desta sessão continuariam sendo registradas neste plano).

## Formato obrigatório do `.claude/plans/$SLUG/plan.md`

```markdown
# PLAN: <título curto>

> **Slug:** <SLUG>
> **Dir:** `.claude/plans/<SLUG>/`
> **Criado:** <ISO>
> **State:** `.claude/plans/<SLUG>/state.json`
> **Branch alvo:** <tipo>/<slug> — `<tipo>` inferido do objetivo, Conventional Commits: feat | fix | refactor | chore | docs (mesma regra do `/herow-dev:execute`)

## Objetivo
<1-2 frases.>

## Escopo
- Inclui: <lista>
- NÃO inclui: <lista>

## Artefatos do gstack (LEITURA OBRIGATÓRIA antes de implementar)
O hook detecta automaticamente **apenas** arquivos gravados em `.claude/plans/<SLUG>/artifacts/` (registrados em `state.json`). Saídas das skills do gstack que vão para fora do diretório do plano (ex.: `~/.gstack/...`) **não** são detectadas — liste-as manualmente a partir do que cada skill gerou nesta sessão:

- `<path>` — gerado por `/office-hours` — <papel>
- `<path>` — gerado por `/plan-ceo-review` — <papel>
- ...

> Estes arquivos NÃO estão no git (`.claude/plans/` e pastas de output do gstack costumam ser locais). Se o `/herow-dev:execute` rodar em outra máquina, caia no resumo abaixo.

## Resumo executável (fallback)
<3-5 bullets capturando o essencial das decisões dos artefatos>

## Arquivos de código a tocar
- `path/to/file1.ts` — <o que muda>

## Passos de implementação
1. **<passo>** — <o que fazer>
   - **Verificação:** <comando executável>

## Critério de aceite global
- [ ] <observável>

## Riscos e decisões
- <risco> → <mitigação>

## Subagent recomendado
<fullstack-developer | python-pro | ...>
```

## Reporte final

- Diretório do plano: `.claude/plans/<SLUG>/`
- Plano: `.claude/plans/<SLUG>/plan.md` · State: `.claude/plans/<SLUG>/state.json`
- Checklist de cobertura das etapas gstack (✅/⬜/➖, o mesmo da consolidação, já refletindo as etapas extras disparadas)
- Próximo comando (imprima o caminho exato): `/herow-dev:execute .claude/plans/<SLUG>/` — isola em `.claude/worktree/<slug>` baseado na branch atual
