from __future__ import annotations

import unittest
from typing import Any

from collectors import inmet
from core.robo import aplicar_meteorologia, carregar_config, consolidar_municipio, texto_modelo_fixo

AVISOS = {
    "hoje": [{
        "codigo": "urn:oid:2.49.0.0.76.0.2026.1.1", "descricao": "Tempestade", "severidade": "Perigo Potencial",
        "aviso_cor": "#FFFE00", "data_inicio": "2026-10-14T00:00:00.000Z", "hora_inicio": "08:50",
        "data_fim": "2026-10-14T00:00:00.000Z", "hora_fim": "23:59", "encerrado": "False",
        "geocodes": "1302405,3550308,1300706",
        "riscos": "['Chuva entre 20 e 30 mm/h.', 'Ventos intensos (40-60 km/h).']",
        "instrucoes": "['Não se abrigue debaixo de árvores.']",
    }],
    "futuro": [{
        "codigo": "x2", "descricao": "Chuvas Intensas", "severidade": "Perigo", "geocodes": "1302405",
        "data_inicio": "2026-10-15T00:00:00.000Z", "hora_inicio": "00:01", "data_fim": "2026-10-15T00:00:00.000Z",
        "hora_fim": "23:59", "encerrado": "True",
    }],
}
PREVISAO = {"1302405": {
    "14/10/2026": {"manha": {"resumo": "Pancadas de chuva", "temp_max": 37, "temp_min": 24, "int_vento": "Fracos",
                             "dir_vento": "N-NW", "umidade_max": 100, "umidade_min": 40}},
    "18/10/2026": {"resumo": "Chuva isolada", "temp_max": 36, "temp_min": 22},
}}


class Resposta:
    def __init__(self, corpo: Any) -> None:
        self.corpo = corpo

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.corpo


class SessaoOpenMeteo:
    def get(self, url: str, **kwargs: Any) -> Resposta:
        n = len(kwargs["params"]["latitude"].split(","))
        um = {"daily": {"time": ["2026-10-14", "2026-10-15"], "precipitation_sum": [2.0, 120.5],
                        "temperature_2m_max": [36, 35], "temperature_2m_min": [24, 23]}}
        return Resposta([um] * n if n > 1 else um)


class TestColetorInmet(unittest.TestCase):
    def test_avisos_por_municipio_do_am_ignorando_encerrados_e_outros_estados(self) -> None:
        linhas = inmet.avisos_para_linhas(AVISOS, {"1302405", "1300706"})
        self.assertEqual(sorted(l["municipio_id"] for l in linhas), ["1300706", "1302405"])
        aviso = linhas[0]
        self.assertEqual((aviso["descricao"], aviso["severidade"]), ("Tempestade", "Perigo Potencial"))
        self.assertEqual(aviso["inicio"], "2026-10-14T08:50:00-03:00")
        self.assertEqual(aviso["riscos"], "Chuva entre 20 e 30 mm/h. Ventos intensos (40-60 km/h).")

    def test_previsao_por_periodo_e_por_dia(self) -> None:
        linhas = inmet.previsao_para_linhas("1302405", PREVISAO)
        self.assertEqual([(l["data"], l["periodo"]) for l in linhas], [("2026-10-14", "manha"), ("2026-10-18", "dia")])
        self.assertEqual(linhas[0]["vento"], "Fracos N-NW")

    def test_chuva_open_meteo_varios_municipios_em_uma_consulta(self) -> None:
        municipios = [{"id_ibge": "1302405", "latitude": -7.2, "longitude": -64.8},
                      {"id_ibge": "1300706", "latitude": -8.7, "longitude": -67.4}]
        linhas = inmet.chuva_open_meteo(municipios, SessaoOpenMeteo())
        self.assertEqual(len(linhas), 4)
        self.assertEqual(linhas[1]["chuva_prevista_mm"], 120.5)


class TestRoboMeteorologia(unittest.TestCase):
    def test_aviso_inmet_e_chuva_elevam_o_sinal_e_entram_no_texto(self) -> None:
        cfg = carregar_config()
        resultado = consolidar_municipio({"id_ibge": "1302405", "nome": "Lábrea"}, [])
        self.assertEqual(resultado["sinal"], "sem_dados")
        aplicar_meteorologia(
            resultado,
            [{"descricao": "Tempestade", "severidade": "Perigo Potencial", "fim": "2026-10-14T23:59:00-03:00"}],
            [{"data": "2026-10-15", "chuva_prevista_mm": 120.5}],
            cfg,
        )
        self.assertEqual(resultado["sinal"], "alerta")  # 120,5 mm >= 100 mm/dia
        texto = texto_modelo_fixo(resultado)
        self.assertIn("INMET: aviso de Tempestade (Perigo Potencial)", texto)
        self.assertIn("120.5 mm", texto)

    def test_grande_perigo_e_alto(self) -> None:
        resultado = consolidar_municipio({"id_ibge": "1", "nome": "X"}, [])
        aplicar_meteorologia(resultado, [{"descricao": "Chuvas Intensas", "severidade": "Grande Perigo", "fim": None}], [], carregar_config())
        self.assertEqual(resultado["sinal"], "alto")


if __name__ == "__main__":
    unittest.main()
