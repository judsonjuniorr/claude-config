#!/usr/bin/env python3
"""Unit tests for pure functions in extract_nf.py."""

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from extract_nf import dedup_key, normalize_cnpj, parse_valor_br

OTP_PATTERN = r"(?:c[oó]digo(?:\s+de)?\s+(?:acesso|verifica[çc][ãa]o)|seu\s+c[oó]digo)[^\d]*(\d{4,8})"


class TestParseValorBr(unittest.TestCase):
    def test_br_format_with_thousands(self) -> None:
        self.assertEqual(parse_valor_br("1.234,56"), 123456)

    def test_br_format_no_thousands(self) -> None:
        self.assertEqual(parse_valor_br("1234,56"), 123456)

    def test_dot_as_decimal(self) -> None:
        self.assertEqual(parse_valor_br("1234.56"), 123456)

    def test_integer_reais(self) -> None:
        self.assertEqual(parse_valor_br("1234"), 123400)

    def test_zero_cents(self) -> None:
        self.assertEqual(parse_valor_br("0,50"), 50)

    def test_none_input(self) -> None:
        self.assertIsNone(parse_valor_br(None))

    def test_empty_string(self) -> None:
        self.assertIsNone(parse_valor_br(""))

    def test_non_numeric(self) -> None:
        self.assertIsNone(parse_valor_br("abc"))

    def test_currency_symbol_stripped(self) -> None:
        self.assertEqual(parse_valor_br("R$ 1.500,00"), 150000)

    def test_single_cent(self) -> None:
        self.assertEqual(parse_valor_br("0,01"), 1)

    def test_large_value(self) -> None:
        self.assertEqual(parse_valor_br("10.000,00"), 1000000)


class TestNormalizeCnpj(unittest.TestCase):
    def test_formatted_cnpj(self) -> None:
        self.assertEqual(normalize_cnpj("12.345.678/0001-95"), "12345678000195")

    def test_digits_only(self) -> None:
        self.assertEqual(normalize_cnpj("12345678000195"), "12345678000195")

    def test_cpf(self) -> None:
        self.assertEqual(normalize_cnpj("123.456.789-09"), "12345678909")

    def test_none(self) -> None:
        self.assertIsNone(normalize_cnpj(None))

    def test_too_short(self) -> None:
        self.assertIsNone(normalize_cnpj("1234"))

    def test_wrong_length(self) -> None:
        self.assertIsNone(normalize_cnpj("1234567890123"))  # 13 digits


class TestDedupKey(unittest.TestCase):
    def test_full_values(self) -> None:
        self.assertEqual(
            dedup_key("12345678000195", "A", "100"),
            ("12345678000195", "A", "100"),
        )

    def test_none_values_become_empty_string(self) -> None:
        self.assertEqual(dedup_key(None, None, None), ("", "", ""))

    def test_serie_uppercased(self) -> None:
        key = dedup_key("12345678000195", "a", "1")
        self.assertEqual(key[1], "A")

    def test_mixed_none(self) -> None:
        key = dedup_key("12345678000195", None, "42")
        self.assertEqual(key, ("12345678000195", "", "42"))

    def test_serie_already_upper(self) -> None:
        key = dedup_key(None, "B", "99")
        self.assertEqual(key, ("", "B", "99"))


class TestOtpRegex(unittest.TestCase):
    def _match(self, text: str) -> str | None:
        m = re.search(OTP_PATTERN, text, re.IGNORECASE)
        return m.group(1) if m else None

    def test_codigo_acesso(self) -> None:
        self.assertEqual(self._match("Seu código de acesso: 123456"), "123456")

    def test_codigo_verificacao(self) -> None:
        self.assertEqual(self._match("código de verificação 9999"), "9999")

    def test_seu_codigo(self) -> None:
        self.assertEqual(self._match("seu código 12345678"), "12345678")

    def test_no_context_no_match(self) -> None:
        self.assertIsNone(self._match("random number 4444"))

    def test_standalone_digits_no_match(self) -> None:
        self.assertIsNone(self._match("12345"))

    def test_codigo_acesso_no_de(self) -> None:
        self.assertEqual(self._match("código acesso 7777"), "7777")

    def test_too_short_digit_no_match(self) -> None:
        # 3 digits is below \d{4,8} minimum
        self.assertIsNone(self._match("seu código 123"))

    def test_accented_variant(self) -> None:
        self.assertEqual(self._match("Seu código de acesso é 654321"), "654321")


if __name__ == "__main__":
    unittest.main()
