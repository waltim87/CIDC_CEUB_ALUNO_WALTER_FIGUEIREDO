import unittest

from collectors.comum import ConfiguracaoPendenteError
from collectors.executar import executar_ciclo, main


def _ok(_config=None):
    return [{"a": 1}, {"a": 2}]


def _pendente(_config=None):
    raise ConfiguracaoPendenteError("CONFIRMAR endpoint")


def _quebra(_config=None):
    raise RuntimeError("falhou")


class ExecutarCicloTest(unittest.TestCase):
    def test_fontes_falham_isoladas_e_saude_e_gravada_por_fonte(self):
        gravados = []
        cfg = {k: {"nome": k} for k in ("a", "b", "c")}
        res = executar_ciclo(
            coletores={"a": _ok, "b": _pendente, "c": _quebra},
            configuracoes=cfg,
            gravar_saude=lambda r: gravados.append(r) or 1,
        )
        self.assertEqual(res["a"]["status"], "operacional")
        self.assertEqual(res["a"]["registros"], 2)
        self.assertEqual(res["b"]["status"], "pendente_confirmacao")
        self.assertEqual(res["c"]["status"], "erro")
        self.assertEqual(len(gravados), 3)

    def test_falha_ao_gravar_uma_fonte_nao_interrompe_as_outras(self):
        chamadas = []

        def gravar(r):
            chamadas.append(list(r))
            if "a" in r:
                raise RuntimeError("banco fora")
            return 1

        res = executar_ciclo(
            coletores={"a": _ok, "b": _ok},
            configuracoes={"a": {"nome": "a"}, "b": {"nome": "b"}},
            gravar_saude=gravar,
        )
        self.assertEqual(len(chamadas), 2)
        self.assertTrue(res["a"].get("erro_registro"))
        self.assertFalse(res["b"].get("erro_registro"))


if __name__ == "__main__":
    unittest.main()
