import unittest

from core import cpf


class TestCpf(unittest.TestCase):
    def test_valida_digitos_verificadores(self) -> None:
        self.assertTrue(cpf.valido("529.982.247-25"))
        self.assertTrue(cpf.valido("52998224725"))
        self.assertFalse(cpf.valido("529.982.247-24"))
        self.assertFalse(cpf.valido("111.111.111-11"))
        self.assertFalse(cpf.valido("123"))
        self.assertFalse(cpf.valido(None))

    def test_formata_e_mascara(self) -> None:
        self.assertEqual(cpf.formatar("52998224725"), "529.982.247-25")
        self.assertEqual(cpf.mascarar("529.982.247-25"), "***.***.247-25")


if __name__ == "__main__":
    unittest.main()
