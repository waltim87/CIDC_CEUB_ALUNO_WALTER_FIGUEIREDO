from __future__ import annotations

import unittest

from collectors import cemaden, inpe, sgb
from core.robo import aplicar_fontes_oficiais, carregar_config, consolidar_municipio

CSV_INPE = (
    "id,lat,lon,data_hora_gmt,satelite,municipio,estado,pais,municipio_id,estado_id,pais_id,"
    "numero_dias_sem_chuva,precipitacao,risco_fogo,bioma,frp\n"
    "a1,  -7.26, -64.80,2026-10-13 15:30:00,AQUA_M-T,LÁBREA,AMAZONAS,Brasil,1302405,13,33,12,0.00,0.91,Amazônia,35.2\n"
    "a2,-10.00,-50.00,2026-10-13 15:30:00,AQUA_M-T,X,PARÁ,Brasil,1500107,15,33,5,0.00,0.50,Amazônia,10.0\n"
    "a3,-7.30,-64.90,2026-10-13 16:00:00,GOES-19,LÁBREA,AMAZONAS,Brasil,1302405,13,33,-999,-999,-999,Amazônia,8.1\n"
)
JSON_CEMADEN = [
    {"idestacao": 6740, "uf": "AM", "codibge": 1302603, "cidade": "MANAUS", "nomeestacao": "Colônia Antônio Aleixo",
     "ultimovalor": 0.2, "datahoraUltimovalor": "14/10/26 21:50", "acc1hr": "-", "acc24hr": 31.4, "acc72hr": 40.1},
    {"idestacao": 1, "uf": "PA", "codibge": 1500107, "nomeestacao": "Fora do AM"},
]
MAPA_SACE = '''
const popupContentamazonas_pm19_s49_sr89 = ` <div>Carregando...</div>
<iframe src="relatorio.php?apenas_grafico=sim&bacia=amazonas&pm=19&s=49&sr=89" style="width: 100%;"></iframe> `;
const popupamazonas_pm19_s49_sr89 = L.popup(popupOptions).setContent(popupContentamazonas_pm19_s49_sr89);
const estacaoamazonas_pm19_s49_sr89 = L.circleMarker([-3.89890, -61.37420], { radius: 7, color: "#333333",
 weight: 1, opacity: 0.7, fillColor: "#FFFF00", fillOpacity: 0.9 }) .addTo(grupoEstacao)
 .bindPopup(popupamazonas_pm19_s49_sr89) .bindTooltip("BE - Beruri", {permanent: false, direction: "top"});
'''
RELATORIO_SACE = '''<h2 style="font-size:1.3rem;">920 Cota (cm)</h2> <p> Última medição: <b>14/10/2026 18:00</b><br />
 Situação: <span class="bolinha" style="background-color: #FFFF00;"></span>Alerta<br /> Beruri<br /> </p>'''


class TestLeitores(unittest.TestCase):
    def test_inpe_so_am_e_valores_ausentes_viram_nulo(self) -> None:
        focos = inpe.focos_do_csv(CSV_INPE)
        self.assertEqual([f["id_inpe"] for f in focos], ["a1", "a3"])
        self.assertEqual((focos[0]["risco_fogo"], focos[0]["dias_sem_chuva"], focos[0]["data_hora"]),
                         (0.91, 12, "2026-10-13T15:30:00+00:00"))
        self.assertIsNone(focos[1]["risco_fogo"])
        self.assertEqual(focos[0]["geom"], "SRID=4326;POINT(-64.8 -7.26)")

    def test_cemaden_converte_traco_em_nulo_e_filtra_am(self) -> None:
        linhas = cemaden.estacoes_do_json(JSON_CEMADEN, {"1302603"})
        self.assertEqual(len(linhas), 1)
        self.assertEqual((linhas[0]["municipio_id"], linhas[0]["acc24h_mm"], linhas[0]["acc1h_mm"]), ("1302603", 31.4, None))
        self.assertEqual(linhas[0]["medido_em"], "2026-10-14T21:50:00+00:00")

    def test_sace_le_mapa_e_relatorio(self) -> None:
        pontos = sgb.pontos_do_mapa(MAPA_SACE)
        self.assertEqual(len(pontos), 1)
        self.assertEqual((pontos[0]["pm"], pontos[0]["nome"], pontos[0]["cor"]), (19, "Beruri", "#FFFF00"))
        self.assertTrue(pontos[0]["link"].endswith("pm=19&s=49&sr=89"))
        dados = sgb.dados_do_relatorio(RELATORIO_SACE)
        self.assertEqual((dados["cota_cm"], dados["situacao"]), (920.0, "Alerta"))
        self.assertEqual(dados["medido_em"], "2026-10-14T18:00:00-04:00")
        municipio = sgb.municipio_mais_proximo(pontos[0], [{"id_ibge": "1300631", "latitude": -3.9, "longitude": -61.37},
                                                           {"id_ibge": "1302603", "latitude": -3.12, "longitude": -60.02}])
        self.assertEqual(municipio, "1300631")


class TestRoboFontesOficiais(unittest.TestCase):
    def test_sace_cemaden_e_inpe_elevam_o_sinal(self) -> None:
        cfg = carregar_config()
        resultado = consolidar_municipio({"id_ibge": "1300631", "nome": "Beruri"}, [])
        aplicar_fontes_oficiais(resultado, {"sace": [{"nome": "Beruri", "situacao": "Alerta", "cota_cm": 920}],
                                            "chuva_24h": 60.0, "focos_24h": 10}, cfg)
        self.assertEqual(resultado["sinal"], "alerta")
        self.assertTrue(any("SGB/SACE" in f for f in resultado["fatores"]))
        self.assertTrue(any("Cemaden" in f for f in resultado["fatores"]))

    def test_muitos_focos_geram_alerta_e_normal_nao_muda(self) -> None:
        cfg = carregar_config()
        resultado = consolidar_municipio({"id_ibge": "1302405", "nome": "Lábrea"}, [])
        aplicar_fontes_oficiais(resultado, {"sace": [{"nome": "X", "situacao": "Normal"}], "focos_24h": 263}, cfg)
        self.assertEqual(resultado["sinal"], "alerta")
        self.assertIn("INPE: 263 focos de calor detectados em 24 h", resultado["fatores"])


if __name__ == "__main__":
    unittest.main()
