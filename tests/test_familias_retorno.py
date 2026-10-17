"""Testes da B6: retorno das famílias."""

from __future__ import annotations

import unittest

from app.familias_retorno import _data_br, _sim_nao


class TestDataBR(unittest.TestCase):
    def test_data_completa(self) -> None:
        self.assertEqual(_data_br("2026-10-14"), "14/10/2026")

    def test_data_com_hora(self) -> None:
        self.assertEqual(_data_br("2026-10-14T18:00:00+00:00"), "14/10/2026")

    def test_vazio(self) -> None:
        self.assertEqual(_data_br(None), "")
        self.assertEqual(_data_br(""), "")

    def test_curto(self) -> None:
        self.assertEqual(_data_br("14/10"), "14/10")


class TestSimNao(unittest.TestCase):
    def test_sim(self) -> None:
        self.assertEqual(_sim_nao(True), "Sim")

    def test_nao(self) -> None:
        self.assertEqual(_sim_nao(False), "Não")

    def test_none(self) -> None:
        self.assertEqual(_sim_nao(None), "—")


if __name__ == "__main__":
    unittest.main()
