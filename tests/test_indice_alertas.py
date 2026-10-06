from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

from core.alertas import gerar_rascunhos, texto_sugerido
from core.indice import (
    IndiceIndisponivelError,
    calcular_indice,
    classificar,
    construir_registro_indice,
    validar_pesos,
)
from core.regras import avaliar_regras, regra_corresponde
from core.motor import calcular_e_gerar_rascunhos

RAIZ = Path(__file__).resolve().parents[1]


class TestIndice(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (RAIZ / "config" / "pesos.yaml").open(encoding="utf-8") as arquivo:
            cls.pesos = yaml.safe_load(arquivo)["pesos"]

    def test_pesos_configuraveis_nao_sao_constantes_do_codigo(self) -> None:
        self.assertEqual(sum(self.pesos.values()), 100)
        validacao = validar_pesos(self.pesos)
        self.assertIsNone(validacao)

    def test_calculo_com_pesos_configurados(self) -> None:
        resultado = calcular_indice(
            {
                "hidrologia": 80,
                "populacao": 40,
                "infraestrutura": 0,
                "logistica": 20,
                "vulnerabilidade": 60,
            },
            pesos=self.pesos,
        )
        esperado = 80 * 0.30 + 40 * 0.25 + 0 * 0.20 + 20 * 0.15 + 60 * 0.10
        self.assertAlmostEqual(resultado["score_total"], esperado)
        self.assertEqual(resultado["classe"], "Alerta")
        self.assertEqual(
            sum(item["peso_percentual_aplicado"] for item in resultado["explicacao"]),
            100,
        )

    def test_componentes_ausentes_sao_excluidos_e_pesos_renormalizados(self) -> None:
        resultado = calcular_indice(
            {"hidrologia": 80, "populacao": 40, "infraestrutura": None},
            pesos=self.pesos,
        )
        self.assertAlmostEqual(resultado["score_total"], (80 * 30 + 40 * 25) / 55)
        self.assertAlmostEqual(
            sum(item["peso_percentual_aplicado"] for item in resultado["explicacao"]),
            100,
        )
        self.assertEqual(len(resultado["explicacao"]), 2)

    def test_sem_componentes_nao_assume_score_zero(self) -> None:
        with self.assertRaises(IndiceIndisponivelError):
            calcular_indice({}, pesos=self.pesos)

    def test_recusa_pesos_que_nao_somam_cem(self) -> None:
        pesos_invalidos = dict(self.pesos)
        pesos_invalidos["hidrologia"] = 29
        with self.assertRaisesRegex(ValueError, "soma dos pesos"):
            calcular_indice({"hidrologia": 10}, pesos=pesos_invalidos)

    def test_recusa_score_fora_do_intervalo(self) -> None:
        with self.assertRaisesRegex(ValueError, "entre 0 e 100"):
            calcular_indice({"hidrologia": 101}, pesos=self.pesos)

    def test_limites_das_classes(self) -> None:
        casos = {
            0: "Normal",
            20: "Normal",
            20.01: "Atenção",
            40: "Atenção",
            40.01: "Alerta",
            60: "Alerta",
            60.01: "Alto",
            80: "Alto",
            80.01: "Crítico",
            100: "Crítico",
        }
        for score, classe in casos.items():
            with self.subTest(score=score):
                self.assertEqual(classificar(score), classe)

    def test_registro_guarda_explicaçao_e_proveniencia(self) -> None:
        registro = construir_registro_indice(
            "1302405",
            {"hidrologia": 80},
            pesos=self.pesos,
            fontes=[{"nome": "Fonte simulada"}],
        )
        self.assertEqual(registro["municipio_id"], "1302405")
        self.assertEqual(registro["score_hidrologia"], 80)
        self.assertEqual(registro["fontes_json"], [{"nome": "Fonte simulada"}])
        self.assertEqual(registro["classe"], "Alto")
        self.assertTrue(registro["explicacao_json"])


class TestRegrasEAlertas(unittest.TestCase):
    def test_motor_exige_fonte_e_horario_com_fuso(self) -> None:
        with self.assertRaisesRegex(ValueError, "ao menos uma fonte"):
            calcular_e_gerar_rascunhos(
                None,
                "1302405",
                {"hidrologia": 50},
                fontes=[],
            )
        with self.assertRaisesRegex(ValueError, "fuso horário"):
            calcular_e_gerar_rascunhos(
                None,
                "1302405",
                {"hidrologia": 50},
                fontes=[
                    {
                        "nome": "Fonte simulada",
                        "data_hora_leitura": "2026-10-05T14:55:00",
                    }
                ],
            )

    def test_comparadores_estruturados_sem_execucao_dinamica(self) -> None:
        self.assertTrue(
            regra_corresponde(
                {"campo": "score_total", "operador": "entre", "valor": [21, 40]},
                {"score_total": 21},
            )
        )
        self.assertFalse(
            regra_corresponde(
                {"campo": "score_total", "operador": "__import__", "valor": 0},
                {"score_total": 99},
            )
        )

    def test_apenas_regras_ativas_correspondentes_sao_retornadas(self) -> None:
        regras = [
            {
                "id": "a",
                "ativa": True,
                "classe": "Alerta",
                "condicao_json": {
                    "campo": "score_total",
                    "operador": "entre",
                    "valor": [41, 60],
                },
            },
            {
                "id": "b",
                "ativa": False,
                "classe": "Crítico",
                "condicao_json": {
                    "campo": "score_total",
                    "operador": "maior_que",
                    "valor": 80,
                },
            },
        ]
        self.assertEqual(
            [regra["id"] for regra in avaliar_regras(regras, {"score_total": 50})],
            ["a"],
        )

    def test_gera_rascunho_com_explicacao_sem_enviar(self) -> None:
        municipio = {"id_ibge": "1302405", "nome": "Lábrea", "uf": "AM"}
        indice: dict[str, Any] = {
            "id": "indice-1",
            "municipio_id": "1302405",
            "score_total": 50,
            "data_hora": "2026-10-05T15:00:00+00:00",
            "data_hora_leitura_referencia": "2026-10-05T14:55:00+00:00",
            "fontes_json": [
                {
                    "nome": "Fonte simulada",
                    "data_hora_leitura": "2026-10-05T14:55:00+00:00",
                }
            ],
            "explicacao_json": [
                {
                    "componente": "hidrologia",
                    "rotulo": "Hidrologia",
                    "score": 80,
                    "peso_percentual_aplicado": 50,
                }
            ],
        }
        regras = [
            {
                "id": "regra-1",
                "ativa": True,
                "classe": "Alerta",
                "condicao_json": {
                    "campo": "score_total",
                    "operador": "entre",
                    "valor": [41, 60],
                },
                "acao_recomendada": "Revisar os dados.",
            }
        ]
        rascunhos = gerar_rascunhos(municipio, indice, regras)
        self.assertEqual(len(rascunhos), 1)
        self.assertEqual(rascunhos[0]["status"], "rascunho")
        self.assertIsNone(rascunhos[0]["canal"])
        self.assertIn("Hidrologia: 80.0/100", rascunhos[0]["texto"])
        self.assertIn("revisão humana obrigatória", rascunhos[0]["texto"])
        self.assertIn("Data/hora da leitura de referência: 2026-10-05T14:55:00+00:00", rascunhos[0]["texto"])
        self.assertIn(
            "Fonte(s): Fonte simulada (2026-10-05T14:55:00+00:00)",
            rascunhos[0]["texto"],
        )

    def test_texto_fixo_usa_somente_dados_informados(self) -> None:
        texto = texto_sugerido(
            {"nome": "Lábrea", "uf": "AM"},
            {"score_total": 55, "data_hora": "hora da leitura"},
            {"classe": "Alerta", "acao_recomendada": "Verificar rota informada."},
        )
        self.assertIn("Lábrea/AM", texto)
        self.assertIn("55.0/100", texto)
        self.assertIn("Verificar rota informada.", texto)
        self.assertIn("componentes não disponíveis", texto)
        self.assertNotIn("10 famílias", texto)


if __name__ == "__main__":
    unittest.main()
