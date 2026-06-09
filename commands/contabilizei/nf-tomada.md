---
description: (herow) Registra uma NF tomada no Contabilizei a partir de PDF/XML — login headless com código via Gmail, checagem de duplicidade e confirmação antes de enviar.
argument-hint: "<caminho do PDF ou XML da NF>"
allowed-tools: Bash, Read, Write, AskUserQuestion, mcp__playwright-headless__browser_navigate, mcp__playwright-headless__browser_snapshot, mcp__playwright-headless__browser_click, mcp__playwright-headless__browser_type, mcp__playwright-headless__browser_select_option, mcp__playwright-headless__browser_fill_form, mcp__playwright-headless__browser_evaluate, mcp__playwright-headless__browser_wait_for, mcp__playwright-headless__browser_close, mcp__claude_ai_Gmail__search_threads, mcp__claude_ai_Gmail__get_thread
---

# `/contabilizei:nf-tomada`

**Regra global: toda pergunta ao usuário usa `AskUserQuestion` com opções — nunca inline.** `AskUserQuestion` exige **no mínimo 2 opções** por pergunta; para campos de texto livre (email, senha, código), ofereça a opção desejada + uma alternativa como "Abortar"/"Outro".

Registra uma NF tomada (nota fiscal de serviço recebida) no Contabilizei a partir de um arquivo PDF ou XML local.

## Passo 0 — Extrair dados da NF

Resolve `$ARGUMENTS` como caminho do arquivo. Se vazio ou não informado, use `AskUserQuestion` para pedir o caminho.

> `$0` **não** resolve a pasta do comando neste harness (o bloco roda fora dela). Descubra `SCRIPT_DIR` procurando nas localizações conhecidas:

```bash
for d in \
  "$HOME/.claude/commands/contabilizei/contabilizei-scripts" \
  "$HOME/sources/personal/claude-config/commands/contabilizei/contabilizei-scripts" \
  "$(dirname "$0")/contabilizei-scripts"; do
  [ -f "$d/extract_nf.py" ] && SCRIPT_DIR="$d" && break
done
[ -z "${SCRIPT_DIR:-}" ] && { echo "err|scripts-not-found|contabilizei-scripts" >&2; exit 1; }
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
browser_navigate → https://app.contabilizei.com.br/painel-de-controle/#/nota-tomada/listagem
browser_snapshot
```

> A URL canônica inclui `/painel-de-controle/`. Sem ela o app redireciona, mas use a forma completa nas navegações dos passos 4–6 para evitar redirects extras.

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

O remetente do código é `seguranca@contabilizei.com.br` (assunto: "Seu código de acesso à plataforma chegou!"). A query `from:contabilizei` cobre.

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
      Marque o email como lido (remova o label UNREAD via Gmail.unlabel_message — sempre, após obter o código)
      Quebra o loop
```

Se após 6 tentativas nenhum código for encontrado ou o desafio não for por email:
- Use `AskUserQuestion` para pedir o código ao usuário (fallback manual).

Após submeter o código: `browser_snapshot` → confirme que está na listagem antes de prosseguir.

### Sub-passo: Dispensar modais bloqueantes (rodar após CADA navegação)

O app exibe modais recorrentes que reaparecem a cada navegação e cobrem o conteúdo: **"Sua mensalidade está atrasada"**, **"Por onde eu começo?"**, **QR code do app** e similares. Dispense-os antes de interagir com a página — clique direto via JS (eles podem estar fora da viewport, o que faz `browser_click` dar timeout):

```
browser_evaluate:
() => {
  const labels = ['Solicitar mais dias', 'Entendi', 'Fechar', 'close'];
  const clicked = [];
  document.querySelectorAll('button').forEach(b => {
    const t = (b.textContent || '').trim();
    const aria = b.getAttribute('aria-label') || '';
    if (labels.some(l => t === l || t.includes(l) || aria === l)) { b.click(); clicked.push(t || aria); }
  });
  return clicked;
}
```

> **NÃO** clique em "Regularizar mensalidade", "Cancelar" de um dialog de registro, nem em botões de ação fiscal. Dispense apenas modais informativos/onboarding.
>
> **Cuidado com dialogs latentes:** o snapshot de acessibilidade pode listar `dialog` nodes que estão no DOM mas **ocultos** (`v-show`/`display:none`) — não estão realmente ativos. Antes de tratar um dialog como bloqueante ou agir nos seus botões, **confirme que está visível**:
>
> ```
> browser_evaluate (no elemento do dialog):
> (el) => { const r = el.getBoundingClientRect(); return !!el.offsetParent && r.width > 0 && r.height > 0; }
> ```

## Passo 3 — Checar duplicidade

A listagem **não** tem busca livre por CNPJ/número — o filtro real é o seletor **Competência** (mês + ano). Selecione a competência correspondente ao mês/ano de `data_emissao` da NF.

`browser_snapshot` → localize os dois `combobox` de Competência (mês e ano). Use `browser_select_option` para selecionar o mês e o ano da NF.

Examine o "Histórico de notas" resultante:
- Se aparecer NF com mesmo **número** (e série, se houver) do mesmo prestador:
  - Reporte: "NF já registrada (CNPJ `<cnpj>`, série `<serie>`, nº `<numero>`)."
  - `browser_close`
  - Encerre o comando.
- Se mostrar "Nenhuma nota tomada encontrada" ou nenhuma com o número da NF: prossiga para o passo 4.

> **Nota:** este check será repetido no passo 6 (imediatamente antes de Registrar) para cobrir o intervalo de tempo durante a pausa de confirmação (TOCTOU).

## Passo 4 — Resolver prestador

`browser_snapshot` — verifique onde está antes de navegar.

```
browser_navigate → https://app.contabilizei.com.br/painel-de-controle/#/nota-tomada/prestadores
browser_snapshot
```

Dispense os modais (sub-passo do passo 2). A tela tem um campo "Busque pelo nome ou CNPJ do prestador" e a lista de prestadores já cadastrados.

Busque o prestador pelo CNPJ extraído (ou localize-o na lista).

- **Existe:** clique no item do prestador. A URL muda para `.../nota-tomada/registrar` com CNPJ e razão social já preenchidos no topo do form. Verifique com `browser_snapshot`.
- **Não existe:** clique em "Cadastrar novo prestador" e preencha CNPJ e razão social nos campos correspondentes (identifique pelos rótulos/placeholders no snapshot).

## Passo 5 — Preencher formulário

`browser_snapshot` — confirme que está no formulário de registro e dispense os modais (sub-passo do passo 2).

Identifique os campos pelo snapshot (rótulos/placeholders reais). Os `data-testid` abaixo foram observados e servem como **dica/fallback** — confirme no snapshot antes de usar:

- **Data de emissão** (`input-emission-date`, placeholder `00/00/0000`): valor de `data_emissao` no formato `DD/MM/AAAA`.
- **Número** (`input-invoice-number`): valor de `numero`.
- **Série** (`input-serial-number`): **o campo aceita apenas dígitos.** Se `serie` for não-numérica (ex.: "E"), **deixe em branco** — não tente digitar a letra (é rejeitada silenciosamente).
- **Valor** (`input-grade-value`, id `input-valor-nota`): campo **mascarado** (`R$ 0,00`). `browser_fill_form`/`browser_type` não funcionam. Injete via JS com o setter nativo, passando só os números com vírgula decimal (ex.: `10,99`):
  ```
  browser_evaluate:
  () => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const el = document.querySelector('[data-testid="input-grade-value"]');
    set.call(el, ''); el.dispatchEvent(new Event('input', {bubbles:true}));
    set.call(el, '10,99');  // substitua pelo valor real
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
    return el.value;  // deve retornar "R$ 10,99"
  }
  ```
- **Descrição** (`Descrição do serviço*`): `descricao` truncada a 250 chars.

**Tipo de serviço** (`select-list-services`) **e Categoria** (`select-list-categories`): leia as opções reais do `<select>` no snapshot. Case-fold e compare com `descricao` e `codigo_servico`. Se houver match razoável, selecione com `browser_select_option`. Se ambíguo, anote as top-3 opções para mostrar na confirmação (passo 6). A Categoria costuma ter poucas opções (ex.: "Outras", "Sistemas de Pagamento") — escolha "Outras" se nenhuma for específica.

## Passo 6 — Confirmar antes de registrar

**Re-checar duplicidade** (TOCTOU): repita a busca do passo 3. Se a NF aparecer agora → reporte duplicata e encerre.

`browser_snapshot` — verifique o estado do form. Se a sessão expirou ou o form está em estado inesperado: re-autentique (passo 2) e re-preencha (passos 4–5). **Nunca submeta sobre form stale.**

Antes de confirmar, **leia de volta os valores reais do form** (via `browser_evaluate` lendo os `.value` dos campos) — confirme que o que será enviado bate com o extraído.

Use `AskUserQuestion`. **O resumo completo vai no próprio texto da pergunta (`question`)** — não apenas em `annotations`/`description`. O usuário precisa ver todos os campos diretamente no card da pergunta. Inclua, um por linha:

```
Confirma o registro desta NF tomada?

• CNPJ:          <cnpj formatado XX.XXX.XXX/XXXX-XX>
• Prestador:     <razao_social>
• Data emissão:  <data_emissao>
• Número:        <numero>   Série: <serie ou —>
• Valor:         R$ <X.XXX,XX>
• Tipo serviço:  <selecionado>
• Categoria:     <selecionada>
• Descrição:     <descricao>
• Competência:   <MM/AAAA> (<mês atual — sem reabertura | mês passado — ATENÇÃO: reabertura/taxa>)

⚠️ Campos extraídos por regex (revisar): [lista campos frágeis, ou "nenhum"]
```

Opções:
- "Confirmar e registrar"
- "Corrigir campo"
- "Abortar"

Se "Corrigir campo": use `AskUserQuestion` para perguntar qual campo e o novo valor, atualize no form e volte ao início deste passo.

Se "Abortar": `browser_close`, encerre reportando "Registro abortado pelo usuário."

## Passo 7 — Registrar e verificar

Clique no botão *Registrar nota* (identifique pelo snapshot — fica desabilitado até o form estar válido).

`browser_snapshot` → verifique o resultado.

### Dialog "Reabertura do mês contábil"

Ao registrar uma NF de **competência já fechada** (mês contábil passado), o Contabilizei abre o dialog **"Reabertura do mês contábil"** — informa uma **taxa única** (≈R$ 21,90 Simples / R$ 54,90 Lucro Presumido por mês fora do prazo) e **transfere ao usuário** a responsabilidade por multas/juros. Botões: "Cancelar" e "Aceitar reabertura e registrar nota".

> **Não confunda DOM com ativo.** Esse dialog é um componente Vue que aparece no snapshot **montado mas se auto-oculta** (via transição CSS) para NF do mês atual (competência aberta). Uma checagem de visibilidade **instantânea dá falso positivo** — pega o modal mid-mount com `opacity` transicionando (`offsetParent` ainda truthy, `opacity` 1→0).
>
> Por isso: ao entrar em `/registrar`, **espere o settle** (`browser_wait_for {time: 2}`) **antes** de checar. Depois confirme visibilidade via `data-testid="modal-reopening-month-accounting"`:
>
> ```
> browser_evaluate:
> () => {
>   const el = document.querySelector('[data-testid="modal-reopening-month-accounting"]');
>   if (!el) return { active: false };
>   const cs = getComputedStyle(el);
>   return { active: !!el.offsetParent && cs.opacity !== '0' && cs.visibility !== 'hidden' };
> }
> ```
>
> Se `active === false`, **ignore o dialog** — competência no prazo, registro segue normal sem taxa (o app inclusive confirma: "prazo máximo é dia 05 do mês seguinte").

Se o dialog estiver **realmente visível** (NF de mês passado):
- Use `AskUserQuestion` para surfacer ao usuário: a taxa exata exibida + a transferência de responsabilidade por multas/juros.
- Só clique "Aceitar reabertura e registrar nota" com consentimento explícito.
- Se "Abortar": clique "Cancelar", `browser_close`, encerre.

Após resolver o dialog (ou se ele não apareceu), `browser_snapshot` → verifique o resultado:
- **Sucesso** (redirecionou para listagem ou exibe confirmação): reporte "NF registrada com sucesso."
- **Erro visível no formulário**: reporte o erro, ofereça corrigir ou abortar via `AskUserQuestion`.
- **Estado ambíguo** (snapshot não confirma nem nega): reporte "Resultado inconclusivo — verifique a listagem do Contabilizei para confirmar se a NF foi registrada."

`browser_close`

Reporte final em uma linha: `✅ NF registrada` / `ℹ️ Já existia` / `⚠️ Abortada` / `❓ Inconclusivo`.
