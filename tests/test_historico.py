import unittest

from core.historico import comparar_com_historico, extremos_observados


class HistoricoTest(unittest.TestCase):
    def test_posicao_entre_seca_e_cheia(self):
        r = comparar_com_historico(1500, 2000, 1000)
        self.assertEqual(r["posicao_pct"], 50)
        self.assertEqual(r["dif_cheia_cm"], -500)
        self.assertEqual(r["situacao"], "dentro_da_faixa_historica")

    def test_acima_da_cheia_e_abaixo_da_seca(self):
        self.assertEqual(comparar_com_historico(2100, 2000, 1000)["situacao"], "acima_da_cheia_historica")
        self.assertEqual(comparar_com_historico(900, 2000, 1000)["situacao"], "abaixo_da_seca_historica")

    def test_sem_marcadores_nao_inventa(self):
        r = comparar_com_historico(1500, None, None)
        self.assertEqual(r["situacao"], "sem_marcadores")
        self.assertIsNone(r["posicao_pct"])

    def test_extremos(self):
        self.assertEqual(extremos_observados([3, None, 9, 1]), (9.0, 1.0))
        self.assertEqual(extremos_observados([]), (None, None))


if __name__ == "__main__":
    unittest.main()
