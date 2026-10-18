"""Calendário: nível medido e status atual de cada estação."""

import unittest
from datetime import datetime, timezone

from app.calendario_risco import status_atual

AGORA = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
ESTACAO = {"id": "e1", "codigo_oficial": "13880000", "nome": "LÁBREA"}


class TestStatusAtual(unittest.TestCase):
    def test_usa_a_analise_do_robo(self) -> None:
        analise = {"13880000": {"codigo": "13880000", "sinal": "alerta", "nivel_cm": 1712.4, "posicao_pct": 81.6,
                                "data_hora_leitura": "2026-10-18T15:00:00+00:00"}}
        s = status_atual(ESTACAO, analise, {}, AGORA)
        self.assertEqual((s["Nível atual (cm)"], s["Status atual"], s["Posição seca→cheia (%)"], s["Medido em"]),
                         (1712, "🟠 Alerta", 82, "18/10 11:00"))

    def test_sem_analise_mostra_a_leitura_sem_inventar_status(self) -> None:
        leituras = {"e1": {"nivel_cm": 950, "data_hora_leitura": "2026-10-18T16:00:00+00:00"}}
        s = status_atual(ESTACAO, {}, leituras, AGORA)
        self.assertEqual((s["Nível atual (cm)"], s["Status atual"], s["Posição seca→cheia (%)"]),
                         (950, "⚪ Medido (sem análise do robô)", None))

    def test_leitura_antiga_e_sem_leitura(self) -> None:
        leituras = {"e1": {"nivel_cm": 950, "data_hora_leitura": "2026-10-17T01:00:00+00:00"}}
        self.assertIn("leitura antiga", status_atual(ESTACAO, {}, leituras, AGORA)["Status atual"])
        self.assertEqual(status_atual(ESTACAO, {}, {}, AGORA)["Status atual"], "⚪ Sem leitura")


if __name__ == "__main__":
    unittest.main()
