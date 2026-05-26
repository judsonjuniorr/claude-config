#!/usr/bin/env python3
"""Perfil pessoal do usuário (provider-agnóstico).

Armazena dados estruturados sobre quem é o usuário para que análises financeiras
sejam personalizadas: idade, profissão, renda, família, moradia, cidade,
tolerância a risco, hábitos. A cada execução de `/finance:organizze` os campos
ainda vazios são perguntados via AskUserQuestion no chat principal.

Arquivo: ~/finance/profile.md (markdown legível, formato `key: value` por linha).

Usage:
  profile.py get [<key>]              # lê tudo ou um campo
  profile.py set <key> <value>        # grava/atualiza um campo
  profile.py missing                  # lista chaves obrigatórias ainda vazias
  profile.py render                   # bloco markdown pronto pra injetar no prompt
  profile.py mark-skip                # grava timestamp em last_skip (silencia 7d)
  profile.py should-ask               # exit 0 se deve perguntar agora; 1 se silenciar
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _storage import PROFILE, migrate_legacy  # noqa: E402

REQUIRED_KEYS = [
    "idade",
    "profissao",
    "renda_liquida_mensal_cents",
    "estado_civil",
    "dependentes",
    "moradia_tipo",
    "moradia_custo_cents",
    "cidade",
    "tolerancia_risco",
]
OPTIONAL_KEYS = ["habitos", "objetivo_principal"]
META_KEYS = ["updated", "last_skip"]
ALL_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS + META_KEYS

ENUM_VALUES = {
    "estado_civil": {"solteiro", "relacionamento", "casado", "divorciado", "viuvo"},
    "moradia_tipo": {
        "propria_quitada", "propria_financiada", "alugada", "cedida", "outra",
    },
    "tolerancia_risco": {"conservador", "moderado", "agressivo"},
}
INT_KEYS = {"idade", "renda_liquida_mensal_cents", "moradia_custo_cents"}

LINE_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*?)\s*$")


def _load() -> dict[str, str]:
    if not PROFILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in PROFILE.read_text().splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        out[m.group(1)] = m.group(2)
    return out


def _save(data: dict[str, str]) -> None:
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = [
        "# Perfil do usuário",
        "# Editável à mão. Um campo por linha, formato `chave: valor`. "
        "Não use múltiplas linhas.",
        "# Campos vazios são re-perguntados em /finance:organizze. Para silenciar "
        "por 7 dias, rode `profile.py mark-skip`.",
        "",
    ]
    data["updated"] = dt.date.today().isoformat()
    ordered = REQUIRED_KEYS + OPTIONAL_KEYS + META_KEYS
    for k in ordered:
        if k in data and data[k] != "":
            out.append(f"{k}: {data[k]}")
    PROFILE.write_text("\n".join(out) + "\n")
    PROFILE.chmod(0o600)


def _brl(c: int | None) -> str:
    if c is None:
        return "(sem dados)"
    v = abs(int(c)) / 100.0
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _validate(key: str, value: str) -> str | None:
    """Retorna erro como string ou None se OK."""
    if key in INT_KEYS:
        try:
            int(value)
        except ValueError:
            return f"campo `{key}` exige inteiro (centavos para valores monetários)"
    if key in ENUM_VALUES:
        if value not in ENUM_VALUES[key]:
            return f"campo `{key}` aceita: {sorted(ENUM_VALUES[key])}"
    return None


def cmd_get(args) -> int:
    data = _load()
    if args.key:
        if args.key not in data:
            print("", end="")
            return 0
        print(data[args.key])
        return 0
    if not data:
        print("(perfil vazio)", file=sys.stderr)
        return 0
    for k in REQUIRED_KEYS + OPTIONAL_KEYS:
        if k in data:
            print(f"{k}: {data[k]}")
    return 0


def cmd_set(args) -> int:
    key = args.key.strip()
    value = args.value.strip()
    if key not in ALL_KEYS:
        print(f"err|bad-key|{key} — aceitas: {ALL_KEYS}", file=sys.stderr)
        return 1
    err = _validate(key, value)
    if err:
        print(f"err|bad-value|{err}", file=sys.stderr)
        return 1
    data = _load()
    if value == "":
        data.pop(key, None)
    else:
        data[key] = value
    # mudança em qualquer campo limpa o silêncio anterior (engajamento renovado)
    if key not in META_KEYS and "last_skip" in data:
        data.pop("last_skip", None)
    _save(data)
    print(f"ok|set|{key}={value}|{PROFILE}")
    return 0


def cmd_missing(args) -> int:
    data = _load()
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    for k in missing:
        print(k)
    return 0


def cmd_mark_skip(args) -> int:
    data = _load()
    data["last_skip"] = dt.date.today().isoformat()
    _save(data)
    print(f"ok|skip-marked|{data['last_skip']}")
    return 0


def cmd_should_ask(args) -> int:
    """Exit 0 = perguntar; 1 = silenciar.
    Silencia se TODOS os obrigatórios preenchidos OU se last_skip <7d e ainda há campos faltantes."""
    data = _load()
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if not missing:
        return 1  # perfil completo, nada a perguntar
    last_skip = data.get("last_skip")
    if last_skip:
        try:
            d = dt.date.fromisoformat(last_skip)
            if (dt.date.today() - d).days < 7:
                return 1  # silenciado
        except ValueError:
            pass
    return 0  # perguntar


def cmd_render(args) -> int:
    data = _load()
    print("# Perfil do usuário (CONTEXTO PESSOAL — calibrar recomendações)")
    print()
    print("Use estes dados para personalizar análises (faixa etária, renda, "
          "dependentes, custo de moradia, cidade, tolerância a risco). "
          "**Toda recomendação deve referenciar ao menos um campo aqui.** "
          "Campos marcados `(sem dados)` significam que o usuário ainda não "
          "informou — se algum for crítico para sua recomendação, emita uma "
          "`[PERGUNTA]` no bloco final do relatório.")
    print()

    idade = data.get("idade") or "(sem dados)"
    print(f"- **Idade**: {idade}{' anos' if idade != '(sem dados)' else ''}")
    print(f"- **Profissão**: {data.get('profissao') or '(sem dados)'}")
    renda = data.get("renda_liquida_mensal_cents")
    print(f"- **Renda líquida mensal**: {_brl(int(renda)) if renda else '(sem dados)'}")
    print(f"- **Estado civil**: {data.get('estado_civil') or '(sem dados)'}")
    print(f"- **Dependentes**: {data.get('dependentes') or '(sem dados)'}")
    moradia = data.get("moradia_tipo") or "(sem dados)"
    custo = data.get("moradia_custo_cents")
    custo_str = _brl(int(custo)) if custo else "(sem dados)"
    print(f"- **Moradia**: {moradia} — custo {custo_str}/mês")
    print(f"- **Cidade**: {data.get('cidade') or '(sem dados)'} "
          f"(use ao buscar preços/alternativas de mercado)")
    print(f"- **Tolerância a risco**: {data.get('tolerancia_risco') or '(sem dados)'} "
          f"(usa para escolher avalanche vs snowball na quitação)")
    if data.get("habitos"):
        print(f"- **Hábitos**: {data['habitos']}")
    if data.get("objetivo_principal"):
        print(f"- **Objetivo principal de curto prazo**: {data['objetivo_principal']}")
    if data.get("updated"):
        print(f"\n_(Última atualização: {data['updated']})_")
    return 0


def main() -> int:
    migrate_legacy()

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get")
    g.add_argument("key", nargs="?", default=None)
    g.set_defaults(func=cmd_get)

    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(func=cmd_set)

    m = sub.add_parser("missing")
    m.set_defaults(func=cmd_missing)

    r = sub.add_parser("render")
    r.set_defaults(func=cmd_render)

    sk = sub.add_parser("mark-skip")
    sk.set_defaults(func=cmd_mark_skip)

    sa = sub.add_parser("should-ask")
    sa.set_defaults(func=cmd_should_ask)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
