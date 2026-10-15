"""Plano de contingência: atrasos, resumo por eixo e edição do protocolo."""

import unittest
from datetime import datetime, timezone

from app.plano import atrasada, diferencas_protocolo, linhas_tarefas, resumo_por_eixo

AGORA = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
TAREFAS = [
    {"eixo": "resposta", "status": "pendente", "prazo": "2026-10-14T12:00:00+00:00", "descricao": "Abrir abrigos"},
    {"eixo": "resposta", "status": "em_andamento", "prazo": "2026-10-15T12:00:00+00:00", "descricao": "Barcos"},
    {"eixo": "preparacao", "status": "concluida", "prazo": "2026-10-13T12:00:00+00:00", "descricao": "Estoques"},
    {"eixo": "recuperacao", "status": "cancelada", "prazo": None, "descricao": "Retorno"},
]
ORIGINAL = [{"id": "a", "Nível": "alerta", "Ameaça": "cheia", "Eixo": "resposta", "Ação": "Abrir abrigos",
             "Responsável": "coordenador_municipal", "Prazo (horas)": 12, "Ativa": True},
            {"id": "b", "Nível": "alto", "Ameaça": "qualquer", "Eixo": "resposta", "Ação": "Avaliar decreto",
             "Responsável": "coordenador_municipal", "Prazo (horas)": 24, "Ativa": True}]


class TestTarefas(unittest.TestCase):
    def test_atrasada_so_quando_aberta_e_vencida(self) -> None:
        self.assertEqual([atrasada(t, AGORA) for t in TAREFAS], [True, False, False, False])

    def test_resumo_por_eixo(self) -> None:
        r = resumo_por_eixo(TAREFAS, AGORA)
        self.assertEqual(r["resposta"], {"abertas": 2, "atrasadas": 1, "concluidas": 0})
        self.assertEqual(r["preparacao"]["concluidas"], 1)
        self.assertEqual(r["recuperacao"], {"abertas": 0, "atrasadas": 0, "concluidas": 0})
        self.assertEqual(set(r), {"prevencao", "mitigacao", "preparacao", "resposta", "recuperacao"})

    def test_lista_mostra_atrasada_primeiro(self) -> None:
        linhas = linhas_tarefas(TAREFAS, AGORA)
        self.assertEqual(linhas[0]["Situação"], "⚠️ ATRASADA")
        self.assertEqual(linhas[0]["Prazo"], "14/10 08:00")


class TestProtocolo(unittest.TestCase):
    def test_sem_mudanca(self) -> None:
        self.assertEqual(diferencas_protocolo(ORIGINAL, [dict(l) for l in ORIGINAL]), ([], [], [], []))

    def test_inclui_altera_e_exclui(self) -> None:
        editado = [dict(ORIGINAL[0], **{"Prazo (horas)": 6.0}),
                   {"id": None, "Nível": "atencao", "Ameaça": "seca", "Eixo": "preparacao",
                    "Ação": "Mapear rotas", "Responsável": "inexistente", "Prazo (horas)": float("nan"), "Ativa": None},
                   {"id": None, "Nível": "atencao", "Ameaça": "seca", "Eixo": "preparacao",
                    "Ação": "Mapear rotas alternativas", "Responsável": None, "Prazo (horas)": 48, "Ativa": None},
                   {"id": None, "Nível": None, "Ameaça": None, "Eixo": None, "Ação": None,
                    "Responsável": None, "Prazo (horas)": None, "Ativa": None}]
        novas, alteradas, excluidas, erros = diferencas_protocolo(ORIGINAL, editado)
        self.assertEqual(len(erros), 1)
        self.assertIn("Linha 2", erros[0])
        self.assertEqual(alteradas[0][0], "a")
        self.assertEqual(alteradas[0][1]["prazo_horas"], 6)
        self.assertEqual(excluidas, ["b"])
        self.assertEqual(novas[0]["descricao"], "Mapear rotas alternativas")
        self.assertTrue(novas[0]["ativo"])
        self.assertIsNone(novas[0]["responsavel_funcao"])


if __name__ == "__main__":
    unittest.main()
