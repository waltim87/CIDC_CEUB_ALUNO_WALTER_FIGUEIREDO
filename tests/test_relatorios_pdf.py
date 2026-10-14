"""Regressões encontradas no teste visual dos relatórios (14/10/2026)."""

import unittest

from core.relatorios import _grafico_barras, _latin1, gerar_csv, gerar_pdf, gerar_pdf_secoes
from core.relatorio_robo import gerar_relatorio_robo


class TestTextoPdf(unittest.TestCase):
    def test_tipografia_vira_equivalente_e_emoji_e_removido(self) -> None:
        # Antes: "Previsão ? Lábrea", "? Incêndio", "40?100", "do sul ?".
        self.assertEqual(_latin1("Previsão — Lábrea"), "Previsão - Lábrea")
        self.assertEqual(_latin1("🔥 Incêndio / fumaça"), "Incêndio / fumaça")
        self.assertEqual(_latin1("40–100"), "40-100")
        self.assertEqual(_latin1("do sul ✔"), "do sul ok")
        self.assertEqual(_latin1("chuva ≥ 50 mm → alerta"), "chuva >= 50 mm -> alerta")
        self.assertNotIn("?", _latin1("🌧️ ⬇️ 🌊 🚫 ❓ texto"))

    def test_acentos_e_simbolos_latin1_sao_mantidos(self) -> None:
        self.assertEqual(_latin1("Ação: m³/s, 38°C, nº 123"), "Ação: m³/s, 38°C, nº 123")
        self.assertEqual(_latin1(None), "")
        self.assertEqual(_latin1("linha 1\nlinha 2"), "linha 1\nlinha 2")


class PdfFalso:
    """Registra as barras desenhadas para conferir a escala."""

    def __init__(self) -> None:
        self.w, self.h, self.l_margin, self.r_margin = 297, 210, 10, 10
        self.y, self.retangulos = 20, []

    def get_y(self):
        return self.y

    def set_xy(self, x, y):
        self.y = y

    def rect(self, x, y, largura, altura, style=None):
        self.retangulos.append(largura)

    def cell(self, *a, **k):
        if k.get("new_y") == "NEXT":
            self.y += 5

    def __getattr__(self, nome):
        return lambda *a, **k: None


class TestGraficos(unittest.TestCase):
    def test_porcentagem_escala_de_0_a_100(self) -> None:
        # Antes: uma estação com 7% aparecia com a barra cheia.
        pdf = PdfFalso()
        _grafico_barras(pdf, "Posição", {"LÁBREA": 7}, escala_maxima=100)
        util = pdf.w - pdf.l_margin - pdf.r_margin - 60 - 20
        self.assertAlmostEqual(pdf.retangulos[0], util * 0.07, places=3)

    def test_sem_escala_usa_o_maior_valor(self) -> None:
        pdf = PdfFalso()
        _grafico_barras(pdf, "Classes", {"A": 10, "B": 5})
        self.assertAlmostEqual(pdf.retangulos[1], pdf.retangulos[0] / 2, places=3)


class TestRelatoriosCompletos(unittest.TestCase):
    LONGO = "Chuva entre 20 e 30 mm/h — ventos intensos; municípios: " + ", ".join(["Lábrea", "Beruri"] * 40)

    def test_pdf_por_menu_com_texto_longo_emoji_e_tabela_larga(self) -> None:
        estreita = [{"Aviso": "🌩️ Tempestade", "Riscos": self.LONGO, "Fim": "14/10 23:59"}]
        larga = [{f"Coluna {i}": f"valor {i} — {self.LONGO[:40]}" for i in range(12)}]
        pdf = gerar_pdf_secoes("Teste", [("Estreita", estreita), ("Larga", larga), ("Vazia", [])],
                               subtitulo="Lábrea/AM", resumo={"Itens": 2})
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_relatorio_estadual_e_do_robo(self) -> None:
        linhas = [{"Município": "Lábrea", "UF": "AM", "Análise": self.LONGO}] * 30
        pdf = gerar_pdf("Estadual", linhas, ["Município", "UF", "Análise"], resumo={"Total": 30},
                        colunas_detalhe=["Município", "UF", "Análise"],
                        graficos=[("Classes", {"Alerta": 2}), ("Posição", {"X": 7}, 100)],
                        analises=[{"Município": "Lábrea", "sinal": "Alerta", "texto": self.LONGO, "gerado_em": "hoje"}])
        self.assertTrue(pdf.startswith(b"%PDF"))
        robo = gerar_relatorio_robo({"1302405": {"sinal": "alerta", "texto": "Lábrea — alerta", "gerado_em": "2026-10-14",
                                                 "estacoes_json": [{"estacao": "LÁBREA", "codigo": "1", "sinal": "alerta",
                                                                    "posicao_pct": 7.0}]}},
                                    {"1302405": "Lábrea/AM"})
        self.assertTrue(robo.startswith(b"%PDF"))

    def test_csv_mantem_texto_completo_e_protege_formula(self) -> None:
        csv = gerar_csv([{"Riscos": self.LONGO, "Valor": "=SOMA(A1)"}], ["Riscos", "Valor"]).decode("utf-8-sig")
        self.assertIn(self.LONGO, csv)
        self.assertIn("'=SOMA(A1)", csv)


if __name__ == "__main__":
    unittest.main()
