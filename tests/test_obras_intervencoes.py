"""Testes da B10: obras e intervenções."""

from __future__ import annotations

import unittest

from app.obras_intervencoes import _numero, _moeda, _data_br


class TestNumero(unittest.TestCase):
    def test_inteiro(self) -> None:
        self.assertEqual(_numero(50), "50")
        self.assertEqual(_numero(0), "0")

    def test_decimal(self) -> None:
        self.assertEqual(_numero(12.5), "12,5")

    def test_none(self) -> None:
        self.assertEqual(_numero(None), "—")


class TestMoeda(unittest.TestCase):
    def test_valor(self) -> None:
        self.assertEqual(_moeda(1500.50), "R$ 1.500,50")
        self.assertEqual(_moeda(0), "R$ 0,00")

    def test_none(self) -> None:
        self.assertEqual(_moeda(None), "—")


class TestDataBR(unittest.TestCase):
    def test_data_completa(self) -> None:
        self.assertEqual(_data_br("2026-10-14"), "14/10/2026")

    def test_vazio(self) -> None:
        self.assertEqual(_data_br(None), "")


if __name__ == "__main__":
    unittest.main()
