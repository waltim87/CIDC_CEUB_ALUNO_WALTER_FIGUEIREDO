"""Testes da B2: checklist de abrigo pronto."""

from __future__ import annotations

import unittest

from app.abrigo_vistoria import _dias_atras, _hora_local, _numero


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


class TestDiasAtras(unittest.TestCase):
    def test_data_antiga(self) -> None:
        from datetime import date, timedelta
        ontem = date.today() - timedelta(days=5)
        self.assertEqual(_dias_atras(ontem), 5)

    def test_data_hoje(self) -> None:
        from datetime import date
        self.assertEqual(_dias_atras(date.today()), 0)

    def test_none(self) -> None:
        self.assertIsNone(_dias_atras(None))


if __name__ == "__main__":
    unittest.main()
