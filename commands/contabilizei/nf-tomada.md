---
description: (herow) Registra uma NF tomada no Contabilizei a partir de PDF/XML — login headless com código via Gmail, checagem de duplicidade e confirmação antes de enviar.
argument-hint: "<caminho do PDF ou XML da NF>"
allowed-tools: Bash, Read, Write, AskUserQuestion, mcp__playwright-headless__browser_navigate, mcp__playwright-headless__browser_snapshot, mcp__playwright-headless__browser_click, mcp__playwright-headless__browser_type, mcp__playwright-headless__browser_select_option, mcp__playwright-headless__browser_fill_form, mcp__playwright-headless__browser_evaluate, mcp__playwright-headless__browser_wait_for, mcp__playwright-headless__browser_close, mcp__claude_ai_Gmail__search_threads, mcp__claude_ai_Gmail__get_thread
---

# `/contabilizei:nf-tomada`

**Regra global: toda pergunta ao usuário usa `AskUserQuestion` com opções — nunca inline.**

Registra uma NF tomada (nota fiscal de serviço recebida) no Contabilizei a partir de um arquivo PDF ou XML local.

## Passo 0 — Extrair dados da NF

Resolve `$ARGUMENTS` como caminho do arquivo. Se vazio ou não informado, use `AskUserQuestion` para pedir o caminho.

```bash
SCRIPT_DIR="$(cd "$(dirname "$0")/contabilizei-scripts" && pwd)"
bash "$SCRIPT_DIR/setup.sh" >&2
python3 "$SCRIPT_DIR/extract_nf.py" "<caminho>"
```

Leia o JSON retornado. Se houver campos `null` nos campos obrigatórios (`cnpj`, `razao_social`, `data_emissao`, `numero`, `valor`), leia o `.txt` correspondente em `~/finance/contabilizei/extracted/<base>.txt` e complete os campos usando o texto bruto.

**Hard-stop:** se após ler o `.txt` algum campo obrigatório ainda for `null`, pare com erro claro:

> "Não foi possível extrair [campos] da NF. Verifique o arquivo e informe os valores manualmente ou tente outro formato."

Use `AskUserQuestion` para oferecer: corrigir manualmente / abortar.

Ao mostrar os dados extraídos na confirmação (passo 6), **destaque** campos que vieram do `.txt`/regex (fonte frágil) para o usuário revisar.

**Valor:** `parse_valor_br` retorna centavos (int). Formate como `R$ X.XXX,XX` apenas na exibição; passe o valor formatado no formulário.

## Passo 1 — Credenciais (primeira vez)

```bash
CONTABILIZEI_HOME="$HOME/finance/contabilizei"
CONFIG="$CONTABILIZEI_HOME/.config"
```

Se `$CONFIG` não existir ou não tiver `EMAIL=`:

Use `AskUserQuestion` para coletar email de login do Contabilizei.

Salve em `$CONFIG` com `chmod 600`:
```
EMAIL="<email>"
```

Verifique se a senha já está no Keychain:
```bash
security find-generic-password -a "<email>" -s "contabilizei-login" -w >/dev/null 2>&1
```

Se não estiver: use `AskUserQuestion` para perguntar a senha (campo de texto livre com aviso de que não será exibida no transcript). Salve **apenas no Keychain**:
```bash
security add-generic-password -a "<email>" -s "contabilizei-login" -w "<senha>" -U
```

A senha **nunca aparece em argv nem em logs.** Use `browser_fill_form` ou `browser_evaluate` para injetá-la no formulário — nunca `browser_type` com o valor literal visível.

## Passo 2 — Login e listagem

Registre o instante do início do login (para o guard de tempo do código OTP):
```
SUBMIT_TIME = agora (ISO)
```

**Orientação inicial — snapshot obrigatório antes de qualquer ação:**

```
browser_navigate → https://app.contabilizei.com.br/#/nota-tomada/listagem
browser_snapshot
```

Analise o snapshot:
- **Se já está na listagem** (logado): vá para o passo 3.
- **Se está na tela de login** (form de email/senha):
  1. Leia a senha do Keychain: `security find-generic-password -a "<email>" -s "contabilizei-login" -w`
  2. Preencha o campo de email com `browser_type`.
  3. Preencha a senha com `browser_evaluate` injetando JS que escreve no campo de senha — ou use `browser_fill_form` — **nunca** com o valor literal em `browser_type`.
  4. Submeta o formulário.
  5. `browser_snapshot` → analise o resultado.
- **Se aparece desafio de código de acesso** (formulário pedindo código enviado por email):
  - Veja sub-passo "Código de acesso" abaixo.
- **Se aparece outro desafio (SMS, autenticador, trusted-device)**:
  - Use `AskUserQuestion` para pedir o código ao usuário (fallback manual).
  - Preencha e submeta.
- **Se sessão expirou durante o fluxo** (detectado em qualquer passo): re-execute este passo 2 completo.

### Sub-passo: Código de acesso por email

Polling do Gmail (até ~30s, 6 tentativas com `browser_wait_for {time: 5}` entre elas):

```
Para cada tentativa (i = 1..6):
  browser_wait_for {time: 5}   # espaça sem sleep bloqueado
  Gmail.search_threads(query="from:contabilizei newer_than:1h", max_results=5)
  Para cada thread (mais recente primeiro):
    Gmail.get_thread(thread_id=...)
    Extraia o corpo do email mais recente
    Verifique: timestamp do email > SUBMIT_TIME  ← guard de tempo
    Regex contextual: r'(?:c[oó]digo(?:\s+de)?\s+(?:acesso|verifica[çc][ãa]o)|seu\s+c[oó]digo)[^\d]*(\d{4,8})'
    Se match E message-id ainda não consumido:
      Registre o message-id como consumido (evita código expirado em retry)
      Use o código encontrado → preencha e submeta
      Quebra o loop
```

Se após 6 tentativas nenhum código for encontrado ou o desafio não for por email:
- Use `AskUserQuestion` para pedir o código ao usuário (fallback manual).

Após submeter o código: `browser_snapshot` → confirme que está na listagem antes de prosseguir.

## Passo 3 — Checar duplicidade

Na listagem, use o filtro/busca da própria UI por **CNPJ + série + número** da NF.

`browser_snapshot` → analise o estado atual (filtro disponível? modal aberto?).

Aplique o filtro disponível. Se a NF aparecer nos resultados:
- Reporte: "NF já registrada (CNPJ `<cnpj>`, série `<serie>`, nº `<numero>`)."
- `browser_close`
- Encerre o comando.

Se não encontrar: prossiga para o passo 4.

> **Nota:** este check será repetido no passo 6 (imediatamente antes de Registrar) para cobrir o intervalo de tempo durante a pausa de confirmação (TOCTOU).

## Passo 4 — Resolver prestador

`browser_snapshot` — verifique onde está antes de navegar.

```
browser_navigate → https://app.contabilizei.com.br/#/nota-tomada/prestadores
browser_snapshot
```

Busque o prestador pelo CNPJ extraído no campo de busca da listagem.

- **Existe:** clique no prestador. A URL deve mudar para `.../registrar` com CNPJ e razão social já preenchidos. Verifique com `browser_snapshot`.
- **Não existe:** navegue para `.../nota-tomada/registrar` e preencha CNPJ e razão social nos campos correspondentes (identifique pelos rótulos/placeholders no snapshot).

## Passo 5 — Preencher formulário

`browser_snapshot` — confirme que está no formulário de registro.

Preencha os campos identificando-os pelo snapshot (rótulos/placeholders reais — não hardcode seletores):

- **Data de emissão:** valor de `data_emissao`
- **Número:** valor de `numero`
- **Série:** valor de `serie` (se presente no formulário e a NF tem série)
- **Valor:** formatar `valor` (centavos) como `R$ X.XXX,XX` antes de digitar
- **Descrição:** `descricao` truncada a 250 chars

**Tipo de serviço / Categoria:** leia as opções reais do `<select>` no snapshot. Case-fold e compare com `descricao` e `codigo_servico`. Se houver match razoável, selecione com `browser_select_option`. Se ambíguo, anote as top-3 opções para mostrar na confirmação (passo 6).

## Passo 6 — Confirmar antes de registrar

**Re-checar duplicidade** (TOCTOU): repita a busca do passo 3. Se a NF aparecer agora → reporte duplicata e encerre.

`browser_snapshot` — verifique o estado do form. Se a sessão expirou ou o form está em estado inesperado: re-autentique (passo 2) e re-preencha (passos 4–5). **Nunca submeta sobre form stale.**

Use `AskUserQuestion` com resumo completo:

```
NF a registrar:
  CNPJ:          <cnpj formatado XX.XXX.XXX/XXXX-XX>
  Prestador:     <razao_social>
  Data emissão:  <data_emissao>
  Número:        <numero>  Série: <serie ou —>
  Valor:         R$ <X.XXX,XX>
  Descrição:     <descricao> [FONTE FRÁGIL se veio do .txt]
  Tipo serviço:  <selecionado>
  Categoria:     <selecionada>

⚠️  Campos extraídos por regex (revisar): [lista campos frágeis, ou "nenhum"]
```

Opções:
- "Confirmar e registrar"
- "Corrigir campo"
- "Abortar"

Se "Corrigir campo": use `AskUserQuestion` para perguntar qual campo e o novo valor, atualize no form e volte ao início deste passo.

Se "Abortar": `browser_close`, encerre reportando "Registro abortado pelo usuário."

## Passo 7 — Registrar e verificar

Clique no botão *Registrar* (identifique pelo snapshot — não hardcode o seletor).

`browser_snapshot` → verifique o resultado:
- **Sucesso** (redirecionou para listagem ou exibe confirmação): reporte "NF registrada com sucesso."
- **Erro visível no formulário**: reporte o erro, ofereça corrigir ou abortar via `AskUserQuestion`.
- **Estado ambíguo** (snapshot não confirma nem nega): reporte "Resultado inconclusivo — verifique a listagem do Contabilizei para confirmar se a NF foi registrada."

`browser_close`

Reporte final em uma linha: `✅ NF registrada` / `ℹ️ Já existia` / `⚠️ Abortada` / `❓ Inconclusivo`.
