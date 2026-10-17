"""Testes da B5: calendário anual de risco."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.calendario_risco import _dias_para, _data_br, _mes_nome, _proxima_data, _proxima_dia_ou_mes


class TestMesNome(unittest.TestCase):
    def test_meses(self) -> None:
        self.assertEqual(_mes_nome(1), "Janeiro")
        self.assertEqual(_mes_nome(12), "Dezembro")
        self.assertEqual(_mes_nome(6), "Junho")


class TestDataBR(unittest.TestCase):
    def test_data_completa(self) -> None:
        self.assertEqual(_data_br("2026-10-14"), "14/10/2026")

    def test_vazio(self) -> None:
        self.assertEqual(_data_br(None), "")


class TestDiasPara(unittest.TestCase):
    def test_dia_futuro(self) -> None:
        futuro = date.today() + timedelta(days=10)
        self.assertEqual(_dias_para(futuro), 10)

    def test_dia_passado(self) -> None:
        passado = date.today() - timedelta(days=5)
        self.assertEqual(_dias_para(passado), -5)

    def test_hoje(self) -> None:
        self.assertEqual(_dias_para(date.today()), 0)


class TestProximaData(unittest.TestCase):
    def test_mes_futuro(self) -> None:
        # Hoje é outubro; dezembro é futuro
        resultado = _proxima_data(12)
        self.assertEqual(resultado.month, 12)
        self.assertEqual(resultado.year, date.today().year)

    def test_mes_passado(self) -> None:
        # Hoje é outubro; janeiro já passou, vai para próximo ano
        resultado = _proxima_data(1)
        self.assertEqual(resultado.month, 1)
        self.assertEqual(resultado.year, date.today().year + 1)


class TestProximaDiaOuMes(unittest.TestCase):
    def test_dia_valido(self) -> None:
        resultado = _proxima_dia_ou_mes(date(2026, 3, 15))
        self.assertEqual(resultado.month, 3)
        self.assertEqual(resultado.day, 15)

    def test_dia_31_em_mes_curto(self) -> None:
        # Hoje é outubro; 31 de janeiro já passou, vai para janeiro do próximo ano
        resultado = _proxima_dia_ou_mes(date(2026, 1, 31))
        self.assertEqual(resultado.month, 1)
        self.assertEqual(resultado.day, 31)
        self.assertEqual(resultado.year, date.today().year + 1)


if __name__ == "__main__":
    unittest.main()
