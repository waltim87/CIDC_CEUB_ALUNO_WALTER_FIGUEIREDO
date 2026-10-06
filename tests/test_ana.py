from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from collectors.ana import (
    ConfiguracaoPendenteError,
    coletar,
    normalizar_registros,
)


class RespostaSimulada:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self) -> Any:
        return self.payload


class SessaoSimulada:
    def __init__(self, respostas: dict[str, RespostaSimulada]) -> None:
        self.respostas = respostas
        self.chamadas: list[str] = []

    def get(self, url: str, **kwargs: Any) -> RespostaSimulada:
        codigo = kwargs["params"]["codigo"]
        self.chamadas.append(codigo)
        resposta = self.respostas[codigo]
        if resposta.status >= 400:
            resposta.raise_for_status()
        return resposta


def configuracao_teste() -> dict[str, Any]:
    return {
        "nome": "ANA teste",
        "status": "ativo",
        "endpoint": "mock://ana",
        "parametros": {"codigo": "{codigo_oficial}"},
        "autenticacao": {"tipo": "sem_autenticacao"},
        "resposta": {
            "caminho_registros": "dados",
            "campos": {
                "data_hora_leitura": "instante",
                "nivel_cm": "nivel",
                "vazao": "vazao",
                "chuva_mm": "chuva",
                "tendencia": "tendencia",
            },
        },
        "estacoes": [
            {"codigo_oficial": "TESTE-1"},
            {"codigo_oficial": "TESTE-2"},
        ],
    }


class TestColetorAna(unittest.TestCase):
    def test_normaliza_leitura_preservando_horario_da_fonte(self) -> None:
        registros = [
            {
                "instante": "2026-10-05T12:00:00-03:00",
                "nivel": "125.5",
                "vazao": 33,
                "chuva": None,
                "tendencia": "subindo",
            }
        ]
        coletado_em = datetime(2026, 10, 5, 15, 1, tzinfo=timezone.utc)

        resultado = normalizar_registros(
            registros,
            codigo_estacao="TESTE-1",
            campos=configuracao_teste()["resposta"]["campos"],
            coletado_em=coletado_em,
        )

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["codigo_estacao"], "TESTE-1")
        self.assertEqual(
            resultado[0]["data_hora_leitura"], "2026-10-05T15:00:00+00:00"
        )
        self.assertEqual(resultado[0]["nivel_cm"], 125.5)
        self.assertEqual(resultado[0]["vazao"], 33.0)
        self.assertIsNone(resultado[0]["chuva_mm"])
        self.assertEqual(resultado[0]["coletado_em"], "2026-10-05T15:01:00+00:00")

    def test_remove_duplicatas_da_mesma_estacao_e_instante(self) -> None:
        campos = configuracao_teste()["resposta"]["campos"]
        registro = {
            "instante": "2026-10-05T15:00:00Z",
            "nivel": 1,
            "vazao": None,
            "chuva": None,
            "tendencia": None,
        }
        resultado = normalizar_registros(
            [registro, registro],
            codigo_estacao="TESTE-1",
            campos=campos,
        )
        self.assertEqual(len(resultado), 1)

    def test_rejeita_horario_sem_fuso(self) -> None:
        with self.assertRaisesRegex(ValueError, "fuso horário"):
            normalizar_registros(
                [
                    {
                        "instante": "2026-10-05T15:00:00",
                        "nivel": 1,
                        "vazao": None,
                        "chuva": None,
                        "tendencia": None,
                    }
                ],
                codigo_estacao="TESTE-1",
                campos=configuracao_teste()["resposta"]["campos"],
            )

    def test_coleta_continua_apos_falha_de_uma_estacao(self) -> None:
        config = configuracao_teste()
        sessao = SessaoSimulada(
            {
                "TESTE-1": RespostaSimulada({}, status=500),
                "TESTE-2": RespostaSimulada(
                    {
                        "dados": [
                            {
                                "instante": "2026-10-05T15:00:00Z",
                                "nivel": 95,
                                "vazao": 12,
                                "chuva": 2,
                                "tendencia": "estavel",
                            }
                        ]
                    }
                ),
            }
        )

        resultado = coletar(config, sessao=sessao)

        self.assertEqual(sessao.chamadas, ["TESTE-1", "TESTE-2"])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["codigo_estacao"], "TESTE-2")

    def test_falha_em_todas_as_estacoes_nao_parece_coleta_bem_sucedida(self) -> None:
        config = configuracao_teste()
        sessao = SessaoSimulada(
            {
                "TESTE-1": RespostaSimulada({}, status=500),
                "TESTE-2": RespostaSimulada({}, status=503),
            }
        )

        with self.assertRaisesRegex(RuntimeError, "todas as 2 estações"):
            coletar(config, sessao=sessao)

    def test_nao_consulta_fonte_enquanto_configuracao_estiver_pendente(self) -> None:
        sessao = SessaoSimulada({})
        with self.assertRaises(ConfiguracaoPendenteError):
            coletar(sessao=sessao)
        self.assertEqual(sessao.chamadas, [])


if __name__ == "__main__":
    unittest.main()
