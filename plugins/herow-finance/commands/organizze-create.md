---
description: (herow) Cria lançamentos no Organizze (conta, cartão, fatura, transferência) com dry-run + confirmação + verificação.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: "[<texto livre: 'gastei 50 no mercado ontem'> | --conta X --cartao Y --fatura Z --parcelas N --recorrente --transferencia]"
effort: medium
---

# /finance:organizze-create — criar lançamento no Organizze

> **REGRA GLOBAL — perguntas ao usuário:** toda pergunta que exige resposta do usuário deve ser feita via `AskUserQuestion`, com 2-4 opções estruturadas (o campo livre "Other" é automático). **Nunca** pergunte inline no texto.

> **Spine de segurança (escrita de dinheiro real):** DRY-RUN é o padrão. Nenhum POST acontece sem `--apply`, e `--apply` só é passado **depois** de uma confirmação Apply/Cancel via `AskUserQuestion`. Toda criação é verificada por read-back.

Este é o **primeiro caminho de escrita** da integração Organizze (o resto é leitura). O comando faz o parse de linguagem natural + perguntas; o script `create.py` é não-interativo e faz resolução por id + payload + POST + verify.

`SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/organizze/create.py"`

## Protocolo do script (como ler a saída)
- **stderr:** `info|<estado>|...` (auth/resolve/category/duplicate/dry-run/payload/apply/verify), `err|<código>|<detalhe>`.
- **stdout:** `ok|created|<id>` ou `ok|transfer|<id>` — só num `--apply` que gravou de verdade.
- O token **nunca** aparece (mascarado `org…xxx`).

## Passos (siga exatamente, não pule)

### 1. First-run / auth
Se `~/finance/organizze/.auth` não existir, **não** rode o script: é o mesmo `.auth` do `/finance:organizze` (escopo leitura+escrita — sem nova credencial). **Leia `${CLAUDE_PLUGIN_ROOT}/resources/organizze-onboarding.md` e siga §Step 2 (token setup)** para criar o `.auth`. Pare aqui até existir o `.auth`.

### 2. Intent parse (linguagem natural → flags)
Do `$ARGUMENTS`, extraia o que der: descrição, valor, sinal (gastei/paguei → `--despesa`; recebi/ganhei → `--receita`), data relativa (ontem/hoje/"dia X"), alvo (no cartão X → `--cartao`; transferência de A para B → `--transferencia --de A --para B`), parcelas ("3x" → `--parcelas 3`), recorrência ("todo mês"/"fixo" → `--recorrente`). O que **não** der para inferir com confiança vira pergunta no passo 3 — nunca chute valor, conta ou sinal.

### 3. Preencher lacunas via AskUserQuestion
Para cada campo essencial ausente ou ambíguo (alvo conta/cartão, valor, sinal receita/despesa, data), pergunte via `AskUserQuestion` com 2-4 opções. Se o script devolver `err|resolve|<hint>` (nome de conta/cartão não encontrado ou ambíguo) ou `err|invoice-unresolved|<cartão>`, **transforme em AskUserQuestion** com a lista — nunca um beco sem saída.

**Pago vs. pendente:** para lançamento com data **passada ou de hoje**, pergunte "já está paga?" via `AskUserQuestion` (Sim → `--paga`, Não → `--nao-paga`). Para data **futura**, o padrão é pendente (não pergunte). Sem flag, o script infere pela data (passado/hoje = paga, futuro = pendente).

### 4. DRY-RUN (sempre primeiro)

> **SEGURANÇA — texto livre nunca vai pra linha de comando.** Descrição e nota podem conter `` ` ``, `$(...)`, `;`, aspas (ex.: texto colado de recibo). **Nunca** interpole esses campos direto no Bash. Use a tool **Write** para criar um arquivo JSON temporário e passe `--input-file`:
> ```json
> // /tmp/org-create.json — escrito via Write tool, não pelo shell
> { "description": "<texto livre do usuário>", "notes": "<nota opcional>" }
> ```
> Só os campos **estruturados** (valor, conta, data, sinal) vão como flags — o argparse os type-coage.

Rode o script **sem** `--apply` com as flags resolvidas + o `--input-file`:
```bash
python3 "$SCRIPT" --input-file /tmp/org-create.json --conta "<conta>" --despesa --valor <v> --data <YYYY-MM-DD> --categoria "<cat>"
```
Leia o `info|resolve|...`, `info|category|...`, `info|dry-run|...` e `info|payload|...`. Se aparecer `info|installments|...` (semântica do valor parcelado não verificada) ou `[APROXIMADA]` na resolução de fatura, **destaque ao usuário**. Renderize um **resumo humano** do alvo resolvido por extenso (ex.: "Nubank → fatura de julho", não "card 3 invoice 189") + valor + categoria. **Não** despeje JSON cru por padrão (ofereça o payload mascarado só se pedirem).

> **Transferência:** `--de` é a conta de **origem** (de onde sai) e `--para` o **destino** (onde entra) — o script mapeia para `credit_account_id`/`debit_account_id` na direção certa da API. Confirme as duas contas no resumo antes do Apply.

### 5. Aviso de duplicata
Se aparecer `info|duplicate|...`, mostre o lançamento existente que casou (id/data/valor) **antes** do confirm, para o usuário decidir se é repetição.

### 6. Confirmação Apply / Cancel
Pergunte via `AskUserQuestion`: **Apply** (criar) ou **Cancel**. Só em **Apply** rode com `--apply` (e `--force` se o usuário confirmou criar mesmo havendo duplicata):
```bash
python3 "$SCRIPT" --apply [--force] <mesmas flags do dry-run>
```

### 7. Verificação + linha de sucesso
- Em sucesso, o script imprime `ok|created|<id>` (ou `ok|transfer|<id>`) e um `info|verify|ok id <id>`.
- Renderize a linha rica ao usuário:
  `✅ Criado: <descrição> R$ <valor> em <conta | cartão→fatura mês> [categoria] — id <id>`
- Se vier `err|verify|...` (gravou mas o read-back não bateu), mostre um **aviso alto** — não declare "ok" silencioso.

## Mapa de erros (renderize problema + causa + correção)
- `err|no-auth|...` → "Sem credencial. Configure o token: `resources/organizze-onboarding.md` §Step 2."
- `err|bad-auth|missing <k>` → "Arquivo `.auth` incompleto (falta `<k>`). Refaça o token: `resources/organizze-onboarding.md` §Step 2."
- `err|duplicate|...` → "Já existe lançamento igual recente (mostrado acima). Confirme criar mesmo assim → re-rode com `--force`, ou cancele."
- `err|http-401|...` → "Token recusado. Reautentique (apague `~/finance/organizze/.auth` e refaça o setup)."
- `err|http-422|<body>` → mostre a mensagem do Organizze + o campo; ofereça reabrir o campo via AskUserQuestion.
- `err|resolve|<hint>` → "Não achei conta/cartão '<hint>'." + AskUserQuestion com a lista.
- `err|invoice-unresolved|<cartão>` → "Não consegui mapear a fatura para essa data." + AskUserQuestion com as faturas.
- `err|validation|amount` → "Valor não pode ser 0."
- `err|validation|installments-recurrence` → "Parcelamento e recorrência são mutuamente exclusivos — escolha um."
- `err|validation|transfer-card` → "Transferência é só entre contas bancárias, não cartão."
- `err|validation|periodicity` → "Periodicidade inválida. Use: monthly, yearly, weekly, biweekly, bimonthly, trimonthly."
- `err|input-file|...` → "Falha ao ler o JSON de texto livre; reescreva o arquivo via Write tool."
- `err|network|...` → falha de rede; tente de novo, sem retry cego.

## Regras
- DRY-RUN é o padrão e é **sempre** mostrado antes de qualquer escrita.
- `--apply` é o único caminho que grava, e só depois do Apply confirmado.
- Toda pergunta via `AskUserQuestion`. Mensagens ao usuário em português; linhas de protocolo (`info|`/`ok|`/`err|`) ficam em inglês de máquina.
- Não pré-inspecione (sem `git status`/listar diretórios) — o script é self-contained.
