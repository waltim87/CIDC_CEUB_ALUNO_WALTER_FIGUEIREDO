"""Testes da B1: áreas de risco por comunidade."""

from __future__ import annotations

import unittest

from app.areas_risco import _hora_local, _numero


class TestNumero(unittest.TestCase):
    def test_inteiro(self) -> None:
        self.assertEqual(_numero(50), "50")
        self.assertEqual(_numero(0), "0")

    def test_decimal(self) -> None:
        self.assertEqual(_numero(12.5), "12,5")
        self.assertEqual(_numero(0.0), "0")

    def test_none(self) -> None:
        self.assertEqual(_numero(None), "—")


class TestHoraLocal(unittest.TestCase):
    def test_utc_para_manaus(self) -> None:
        # 2026-10-14T18:00:00Z -> 14/10 14:00 (Manaus = UTC-4)
        self.assertEqual(_hora_local("2026-10-14T18:00:00+00:00"), "14/10 14:00 (Manaus)")

    def test_vazio(self) -> None:
        self.assertEqual(_hora_local(None), "—")
        self.assertEqual(_hora_local(""), "—")

    def test_sem_fuso(self) -> None:
        self.assertEqual(_hora_local("2026-10-14T18:00:00"), "14/10 14:00 (Manaus)")


if __name__ == "__main__":
    unittest.main()
