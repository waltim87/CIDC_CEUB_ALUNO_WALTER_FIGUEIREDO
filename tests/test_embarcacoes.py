"""Testes da B9: embarcações e equipes."""

from __future__ import annotations

import unittest

from app.embarcacoes import _numero, _hora_local


class TestNumero(unittest.TestCase):
    def test_inteiro(self) -> None:
        self.assertEqual(_numero(50), "50")
        self.assertEqual(_numero(0), "0")

    def test_decimal(self) -> None:
        self.assertEqual(_numero(12.5), "12,5")

    def test_none(self) -> None:
        self.assertEqual(_numero(None), "—")


class TestHoraLocal(unittest.TestCase):
    def test_utc_para_manaus(self) -> None:
        self.assertEqual(_hora_local("2026-10-14T18:00:00+00:00"), "14/10 14:00 (Manaus)")

    def test_vazio(self) -> None:
        self.assertEqual(_hora_local(None), "—")
        self.assertEqual(_hora_local(""), "—")


if __name__ == "__main__":
    unittest.main()
