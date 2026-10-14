from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest import mock

from core import llm
from core.robo import (
    analisar_estacao,
    carregar_config,
    consolidar_municipio,
    executar_robo,
    texto_modelo_fixo,
)

AGORA = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
CFG = carregar_config()
ESTACAO = {"nome": "BERURI", "codigo_oficial": "13990000", "rio": "Purus"}


def serie(niveis_por_hora: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """[(horas_atras, nivel)] -> leituras."""
    return [
        {"data_hora_leitura": (AGORA - timedelta(hours=h)).isoformat(), "nivel_cm": n}
        for h, n in niveis_por_hora
    ]


class TestAnaliseEstacao(unittest.TestCase):
    def test_descida_rapida_gera_alerta(self) -> None:
        resultado = analisar_estacao(ESTACAO, serie([(24.5, 960), (0.5, 925)]), CFG, agora=AGORA)
        self.assertEqual(resultado["direcao"], "descendo")
        self.assertEqual(resultado["variacao_24h_cm"], -35.0)
        self.assertEqual(resultado["sinal"], "alerta")

    def test_nivel_estavel_e_normal(self) -> None:
        resultado = analisar_estacao(ESTACAO, serie([(24, 900), (1, 901)]), CFG, agora=AGORA)
        self.assertEqual(resultado["direcao"], "estavel")
        self.assertEqual(resultado["sinal"], "normal")

    def test_leitura_atrasada_vira_sem_dados_e_nao_normal(self) -> None:
        resultado = analisar_estacao(ESTACAO, serie([(30, 900), (9, 901)]), CFG, agora=AGORA)
        self.assertEqual(resultado["sinal"], "sem_dados")

    def test_sem_leituras(self) -> None:
        self.assertEqual(analisar_estacao(ESTACAO, [], CFG, agora=AGORA)["sinal"], "sem_dados")

    def test_cota_de_emergencia_eleva_para_alto(self) -> None:
        estacao = {**ESTACAO, "cota_alerta": 800, "cota_emergencia": 900}
        resultado = analisar_estacao(estacao, serie([(24, 905), (1, 905)]), CFG, agora=AGORA)
        self.assertEqual(resultado["sinal"], "alto")

    MARCADORES = {
        "seca_historica_cm": 254, "seca_historica_data": "2024-10-11",
        "cheia_historica_cm": 2235.5, "cheia_historica_data": "2015-06-24",
    }

    def _faixa(self, nivel: float) -> dict[str, Any]:
        estacao = {**ESTACAO, **self.MARCADORES}
        return analisar_estacao(estacao, serie([(24, nivel), (1, nivel)]), CFG, agora=AGORA)

    def test_perto_da_seca_recorde_gera_alerta_com_motivo(self) -> None:
        resultado = self._faixa(400)  # (400-254)/(2235.5-254) = 7,4%
        self.assertEqual(resultado["posicao_pct"], 7.4)
        self.assertEqual(resultado["sinal"], "alerta")
        self.assertIn("seca recorde de 254 cm em 11/10/2024", resultado["motivos"][0])

    def test_faixa_de_atencao_e_faixa_usual(self) -> None:
        self.assertEqual(self._faixa(600)["sinal"], "atencao")  # 17,5%
        self.assertEqual(self._faixa(1200)["sinal"], "normal")  # 47,7%

    def test_perto_da_cheia_recorde_tambem_alerta(self) -> None:
        self.assertEqual(self._faixa(2100)["sinal"], "alerta")  # 93,2%

    def test_abaixo_da_seca_recorde_e_alto(self) -> None:
        resultado = self._faixa(240)
        self.assertEqual(resultado["sinal"], "alto")
        self.assertIn("abaixo da seca recorde", resultado["motivos"][0])

    def test_sem_marcadores_nao_inventa_posicao(self) -> None:
        resultado = analisar_estacao(ESTACAO, serie([(24, 400), (1, 400)]), CFG, agora=AGORA)
        self.assertIsNone(resultado["posicao_pct"])
        self.assertEqual(resultado["sinal"], "normal")


class TestConsolidacao(unittest.TestCase):
    def test_municipio_assume_o_pior_sinal_e_texto_cita_fontes(self) -> None:
        a = analisar_estacao(ESTACAO, serie([(24.5, 960), (0.5, 925)]), CFG, agora=AGORA)
        b = analisar_estacao({**ESTACAO, "nome": "ARUMÃ"}, [], CFG, agora=AGORA)
        resultado = consolidar_municipio({"id_ibge": "1300631", "nome": "Beruri", "populacao": 20718}, [a, b])
        self.assertEqual(resultado["sinal"], "alerta")
        texto = texto_modelo_fixo(resultado)
        self.assertIn("925.0 cm", texto)
        self.assertIn("sem validação oficial", texto)


class TestLlm(unittest.TestCase):
    FATOS = {"municipio": "Beruri", "estacoes": [{"nivel_cm": 925.0, "variacao_24h_cm": -35.0}]}

    def test_aceita_texto_com_numeros_dos_fatos(self) -> None:
        self.assertTrue(llm.texto_respeita_fatos("Nível 925 cm, caindo 35,0 cm em 24 h.", self.FATOS | {"h": 24}))

    def test_rejeita_numero_inventado(self) -> None:
        self.assertFalse(llm.texto_respeita_fatos("Nível deve chegar a 800 cm amanhã.", self.FATOS))

    def test_sem_chave_usa_modelo_fixo(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(llm.gerar_texto(self.FATOS, "fixo", modelo="m"), ("fixo", "modelo_fixo", None))

    def test_texto_inventado_da_ia_cai_no_modelo_fixo(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}):
            resultado = llm.gerar_texto(
                self.FATOS, "fixo", modelo="m", chamador=lambda *a, **k: "Subirá 999 cm."
            )
        self.assertEqual(resultado[1], "modelo_fixo")

    def test_falha_da_api_cai_no_modelo_fixo(self) -> None:
        def quebra(*_: Any, **__: Any) -> str:
            raise TimeoutError

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}):
            self.assertEqual(llm.gerar_texto(self.FATOS, "fixo", modelo="m", chamador=quebra)[1], "modelo_fixo")

    def test_texto_valido_da_ia_e_aceito(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}):
            resultado = llm.gerar_texto(
                self.FATOS, "fixo", modelo="m", chamador=lambda *a, **k: "Beruri: nível 925 cm."
            )
        self.assertEqual(resultado, ("Beruri: nível 925 cm.", "ia", "m"))


class Consulta:
    def __init__(self, cliente: "ClienteFalso", tabela: str) -> None:
        self.cliente, self.tabela, self.filtros = cliente, tabela, {}

    def select(self, *_: Any) -> "Consulta":
        return self

    def __getattr__(self, nome: str) -> Any:
        if nome == "not_":
            return self
        return lambda *args, **kwargs: self._filtro(nome, args)

    def _filtro(self, nome: str, args: tuple) -> "Consulta":
        if nome == "eq":
            self.filtros[args[0]] = args[1]
        return self

    def insert(self, linha: dict[str, Any]) -> "Consulta":
        self.cliente.inseridos.append(linha)
        return self

    def execute(self) -> Any:
        dados = self.cliente.dados.get(self.tabela, [])
        if "estacao_id" in self.filtros:
            dados = [d for d in dados if d["estacao_id"] == self.filtros["estacao_id"]]
        return type("R", (), {"data": dados})()


class ClienteFalso:
    def __init__(self, dados: dict[str, list]) -> None:
        self.dados, self.inseridos = dados, []

    def table(self, nome: str) -> Consulta:
        return Consulta(self, nome)


class TestExecucaoRobo(unittest.TestCase):
    def test_grava_uma_analise_por_municipio_com_fontes(self) -> None:
        leituras = [{"estacao_id": "e1", **l} for l in serie([(24.5, 960), (0.5, 925)])]
        cliente = ClienteFalso(
            {
                "estacoes": [{**ESTACAO, "id": "e1", "municipio_id": "1300631", "latitude": -3.9, "longitude": -61.4}],
                "municipios": [{"id_ibge": "1300631", "nome": "Beruri", "populacao": 20718}],
                "leituras": leituras,
            }
        )
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            resumo = executar_robo(cliente, agora=AGORA)
        self.assertEqual(
            resumo, {"municipios": 1, "ia": 0, "modelo_fixo": 1, "alertas": 1, "erros": 0}
        )
        linha, alerta = cliente.inseridos
        self.assertEqual(linha["sinal"], "alerta")
        self.assertEqual(alerta["status"], "rascunho")
        self.assertEqual(alerta["classe"], "Alerta")
        self.assertEqual(linha["fontes_json"][0]["nome"], "ANA estação 13990000")
        self.assertIsNotNone(linha["data_hora_leitura_referencia"])


    def test_nao_repete_alerta_dentro_da_janela(self) -> None:
        leituras = [{"estacao_id": "e1", **l} for l in serie([(24.5, 960), (0.5, 925)])]
        cliente = ClienteFalso(
            {
                "estacoes": [{**ESTACAO, "id": "e1", "municipio_id": "1300631"}],
                "municipios": [{"id_ibge": "1300631", "nome": "Beruri"}],
                "leituras": leituras,
                "alertas": [{"id": "existente"}],
            }
        )
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            resumo = executar_robo(cliente, agora=AGORA)
        self.assertEqual(resumo["alertas"], 0)
        self.assertEqual(len(cliente.inseridos), 1)


class TestRelatorioRobo(unittest.TestCase):
    def test_gera_pdf_com_marcadores(self) -> None:
        from core.relatorio_robo import gerar_relatorio_robo, linhas_estacoes

        estacao = analisar_estacao(
            {**ESTACAO, **TestAnaliseEstacao.MARCADORES}, serie([(24, 400), (1, 400)]), CFG, agora=AGORA
        )
        analises = {"1300631": {"sinal": "alerta", "direcao": "estavel", "texto": "Beruri: alerta.",
                                "gerado_em": AGORA.isoformat(), "estacoes_json": [estacao]}}
        linhas = linhas_estacoes(analises, {"1300631": "Beruri/AM"})
        self.assertEqual(linhas[0]["Seca recorde (cm)"], "254 (11/10/2024)")
        self.assertTrue(gerar_relatorio_robo(analises, {"1300631": "Beruri/AM"}).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
