"""Testes da B7: lições aprendidas."""

from __future__ import annotations

import unittest

from app.licoes_aprendidas import _data_br, _hora_br, _sim_nao


class TestDataBR(unittest.TestCase):
    def test_data_completa(self) -> None:
        self.assertEqual(_data_br("2026-10-14"), "14/10/2026")

    def test_vazio(self) -> None:
        self.assertEqual(_data_br(None), "")


class TestHoraBR(unittest.TestCase):
    def test_hora_completa(self) -> None:
        self.assertEqual(_hora_br("2026-10-14T18:30:00+00:00"), "14/10 18:30")

    def test_vazio(self) -> None:
        self.assertEqual(_hora_br(None), "")


class TestSimNao(unittest.TestCase):
    def test_sim_nao_none(self) -> None:
        self.assertEqual(_sim_nao(True), "Sim")
        self.assertEqual(_sim_nao(False), "Não")
        self.assertEqual(_sim_nao(None), "—")


if __name__ == "__main__":
    unittest.main()
