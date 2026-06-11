---
description: (herow) Fase de planejamento completa do gstack — persistência via hook, .plans/ local (não commitado)
argument-hint: <descrição da feature/mudança>
---

Você está na fase de **PLANEJAMENTO PURO**. **NÃO escreva código de produção** e **NÃO crie worktree** — o blueprint roda no tree principal e gera apenas um plano em `.plans/` (pasta local, gitignored) que referencia os artefatos gerados pelas skills do gstack. O isolamento em worktree (`.claude/worktree`, base = branch atual) acontece depois, no `/herow-dev:execute`.

Descrição:

**$ARGUMENTS**

## Setup inicial (faça primeiro, em ordem)

1. `mkdir -p .plans`
2. **Garanta que `.plans/` está no `.gitignore`** do repo (adicione a linha se faltar) — a pasta é local, nunca versionada.
3. Gere ID: `TS=$(date -u +%Y%m%d-%H%M%S)`, slug kebab-case da descrição (máx 40 chars), `ID="${TS}-${SLUG}"`.
4. **Guard de colisão do tracker:** se `.plans/.active` já existe, **não sobrescreva**. Leia o ID que está nele e decida com o usuário (`AskUserQuestion`): se for resto de um blueprint abortado, limpe (`rm .plans/.active`) e siga; se outro blueprint pode estar em andamento nesta máquina, **aborte** — sobrescrever contaminaria o state do outro plano.
5. **Ative o tracker do harness:** `echo "$ID" > .plans/.active`
   - A partir daqui, o hook `PostToolUse:Skill` do plugin herow-dev (`blueprint-track.sh`) registra automaticamente em `.plans/$ID.state.json` cada skill executada + artefatos detectados via diff de mtimes. Você **não** precisa fazer snapshots manuais.
6. Crie o arquivo de plano vazio: `.plans/$ID.md` (será preenchido ao final).

> O ponteiro `.plans/latest.txt` só é atualizado na consolidação final, depois do plano preenchido — assim um blueprint abortado nunca deixa o `/herow-dev:execute` apontando para um plano vazio.

## Sequência obrigatória das skills

Apenas execute na ordem — o hook cuida da persistência:

1. **`/office-hours`** — design doc inicial
2. **`/plan-ceo-review`** — desafio estratégico
3. **`/plan-eng-review`** — arquitetura, dados, testes, edge cases
4. **Se tocar UI:** `/plan-design-review`
5. **Se tocar API/SDK/docs:** `/plan-devex-review`
6. **Opcional:** `/spec` — refina em spec executável

## Consolidação final

A ordem importa — o tracker (`.plans/.active`) fica ativo até o passo 7, para que skills disparadas no passo 4 também sejam registradas.

1. **Leia o state.json:** `cat .plans/$ID.state.json` — contém lista de skills executadas (`skills[].skill`, sem a barra inicial: ex. `office-hours`) e artefatos detectados.
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
5. Use a lista final de artefatos pra preencher a seção "Artefatos do gstack" do plano (caminhos + papel de cada um).
6. **Escreva o plano** `.plans/$ID.md` e só então atualize o ponteiro: `echo ".plans/$ID.md" > .plans/latest.txt`
7. **Desative o tracker:** `rm .plans/.active` (importante — senão skills futuras continuarão sendo registradas neste plano).

## Formato obrigatório do `.plans/$ID.md`

```markdown
# PLAN: <título curto>

> **ID:** <ID>
> **Criado:** <ISO>
> **State:** `.plans/<ID>.state.json`
> **Branch alvo:** <tipo>/<slug> — `<tipo>` inferido do objetivo, Conventional Commits: feat | fix | refactor | chore | docs (mesma regra do `/herow-dev:execute`)

## Objetivo
<1-2 frases.>

## Escopo
- Inclui: <lista>
- NÃO inclui: <lista>

## Artefatos do gstack (LEITURA OBRIGATÓRIA antes de implementar)
Detectados automaticamente pelo hook a partir de `.plans/<ID>.state.json`:

- `<path>` — gerado por `/office-hours` — <papel>
- `<path>` — gerado por `/plan-ceo-review` — <papel>
- ...

> Estes arquivos NÃO estão no git (`.plans/` e pastas de output do gstack costumam ser locais). Se o `/herow-dev:execute` rodar em outra máquina, caia no resumo abaixo.

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

- Caminho do plano: `.plans/<ID>.md`
- State: `.plans/<ID>.state.json`
- Checklist de cobertura das etapas gstack (✅/⬜/➖, o mesmo da consolidação, já refletindo as etapas extras disparadas)
- Próximo comando: `/herow-dev:execute` (usa `.plans/latest.txt` automaticamente; isola em `.claude/worktree/<slug>` baseado na branch atual)
