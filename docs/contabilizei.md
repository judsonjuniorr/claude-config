# contabilizei

Comandos para registrar notas fiscais no Contabilizei via automação headless.

## `/contabilizei:nf-tomada <arquivo>`

Registra uma **NF tomada** (nota fiscal de serviço recebida) a partir de um PDF ou XML local.

**O que faz:**
1. Extrai os dados da nota via script Python (PDF multi-município defensivo ou XML ABRASF).
2. Faz login headless no Contabilizei; lê o código de acesso automaticamente do Gmail.
3. Checa duplicidade pela listagem da UI (CNPJ + série + número).
4. Resolve o prestador (existente ou novo cadastro).
5. Preenche o formulário de registro.
6. **Pausa para confirmação** antes de enviar — ação fiscal difícil de reverter.
7. Reporta o resultado.

**Quando usar:** sempre que receber uma NF de serviço que precisa ser lançada no Contabilizei.

**Pré-requisitos:**
- macOS Keychain (usado para guardar a senha — nunca fica em disco).
- MCP `playwright-headless` configurado e ativo na sessão Claude Code.
- MCP `Gmail` configurado e autenticado (`mcp__claude_ai_Gmail__*`).
- Python 3 com `pdfplumber` (instalado automaticamente pelo `setup.sh`).

**Dados locais em `~/finance/contabilizei/`** — este diretório **nunca é commitado** no repositório. Contém:
- `.config` — email de login (modo `600`).
- `extracted/` — JSONs e textos extraídos das notas (modo `600`), dados fiscais/PII.

Limpe `extracted/` periodicamente; os arquivos contêm dados de terceiros.
