from __future__ import annotations

import unittest
from typing import Any

from collectors.cemaden import coletar as coletar_cemaden
from collectors.cnes import coletar as coletar_cnes
from collectors.ibge import coletar as coletar_ibge
from collectors.inep import coletar as coletar_inep
from collectors.inmet import coletar as coletar_inmet
from collectors.inpe import coletar as coletar_inpe
from collectors.sgb import coletar as coletar_sgb
from collectors.saude import verificar_fontes
from collectors.comum import ConfiguracaoPendenteError


class RespostaSimulada:
    def __init__(self, payload: Any = None, *, texto: str = "") -> None:
        self.payload = payload
        self.text = texto

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class SessaoSimulada:
    def __init__(self, resposta: RespostaSimulada) -> None:
        self.resposta = resposta
        self.chamadas: list[str] = []

    def get(self, url: str, **kwargs: Any) -> RespostaSimulada:
        self.chamadas.append(url)
        return self.resposta


def configuracao_json(
    nome: str = "Fonte simulada",
    *,
    uf: str | None = None,
) -> dict[str, Any]:
    config = {
        "nome": nome,
        "status": "ativo",
        "endpoint": "https://exemplo.invalid/dados",
        "formato": "json",
        "caminho_registros": "dados",
        "campos": {"codigo": "codigo", "valor": "valor"},
        "autenticacao": {"tipo": "sem_autenticacao"},
    }
    if uf:
        config["uf"] = uf
        config["campos"] = {"id_ibge": "id", "nome": "nome"}
        config["caminho_registros"] = ""
    return config


class TestColetoresFontes(unittest.TestCase):
    def test_coletor_inpe_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": 7, "valor": 1}]}))
        resultado = coletar_inpe(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["codigo"], 7)
        self.assertEqual(resultado[0]["fonte"], "Fonte simulada")

    def test_coletor_inmet_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": "A", "valor": 25}]}))
        resultado = coletar_inmet(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["valor"], 25)

    def test_coletor_sgb_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": "S", "valor": "alerta"}]}))
        resultado = coletar_sgb(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["valor"], "alerta")

    def test_coletor_cemaden_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": "C", "valor": 2}]}))
        resultado = coletar_cemaden(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["codigo"], "C")

    def test_coletor_cnes_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": "U", "valor": "ubs"}]}))
        resultado = coletar_cnes(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["valor"], "ubs")

    def test_coletor_inep_com_resposta_json_simulada(self) -> None:
        sessao = SessaoSimulada(RespostaSimulada({"dados": [{"codigo": "E", "valor": "escola"}]}))
        resultado = coletar_inep(configuracao_json(), sessao=sessao)
        self.assertEqual(resultado[0]["valor"], "escola")

    def test_coletor_ibge_normaliza_codigos_e_municipios_simulados(self) -> None:
        config = configuracao_json("IBGE simulado", uf="AM")
        sessao = SessaoSimulada(
            RespostaSimulada(
                [
                    {"id": 1302405, "nome": "Lábrea"},
                    {"id": 1300631, "nome": "Beruri"},
                ]
            )
        )
        resultado = coletar_ibge(config, sessao=sessao)
        self.assertEqual(
            [(item["id_ibge"], item["nome"], item["uf"]) for item in resultado],
            [("1302405", "Lábrea", "AM"), ("1300631", "Beruri", "AM")],
        )
        self.assertEqual([item["fonte"] for item in resultado], ["IBGE simulado"] * 2)
        self.assertTrue(all(item["coletado_em"].endswith("+00:00") for item in resultado))

    def test_coletor_csv_simulado_normaliza_cabecalho(self) -> None:
        from collectors.comum import coletar_configurado

        config = configuracao_json()
        config.update(
            formato="csv",
            caminho_registros="",
            campos={"codigo": "codigo_fonte", "valor": "medida"},
        )
        sessao = SessaoSimulada(
            RespostaSimulada(texto="codigo_fonte,medida\nQ,17\n")
        )
        resultado = coletar_configurado("inpe", config, sessao=sessao)
        self.assertEqual(resultado[0]["codigo"], "Q")
        self.assertEqual(resultado[0]["valor"], "17")

    def test_fontes_pendentes_nao_chamam_endpoint_e_isolam_falhas(self) -> None:
        chamada: list[str] = []

        def falha(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            chamada.append("fonte-a")
            raise ConfiguracaoPendenteError("pendente")

        def sucesso(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            chamada.append("fonte-b")
            return [{"id": 1}]

        resultados = verificar_fontes(
            configuracoes={
                "a": {"nome": "Fonte A"},
                "b": {"nome": "Fonte B"},
            },
            coletores={"a": falha, "b": sucesso},
        )
        self.assertEqual(chamada, ["fonte-a", "fonte-b"])
        self.assertEqual(resultados["a"]["status"], "pendente_confirmacao")
        self.assertEqual(resultados["b"]["status"], "operacional")
        self.assertEqual(resultados["b"]["registros"], 1)


if __name__ == "__main__":
    unittest.main()
