"""Ocorrências: ordem da fila, indicadores e tempo de atendimento."""

import unittest
from datetime import datetime, timezone

from app.ocorrencias import duracao, indicadores, linhas_relatorio, ordenar_fila

AGORA = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)


def oc(n, prioridade, status, aberta, resolvida=None, **extra):
    return {"id": str(n), "numero": n, "prioridade": prioridade, "status": status, "tipo": "resgate",
            "titulo": f"Caso {n}", "aberta_em": aberta, "resolvida_em": resolvida, **extra}


CASOS = [
    oc(1, "media", "aberta", "2026-10-14T10:00:00+00:00"),
    oc(2, "critica", "atribuida", "2026-10-14T16:00:00+00:00", equipe_funcao="agente_campo", pessoas_envolvidas=4),
    oc(3, "critica", "aberta", "2026-10-14T15:00:00+00:00"),
    oc(4, "alta", "resolvida", "2026-10-14T08:00:00+00:00", "2026-10-14T10:30:00+00:00"),
    oc(5, "baixa", "resolvida", "2026-10-14T09:00:00+00:00", "2026-10-14T09:30:00+00:00"),
]


class TestOcorrencias(unittest.TestCase):
    def test_fila_mais_grave_e_mais_antiga_primeiro(self) -> None:
        self.assertEqual([o["numero"] for o in ordenar_fila(CASOS)], [3, 2, 4, 1, 5])

    def test_indicadores(self) -> None:
        k = indicadores(CASOS)
        self.assertEqual((k["abertas"], k["graves"], k["sem_equipe"], k["pessoas"]), (3, 2, 2, 4))
        self.assertEqual(k["tempo_medio"], "1 h 30 min")   # (150 + 30) / 2 minutos

    def test_duracao(self) -> None:
        self.assertEqual(duracao("2026-10-14T17:15:00+00:00", agora=AGORA), "45 min")
        self.assertEqual(duracao("2026-10-14T08:00:00Z", "2026-10-14T10:05:00Z"), "2 h 05 min")
        self.assertEqual(duracao("2026-10-10T18:00:00+00:00", agora=AGORA), "4 dias")
        self.assertEqual(duracao(None), "")

    def test_relatorio(self) -> None:
        linha = linhas_relatorio([CASOS[1]])[0]
        self.assertEqual((linha["Prioridade"], linha["Tipo"], linha["Situação"]), ("Crítica", "Resgate de pessoas", "Equipe designada"))
        self.assertEqual(linha["Aberta em"], "14/10 12:00")


if __name__ == "__main__":
    unittest.main()
