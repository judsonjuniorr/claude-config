---
description: Gerencia o perfil pessoal (idade, profissão, renda, família, moradia, cidade, risco) que análises usam para personalizar recomendações.
allowed-tools: Bash, AskUserQuestion
argument-hint: "[<texto livre> | init | list | get <key> | set <key> <value> | skip]"
---

# /finance:profile — Perfil pessoal (provider-agnóstico)

> **REGRA GLOBAL — perguntas ao usuário:** toda pergunta que exija resposta do usuário deve ser feita via tool `AskUserQuestion`, com 2-4 opções estruturadas (o campo de texto livre "Outro" é automático). **Nunca** faça perguntas inline no texto.

Wrapper conversacional sobre `commands/finance/scripts/profile.py`. Dados ficam em `~/finance/profile.md` (formato `key: value`, editável à mão) e são injetados em **toda análise** (`/finance:organizze` e futuros providers) como contexto pessoal — para calibrar recomendações por idade, renda, dependentes, moradia, cidade, tolerância a risco.

Path absoluto do script:
`/Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py`

Quando o usuário invocar `/finance:profile`, classifique `$ARGUMENTS` e siga o fluxo. Não pré-inspecione filesystem.

---

## Campos do perfil

| Chave                            | Tipo                                                                                  | Obrig. |
|----------------------------------|---------------------------------------------------------------------------------------|:------:|
| `idade`                          | inteiro                                                                               |   ✓    |
| `profissao`                      | texto livre                                                                           |   ✓    |
| `renda_liquida_mensal_cents`     | inteiro em centavos (R$ 12.000,00 = `1200000`)                                        |   ✓    |
| `estado_civil`                   | `solteiro` \| `relacionamento` \| `casado` \| `divorciado` \| `viuvo`                 |   ✓    |
| `dependentes`                    | texto livre (ex.: "nenhum", "2 filhos (5 e 8 anos)", "esposa + cachorro")             |   ✓    |
| `moradia_tipo`                   | `propria_quitada` \| `propria_financiada` \| `alugada` \| `cedida` \| `outra`         |   ✓    |
| `moradia_custo_cents`            | inteiro em centavos (parcela financiamento ou aluguel; `0` se cedida/quitada)         |   ✓    |
| `cidade`                         | texto livre (ex.: "São Paulo, SP") — usado em pesquisa de mercado                     |   ✓    |
| `tolerancia_risco`               | `conservador` \| `moderado` \| `agressivo`                                            |   ✓    |
| `habitos`                        | texto livre, 1 linha (ex.: "treina 4x/sem, home office")                              |        |
| `objetivo_principal`             | texto livre, 1 linha (foco financeiro do momento)                                     |        |

---

## Modo 1 — Sem args (gerenciar)

1. Mostre o perfil atual:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py get
   ```

2. Liste campos faltantes:
   ```bash
   python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py missing
   ```

3. Pergunte via `AskUserQuestion` o que fazer:
   - **A) Preencher faltantes agora** — vá ao Modo 4 (entrevista).
   - **B) Atualizar um campo específico** — pergunte qual + novo valor, rode `profile.py set <key> <value>`.
   - **C) Iniciar entrevista completa do zero** — vá ao Modo 4.
   - **D) Silenciar perguntas por 7 dias** — rode `profile.py mark-skip`.
   - **E) Sair**.

## Modo 2 — Texto livre (registrar)

`$ARGUMENTS` traz uma frase tipo "tenho 32 anos, sou dev, ganho 12k". Extraia o que conseguir e grave campo a campo com `profile.py set`. Para o que não der pra inferir com certeza, **não chute** — peça via `AskUserQuestion` ou deixe pra próxima.

Para valores monetários em frases ("12k", "R$ 12.000", "12 mil") converta para centavos antes de gravar.

## Modo 3 — Sub-comandos diretos

| Argumento                       | Comando                                                |
|---------------------------------|--------------------------------------------------------|
| `list` ou `get`                 | `profile.py get` (lista tudo)                          |
| `get <key>`                     | `profile.py get <key>`                                 |
| `set <key> <value>`             | `profile.py set <key> <value>`                         |
| `missing`                       | `profile.py missing`                                   |
| `skip`                          | `profile.py mark-skip` (silencia por 7d)               |
| `init`                          | vai pro Modo 4                                         |

## Modo 4 — Entrevista (init ou faltantes)

Para cada chave a perguntar (todas no `init`; apenas as de `missing` quando convocado pelo `/finance:organizze`), use `AskUserQuestion` com formato adequado e **sempre incluindo opção "Pular"**.

**Sugestões de formato por campo:**

- `idade`: pergunta aberta ("Qual sua idade?"), aceite resposta numérica.
- `profissao`: pergunta aberta ("Qual sua profissão / como você ganha dinheiro?").
- `renda_liquida_mensal_cents`: pergunta aberta ("Qual sua renda líquida média mensal em R$?"). Converta para centavos.
- `estado_civil`: opções `solteiro / relacionamento / casado / divorciado / viuvo` + Pular.
- `dependentes`: pergunta aberta ("Tem dependentes? Quantos e idades, ou 'nenhum'").
- `moradia_tipo`: opções `própria quitada / própria financiada / alugada / cedida / outra` + Pular. (Mapear texto da opção pro enum: "própria quitada" → `propria_quitada`, etc.)
- `moradia_custo_cents`: pergunta aberta ("Quanto paga de moradia por mês (parcela ou aluguel) em R$? Use 0 se zero"). Converta para centavos.
- `cidade`: pergunta aberta ("Em que cidade/estado mora? Ex.: 'São Paulo, SP'").
- `tolerancia_risco`: opções `conservador / moderado / agressivo` + Pular. Acrescente descrição curta de cada uma.
- `habitos` (opcional): pergunta aberta ("Algum hábito/contexto relevante? Ex.: 'treino 4x/sem, home office, viajo bastante'").
- `objetivo_principal` (opcional): pergunta aberta ("Qual seu foco financeiro principal agora? Ex.: 'quitar cartão', 'guardar reserva', 'comprar carro'").

Para cada resposta válida, grave imediatamente:
```bash
python3 /Users/judson/sources/personal/claude-config/commands/finance/scripts/profile.py set <key> "<value>"
```

Se o usuário pular **todos** os campos, rode `profile.py mark-skip` (silencia por 7 dias).

Ao final, mostre o estado atualizado com `profile.py get` e diga: "Próximo `/finance:organizze` já considera."

---

## Regras

- **Não chame `/finance:organizze`** automaticamente. Este comando é CRUD; análise é separada.
- O script roda migração legacy automaticamente na primeira execução.
- Storage é editável à mão (`~/finance/profile.md`).
- **Limite por sessão**: se chamado pelo `/finance:organizze` no fluxo de entrevista, pergunte no máximo **6 campos** por turno pra não cansar. Os demais entram na próxima execução.
- **Conversão monetária**: usuário diz "12k" → grave `1200000`. Usuário diz "R$ 1.200,50" → grave `120050`. Confirme em 1 linha antes de gravar quando o valor for ambíguo.
