import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from core import automatico
from core.automatico import score_hidrologia_estacao


class Consulta:
    def __init__(self, dados):
        self.dados = dados

    def __getattr__(self, _nome):
        return lambda *a, **k: self

    def execute(self):
        return type("R", (), {"data": self.dados})()


class Cliente:
    def __init__(self, estacoes, leituras):
        self.tabelas = {"estacoes": estacoes, "leituras": leituras}

    def table(self, nome):
        return Consulta(self.tabelas[nome])


AGORA = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


class ScoreTest(unittest.TestCase):
    def test_faixas(self):
        self.assertEqual(score_hidrologia_estacao(100, 1000, 1200), 0)
        self.assertEqual(score_hidrologia_estacao(1000, 1000, 1200), 50)
        self.assertEqual(score_hidrologia_estacao(1200, 1000, 1200), 80)
        self.assertEqual(score_hidrologia_estacao(5000, 1000, 1200), 100)


class MotorTest(unittest.TestCase):
    estacao = {"id": 1, "nome": "X", "municipio_id": "1300", "cota_alerta": 1000, "cota_emergencia": 1200}

    def test_leitura_recente_gera_score(self):
        cliente = Cliente(
            [self.estacao],
            [{"nivel_cm": 1100, "data_hora_leitura": "2026-10-06T10:00:00+00:00"}],
        )
        dados = automatico.coletar_hidrologia_por_municipio(cliente, agora=AGORA)
        self.assertAlmostEqual(dados["1300"]["score"], 65.0)

    def test_leitura_antiga_e_ignorada(self):
        cliente = Cliente(
            [self.estacao],
            [{"nivel_cm": 1100, "data_hora_leitura": "2026-10-01T10:00:00+00:00"}],
        )
        self.assertEqual(automatico.coletar_hidrologia_por_municipio(cliente, agora=AGORA), {})

    def test_falha_de_um_municipio_nao_derruba_os_outros(self):
        cliente = Cliente(
            [self.estacao],
            [{"nivel_cm": 1100, "data_hora_leitura": "2026-10-06T10:00:00+00:00"}],
        )
        with patch.object(automatico, "calcular_e_gerar_rascunhos", side_effect=RuntimeError("x")):
            resumo = automatico.executar_motor(cliente, agora=AGORA)
        self.assertEqual(resumo["erros"], 1)


if __name__ == "__main__":
    unittest.main()
