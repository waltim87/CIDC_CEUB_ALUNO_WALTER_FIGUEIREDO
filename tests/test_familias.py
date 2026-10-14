import unittest

from app.familias import validar_membros


def membro(**campos):
    base = {"Nome completo": "Ana Souza Lima", "CPF": "529.982.247-25", "Sem CPF — motivo": "",
            "Parentesco": "filho(a)", "Desaparecido": False, "Visto por último em (dd/mm/aaaa)": "",
            "Último local visto": ""}
    return {**base, **campos}


class TestValidacaoMembros(unittest.TestCase):
    def test_membro_completo_e_valido(self) -> None:
        self.assertEqual(validar_membros([membro()]), [])

    def test_exige_nome_completo_cpf_valido_e_parentesco(self) -> None:
        erros = validar_membros([membro(**{"Nome completo": "Ana", "CPF": "111.111.111-11", "Parentesco": None})])
        self.assertEqual(len(erros), 3)

    def test_sem_cpf_exige_motivo(self) -> None:
        self.assertEqual(len(validar_membros([membro(CPF="")])), 1)
        self.assertEqual(validar_membros([membro(**{"CPF": "", "Sem CPF — motivo": "recém-nascido"})]), [])

    def test_desaparecido_exige_ultimo_dia_e_local(self) -> None:
        erros = validar_membros([membro(Desaparecido=True)])
        self.assertEqual(len(erros), 2)
        ok = membro(**{"Desaparecido": True, "Visto por último em (dd/mm/aaaa)": "12/10/2026",
                       "Último local visto": "porto da comunidade"})
        self.assertEqual(validar_membros([ok]), [])

    def test_linha_vazia_e_ignorada(self) -> None:
        vazia = {k: "" for k in membro()}
        vazia["Desaparecido"] = False
        vazia["Parentesco"] = None
        self.assertEqual(validar_membros([vazia]), [])


if __name__ == "__main__":
    unittest.main()
