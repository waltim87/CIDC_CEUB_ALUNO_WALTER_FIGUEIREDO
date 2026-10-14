from __future__ import annotations

import unittest
from datetime import date, timedelta
from typing import Any

from collectors import marcadores


def xml_serie(codigo: str, mes_inicial: date, meses: int, cota: callable) -> str:
    linhas = []
    for m in range(meses):
        ano = mes_inicial.year + (mes_inicial.month - 1 + m) // 12
        mes = (mes_inicial.month - 1 + m) % 12 + 1
        cotas = "".join(f"<Cota{d:02d}>{cota(ano, mes, d)}</Cota{d:02d}>" for d in range(1, 29))
        linhas.append(
            f"<SerieHistorica><EstacaoCodigo>{codigo}</EstacaoCodigo><NivelConsistencia>2</NivelConsistencia>"
            f"<DataHora>{ano}-{mes:02d}-01 00:00:00</DataHora>{cotas}</SerieHistorica>"
        )
    return f"<DataTable><DocumentElement>{''.join(linhas)}</DocumentElement></DataTable>"


class Resposta:
    def __init__(self, texto: str, status: int = 200) -> None:
        self.text, self.status_code = texto, status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SessaoAna:
    def __init__(self, serie: str, telemetria_nivel: float, status_serie: int = 200) -> None:
        self.serie, self.nivel, self.status = serie, telemetria_nivel, status_serie

    def get(self, url: str, **kwargs: Any) -> Resposta:
        if url.endswith("HidroSerieHistorica"):
            return Resposta(self.serie, self.status)
        return Resposta(
            "<DataTable><DadosHidrometereologicos><Nivel>%s</Nivel></DadosHidrometereologicos></DataTable>"
            % self.nivel
        )


def cota_senoidal(ano: int, mes: int, dia: int) -> float:
    # Cheia em maio (1000 cm), seca em outubro (300 cm); um pico absurdo em 2010.
    if (ano, mes, dia) == (2010, 3, 10):
        return 9999
    return {1: 700, 2: 800, 3: 900, 4: 980, 5: 1000, 6: 950, 7: 800, 8: 600, 9: 400,
            10: 300, 11: 450, 12: 600}[mes]


class TestMarcadores(unittest.TestCase):
    def test_calcula_extremos_descarta_pico_e_confere_regua(self) -> None:
        serie = xml_serie("1", date(2009, 1, 1), 36, cota_senoidal)
        resultado = marcadores.calcular_marcadores("1", SessaoAna(serie, telemetria_nivel=600))
        self.assertEqual(resultado["cheia_historica_cm"], 1000)
        self.assertEqual(resultado["seca_historica_cm"], 300)
        self.assertIn("régua conferida", resultado["historico_fonte"])

    def test_regua_divergente_nao_gera_marcador(self) -> None:
        serie = xml_serie("1", date(2009, 1, 1), 36, cota_senoidal)
        self.assertIsNone(marcadores.calcular_marcadores("1", SessaoAna(serie, telemetria_nivel=5000)))

    def test_ignora_anos_antes_de_1990(self) -> None:
        serie = xml_serie("1", date(1985, 1, 1), 24, lambda a, m, d: 5)
        serie += ""
        self.assertIsNone(marcadores.calcular_marcadores("1", SessaoAna(serie, telemetria_nivel=5)))

    def test_servico_fora_do_ar_levanta_erro_especifico(self) -> None:
        with self.assertRaises(marcadores.SerieIndisponivelError):
            marcadores.cotas_diarias("1", SessaoAna("erro", 0, status_serie=500))


class Consulta:
    def __init__(self, cliente: "Cliente", tabela: str) -> None:
        self.cliente, self.tabela = cliente, tabela
        self.valores: dict | None = None

    def __getattr__(self, nome: str) -> Any:
        if nome == "not_":
            return self
        return lambda *a, **k: self._encadear(nome, a)

    def _encadear(self, nome: str, args: tuple) -> "Consulta":
        if nome == "update":
            self.valores = args[0]
        if nome == "eq" and self.valores is not None:
            self.cliente.atualizacoes.append((args[1], self.valores))
        return self

    def execute(self) -> Any:
        return type("R", (), {"data": self.cliente.pendentes if self.valores is None else []})()


class Cliente:
    def __init__(self, pendentes: list[dict]) -> None:
        self.pendentes, self.atualizacoes = pendentes, []

    def table(self, nome: str) -> Consulta:
        return Consulta(self, nome)


class TestPreencherPendentes(unittest.TestCase):
    def test_para_quando_a_ana_esta_fora_do_ar(self) -> None:
        cliente = Cliente([{"id": "a", "codigo_oficial": "1"}, {"id": "b", "codigo_oficial": "2"}])
        resumo = marcadores.preencher_pendentes(cliente, sessao=SessaoAna("", 0, status_serie=500))
        self.assertEqual(resumo["preenchidas"], 0)
        self.assertEqual(cliente.atualizacoes, [])

    def test_grava_marcadores_e_registra_sem_marcador(self) -> None:
        serie = xml_serie("1", date(2009, 1, 1), 36, cota_senoidal)
        cliente = Cliente([{"id": "a", "codigo_oficial": "1"}])
        resumo = marcadores.preencher_pendentes(cliente, sessao=SessaoAna(serie, telemetria_nivel=600))
        self.assertEqual(resumo["preenchidas"], 1)
        self.assertEqual(cliente.atualizacoes[0][1]["seca_historica_cm"], 300)

        cliente = Cliente([{"id": "b", "codigo_oficial": "2"}])
        resumo = marcadores.preencher_pendentes(cliente, sessao=SessaoAna(serie, telemetria_nivel=5000))
        self.assertEqual(resumo["sem_marcador"], 1)
        self.assertTrue(cliente.atualizacoes[0][1]["historico_fonte"].startswith("sem marcador"))

    def test_nao_refaz_estacao_ja_avaliada_sem_marcador(self) -> None:
        cliente = Cliente([{"id": "b", "codigo_oficial": "2", "historico_fonte": "sem marcador confiável em 14/10/2026"}])
        resumo = marcadores.preencher_pendentes(cliente, sessao=SessaoAna("", 0, status_serie=500))
        self.assertEqual(resumo["pendentes"], 0)


if __name__ == "__main__":
    unittest.main()
