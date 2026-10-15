"""Ajuda humanitária: quem está sem receber e itens do formulário."""

import unittest
from datetime import datetime, timezone

from app.ajuda import _numero, familias_sem_item, itens_preenchidos

AGORA = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)


class TestAjuda(unittest.TestCase):
    def test_familias_sem_cesta(self) -> None:
        cobertura = [
            {"familia_id": "a", "ultima_cesta": None},                          # nunca recebeu
            {"familia_id": "b", "ultima_cesta": "2026-10-01T12:00:00+00:00"},   # 13 dias
            {"familia_id": "c", "ultima_cesta": "2026-10-12T12:00:00+00:00"},   # 2 dias
        ]
        self.assertEqual([c["familia_id"] for c in familias_sem_item(cobertura, agora=AGORA)], ["a", "b"])
        self.assertEqual(len(familias_sem_item(cobertura, dias=20, agora=AGORA)), 1)

    def test_so_itens_com_quantidade(self) -> None:
        self.assertEqual(itens_preenchidos({"cesta_basica": 1.0, "agua_potavel": 0.0, "rede": None, "roupas": 3}),
                         {"cesta_basica": 1.0, "roupas": 3.0})

    def test_numero_brasileiro(self) -> None:
        self.assertEqual(_numero(1500), "1.500")
        self.assertEqual(_numero(2.5), "2,5")
        self.assertEqual(_numero(None), "0")


if __name__ == "__main__":
    unittest.main()
