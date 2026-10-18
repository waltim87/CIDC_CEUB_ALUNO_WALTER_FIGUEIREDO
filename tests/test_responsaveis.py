"""Matriz de responsáveis por área."""

import unittest

from app.responsaveis import AREAS, areas_sem_titular, matriz

ATRIBUICOES = [
    {"area": "saude", "papel": "titular", "nome_exibicao": "Ana", "ate": None, "desde": "2026-10-01",
     "contato_institucional": "(97) 3331-0000"},
    {"area": "saude", "papel": "suplente", "nome_exibicao": "Bia", "ate": None, "desde": "2026-10-01"},
    {"area": "abrigos", "papel": "titular", "nome_exibicao": "Caio (antigo)", "ate": "2026-10-10", "desde": "2026-09-01"},
]


class TestResponsaveis(unittest.TestCase):
    def test_matriz_mostra_titular_suplente_e_ignora_encerrados(self) -> None:
        linhas = {l["Área"]: l for l in matriz(ATRIBUICOES)}
        self.assertEqual(len(linhas), len(AREAS))
        saude = linhas[AREAS["saude"][0]]
        self.assertEqual((saude["Titular"], saude["Suplente"], saude["Contato"]), ("Ana", "Bia", "(97) 3331-0000"))
        self.assertEqual(linhas[AREAS["abrigos"][0]]["Titular"], "⚠️ a definir")

    def test_areas_sem_titular(self) -> None:
        faltando = areas_sem_titular(ATRIBUICOES)
        self.assertNotIn(AREAS["saude"][0], faltando)
        self.assertIn(AREAS["abrigos"][0], faltando)
        self.assertEqual(len(faltando), len(AREAS) - 1)


if __name__ == "__main__":
    unittest.main()
