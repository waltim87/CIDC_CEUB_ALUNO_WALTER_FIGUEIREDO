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


if __name__ == "__main__":
    unittest.main()
