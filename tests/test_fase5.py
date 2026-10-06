import csv
import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.indicador import calcular_indicador, minutos_leitura_emissao
from core.relatorios import gerar_csv, gerar_pdf


def alerta(leitura, emissao):
    return {
        "emitido_em": emissao,
        "indices": {"data_hora_leitura_referencia": leitura},
    }


class IndicadorTest(unittest.TestCase):
    def test_minutos(self):
        a = alerta("2026-10-01T10:00:00+00:00", "2026-10-01T10:12:30+00:00")
        self.assertAlmostEqual(minutos_leitura_emissao(a), 12.5)

    def test_embutido_como_lista(self):
        a = {
            "emitido_em": "2026-10-01T10:05:00Z",
            "indices": [{"data_hora_leitura_referencia": "2026-10-01T10:00:00Z"}],
        }
        self.assertEqual(minutos_leitura_emissao(a), 5)

    def test_dados_ausentes_ou_inconsistentes_nao_entram(self):
        self.assertIsNone(minutos_leitura_emissao(alerta(None, "2026-10-01T10:00:00Z")))
        self.assertIsNone(
            minutos_leitura_emissao(
                alerta("2026-10-01T10:10:00Z", "2026-10-01T10:00:00Z")
            )
        )

    def test_resumo_e_meta(self):
        resumo = calcular_indicador(
            [
                alerta("2026-10-01T10:00:00Z", "2026-10-01T10:08:00Z"),
                alerta("2026-10-01T11:00:00Z", "2026-10-01T11:10:00Z"),
                alerta(None, "2026-10-01T12:00:00Z"),
            ]
        )
        self.assertEqual(resumo["alertas_medidos"], 2)
        self.assertEqual(resumo["alertas_sem_dados"], 1)
        self.assertEqual(resumo["media_minutos"], 9.0)
        self.assertTrue(resumo["meta_atingida"])

    def test_sem_medidas_nao_inventa_media(self):
        resumo = calcular_indicador([])
        self.assertIsNone(resumo["media_minutos"])
        self.assertIsNone(resumo["meta_atingida"])


class RelatoriosTest(unittest.TestCase):
    def test_csv_com_bom_e_sem_formulas(self):
        dados = gerar_csv([{"a": "=1+1", "b": "São"}], ["a", "b"])
        self.assertTrue(dados.startswith("\ufeff".encode("utf-8")))
        linhas = list(csv.reader(io.StringIO(dados.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(linhas[1], ["'=1+1", "São"])

    def test_pdf_valido(self):
        pdf = gerar_pdf("Teste", [{"a": "Maré ç"}], ["a"], resumo={"x": 1})
        self.assertTrue(pdf.startswith(b"%PDF"))


class ApiTest(unittest.TestCase):
    def test_saude_e_erro_isolado(self):
        from api.main import app

        cliente = TestClient(app)
        self.assertEqual(cliente.get("/saude").status_code, 200)
        with patch("api.main._cliente", side_effect=RuntimeError("x")):
            resposta = cliente.get("/alertas")
        self.assertEqual(resposta.status_code, 503)
        self.assertNotIn("x", resposta.text.replace("indisponível", ""))


class SituacaoMunicipalTest(unittest.TestCase):
    MUNICIPIOS = {
        "1": {"nome": "Beta", "uf": "AM"},
        "2": {"nome": "Alfa", "uf": "AM"},
        "3": {"nome": "Gama", "uf": "PA"},
    }

    def test_uma_linha_por_municipio_e_ultimo_indice(self):
        from core.relatorios import montar_situacao_municipal

        indices = [
            {"municipio_id": "1", "classe": "Alto", "score_total": 70, "fontes_json": [{"nome": "ANA"}]},
            {"municipio_id": "1", "classe": "Normal", "score_total": 10, "fontes_json": []},
        ]
        alertas = [{"municipio_id": "2", "classe": "Alerta", "status": "enviado"}]
        linhas = montar_situacao_municipal(self.MUNICIPIOS, indices, alertas)
        self.assertEqual(len(linhas), 3)
        self.assertEqual(linhas[0]["Município"], "Beta")
        self.assertEqual(linhas[0]["Classe"], "Alto")
        self.assertEqual(linhas[0]["Fontes"], "ANA")
        sem = {l["Município"]: l for l in linhas[1:]}
        self.assertEqual(sem["Alfa"]["Classe"], "Sem índice")
        self.assertIsNone(sem["Alfa"]["Índice"])
        self.assertEqual(sem["Alfa"]["Último alerta"], "Alerta (enviado)")
        self.assertEqual(sem["Gama"]["Último alerta"], "Nenhum")

    def test_resumo_por_classe(self):
        from core.relatorios import montar_situacao_municipal, resumo_por_classe

        linhas = montar_situacao_municipal(self.MUNICIPIOS, [], [])
        resumo = resumo_por_classe(linhas)
        self.assertEqual(resumo["Total de municípios"], 3)
        self.assertEqual(resumo["Municípios — Sem índice"], 3)


class RelatorioDetalhadoTest(unittest.TestCase):
    def test_detalhes_agregados_por_municipio(self):
        from core.relatorios import (
            COLUNAS_DETALHADAS, detalhar_situacao, gerar_csv, gerar_pdf,
            montar_situacao_municipal, totais_detalhados, COLUNAS_PDF_DETALHADO,
        )

        municipios = {"1": {"nome": "Alfa", "uf": "AM"}, "2": {"nome": "Beta", "uf": "AM"}}
        indices = [{"municipio_id": "1", "classe": "Alto", "score_total": 70,
                    "score_hidrologia": 80, "score_populacao": 40}]
        alertas = [{"id": "a1", "municipio_id": "1", "classe": "Alto", "status": "enviado"}]
        dados = {
            "municipios": [{"id_ibge": "1", "calha": "Purus", "populacao": 1000}],
            "comunidades": [{"id": "c1", "municipio_id": "1", "populacao_estimada": 300}],
            "estacoes": [{"id": "e1", "municipio_id": "1"}],
            "leituras": [{"estacao_id": "e1", "data_hora_leitura": "2026-10-01", "nivel_cm": 900, "chuva_mm": 2}],
            "infra": [{"tipo": "ubs", "municipio_id": "1"}, {"tipo": "porto", "municipio_id": "1"}],
            "abrigos": [{"municipio_id": "1", "capacidade": 100, "ocupacao": 25}],
            "recursos": [{"municipio_id": "1", "tipo": "agua", "quantidade": 50}],
            "afetados": [{"comunidade_id": "c1", "familias": 5, "pessoas": 20}],
            "acoes": [{"alerta_id": "a1", "status": "pendente"}, {"alerta_id": "a1", "status": "concluida"}],
            "situacao": [{"municipio_id": "1", "data": "2026-10-01", "situacao": "alerta"}],
            "focos": [{"municipio_id": "1"}],
        }
        base = montar_situacao_municipal(municipios, indices, alertas)
        linhas = detalhar_situacao(base, indices, alertas, dados)
        alfa = next(l for l in linhas if l["Município"] == "Alfa")
        beta = next(l for l in linhas if l["Município"] == "Beta")
        self.assertEqual(alfa["População"], 1000)
        self.assertEqual(alfa["Maior componente"], "Hidrologia")
        self.assertEqual(alfa["Pessoas afetadas"], 20)
        self.assertEqual(alfa["Nível último (cm)"], 900)
        self.assertEqual(alfa["Unidades de saúde"], 1)
        self.assertEqual(alfa["Outra infraestrutura"], 1)
        self.assertEqual(alfa["Ocupação (%)"], 25.0)
        self.assertEqual(alfa["Água"], 50)
        self.assertEqual(alfa["Tarefas pendentes"], 1)
        self.assertEqual(alfa["Tarefas concluídas"], 1)
        self.assertEqual(alfa["Situação oficial"], "alerta")
        self.assertEqual(beta["Situação oficial"], "Não informada")
        self.assertEqual(beta["Comunidades"], 0)
        self.assertIsNone(beta["Ocupação (%)"])
        self.assertEqual(totais_detalhados(linhas)["Pessoas afetadas registradas"], 20)
        self.assertTrue(gerar_csv(linhas, COLUNAS_DETALHADAS).startswith(b"\xef\xbb\xbf"))
        self.assertTrue(gerar_pdf("T", linhas, COLUNAS_PDF_DETALHADO, resumo=totais_detalhados(linhas)).startswith(b"%PDF"))

    def test_carregamento_isola_falha_de_tabela(self):
        from core.relatorios import carregar_dados_relatorio

        class Cliente:
            def table(self, nome):
                if nome == "focos_calor":
                    raise RuntimeError("sem permissão")
                return self

            def select(self, *_): return self
            def order(self, *_, **__): return self
            def limit(self, *_): return self
            def execute(self):
                class R: data = [{"x": 1}]
                return R()

        dados, avisos = carregar_dados_relatorio(Cliente())
        self.assertEqual(dados["focos"], [])
        self.assertEqual(len(avisos), 1)
        self.assertEqual(dados["abrigos"], [{"x": 1}])


if __name__ == "__main__":
    unittest.main()
