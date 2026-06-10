#!/usr/bin/env python3
"""Extract NF (nota fiscal) data from PDF or XML and save JSON + TXT to ~/finance/contabilizei/extracted/."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

EXTRACTED_DIR = pathlib.Path.home() / "finance" / "contabilizei" / "extracted"


# --- helpers ------------------------------------------------------------------


def local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def normalize_cnpj(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) not in (11, 14):
        return None
    return digits


def parse_valor_br(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # Remove currency symbols and whitespace
    s = re.sub(r"[R$\s]", "", s)
    if not s:
        return None
    # Determine decimal separator
    dot_pos = s.rfind(".")
    comma_pos = s.rfind(",")
    if comma_pos > dot_pos:
        # BR format: 1.234,56 or 1234,56
        integer_part = s[:comma_pos].replace(".", "")
        decimal_part = s[comma_pos + 1 :]
    elif dot_pos > comma_pos:
        # Check if dot is decimal separator (exactly 2 digits after last dot)
        after_dot = s[dot_pos + 1 :]
        if len(after_dot) == 2:
            # Treat as decimal: 1234.56
            integer_part = s[:dot_pos].replace(",", "")
            decimal_part = after_dot
        else:
            # Dot is thousands separator, no decimal
            integer_part = s.replace(".", "").replace(",", "")
            decimal_part = ""
    else:
        # No separator or only one type; no decimal
        integer_part = s.replace(".", "").replace(",", "")
        decimal_part = ""
    try:
        int_val = int(integer_part) if integer_part else 0
    except ValueError:
        return None
    if decimal_part:
        if len(decimal_part) == 1:
            decimal_part = decimal_part + "0"
        elif len(decimal_part) > 2:
            decimal_part = decimal_part[:2]
        try:
            dec_val = int(decimal_part)
        except ValueError:
            return None
    else:
        dec_val = 0
    return int_val * 100 + dec_val


def dedup_key(
    cnpj: str | None, serie: str | None, numero: str | None
) -> tuple[str, str, str]:
    return (cnpj or "", (serie or "").upper(), numero or "")


def _ensure_dirs() -> None:
    base = pathlib.Path.home() / "finance" / "contabilizei"
    base.mkdir(parents=True, exist_ok=True)
    base.chmod(0o700)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


# --- XML extraction -----------------------------------------------------------


def _find_text(root: ET.Element, local_name: str) -> str | None:
    for el in root.iter():
        if local(el.tag) == local_name:
            return (el.text or "").strip() or None
    return None


def extract_xml(path: pathlib.Path) -> dict:
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"err|xml-parse|{e}", file=sys.stderr)
        sys.exit(1)

    root = tree.getroot()

    cnpj_raw = _find_text(root, "Cnpj") or _find_text(root, "CpfCnpj")
    razao = _find_text(root, "RazaoSocial")
    data_emissao = _find_text(root, "DataEmissao")
    numero = _find_text(root, "Numero")
    serie = _find_text(root, "Serie")
    valor_raw = _find_text(root, "ValorServicos")
    discriminacao = _find_text(root, "Discriminacao")
    codigo = _find_text(root, "ItemListaServico") or _find_text(
        root, "CodigoTributacaoMunicipio"
    )

    # Municipio: look for Municipio or MunicipioIncidencia
    municipio = _find_text(root, "Municipio") or _find_text(root, "MunicipioIncidencia")

    # Normalize data_emissao to ISO date if it contains a T (datetime)
    if data_emissao and "T" in data_emissao:
        data_emissao = data_emissao.split("T")[0]

    # valor from XML is a decimal string like "1234.56"
    valor: int | None = None
    if valor_raw:
        valor = parse_valor_br(valor_raw)

    desc = (discriminacao or "")[:250] or None

    return {
        "cnpj": normalize_cnpj(cnpj_raw),
        "razao_social": razao,
        "data_emissao": data_emissao,
        "numero": numero,
        "serie": serie,
        "valor": valor,
        "descricao": desc,
        "codigo_servico": codigo,
        "municipio": municipio,
        "_source": "xml",
    }


# --- PDF extraction -----------------------------------------------------------


def _extract_text_pdfplumber(path: pathlib.Path) -> tuple[str, str]:
    import pdfplumber  # type: ignore[import-untyped]

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            pages.append(t)
    return "\n".join(pages), "pdf-pdfplumber"


def _extract_text_pypdf(path: pathlib.Path) -> tuple[str, str]:
    from pypdf import PdfReader  # type: ignore[import-untyped]

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        t = page.extract_text() or ""
        pages.append(t)
    return "\n".join(pages), "pdf-pypdf"


def _regex_first(
    pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL
) -> str | None:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    return m.group(1).strip() or None


def extract_pdf(path: pathlib.Path) -> tuple[dict, str]:
    try:
        text, source = _extract_text_pdfplumber(path)
    except ImportError:
        try:
            text, source = _extract_text_pypdf(path)
        except ImportError:
            print("err|no-pdf-lib|install pdfplumber or pypdf", file=sys.stderr)
            sys.exit(1)

    cnpj_raw = _regex_first(
        r"CNPJ[:\s]+([0-9]{2}[.\-/]?[0-9]{3}[.\-/]?[0-9]{3}[.\-/]?[0-9]{4}[.\-/]?[0-9]{2})",
        text,
    )
    razao_raw = _regex_first(r"Raz[ãa]o\s+Social[:\s]+(.+)", text)
    razao = (razao_raw or "")[:200].strip() or None

    data_raw = _regex_first(
        r"Data.*?Emiss[ãa]o[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", text
    )
    numero = _regex_first(r"N[úu]mero\s*[:\s]+(\d+)", text) or _regex_first(
        r"N[ºo°\.]\s*(\d+)", text
    )
    serie = _regex_first(r"S[ée]rie[:\s]+(\w+)", text)
    valor_raw = _regex_first(
        r"Valor(?:\s+(?:dos?\s+)?Servi[çc]os?)?[:\s]+R?\$?\s*([\d.,]+)",
        text,
    )
    disc_raw = _regex_first(
        r"Discrimina[çc][ãa]o(?:\s+dos?\s+Servi[çc]os?)?[:\s]+(.+)",
        text,
    )
    codigo = _regex_first(
        r"(?:Item\s+Lista\s+Servi[çc]o|C[óo]digo\s+(?:de\s+)?Tributa[çc][ãa]o)[:\s]+(\S+)",
        text,
    )
    municipio = _regex_first(r"Munic[íi]pio[:\s]+(.+)", text)

    desc = ((disc_raw or "")[:250]) or None

    result: dict = {
        "cnpj": normalize_cnpj(cnpj_raw),
        "razao_social": razao,
        "data_emissao": data_raw,
        "numero": numero,
        "serie": serie,
        "valor": parse_valor_br(valor_raw),
        "descricao": desc,
        "codigo_servico": codigo,
        "municipio": (municipio or "")[:100].strip() or None,
        "_source": source,
    }
    return result, text


# --- main ---------------------------------------------------------------------

REQUIRED_FIELDS = ("cnpj", "razao_social", "data_emissao", "numero", "valor")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract NF data from PDF or XML.")
    ap.add_argument("path", help="Path to .xml or .pdf file")
    args = ap.parse_args()

    src = pathlib.Path(args.path)
    if not src.exists():
        print(f"err|not-found|{src}", file=sys.stderr)
        return 1

    suffix = src.suffix.lower()
    full_text: str = ""

    if suffix == ".xml":
        data = extract_xml(src)
        full_text = src.read_text(errors="replace")
    elif suffix == ".pdf":
        data, full_text = extract_pdf(src)
    else:
        print(
            f"err|unsupported-format|{suffix} (expected .xml or .pdf)", file=sys.stderr
        )
        return 1

    _ensure_dirs()

    base = src.stem
    json_out = EXTRACTED_DIR / f"{base}.json"
    txt_out = EXTRACTED_DIR / f"{base}.txt"

    json_out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    json_out.chmod(0o600)

    txt_out.write_text(full_text)
    txt_out.chmod(0o600)

    null_fields = [f for f in REQUIRED_FIELDS if data.get(f) is None]
    if null_fields:
        print(f"warn|null-fields|{','.join(null_fields)}", file=sys.stderr)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"ok|extracted|{json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
