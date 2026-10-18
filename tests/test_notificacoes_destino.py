"""Aviso interno só vai para o Telegram do próprio responsável (regressão de 17/10/2026)."""

import unittest

from core.notificacoes_telegram import chat_id_do_usuario


class _Consulta:
    def __init__(self, linhas):
        self.linhas, self.filtros = linhas, {}

    @property
    def not_(self):
        return self

    def select(self, *_):
        return self

    def eq(self, coluna, valor):
        self.filtros[coluna] = valor
        return self

    def is_(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        dados = [l for l in self.linhas if all(l.get(c) == v for c, v in self.filtros.items())]
        return type("R", (), {"data": dados})()


class _Cliente:
    def __init__(self, tabelas):
        self.tabelas = tabelas

    def table(self, nome):
        return _Consulta(self.tabelas.get(nome, []))


class TestDestino(unittest.TestCase):
    def test_nunca_usa_assinatura_publica_de_outra_pessoa(self) -> None:
        cliente = _Cliente({"voluntarios": [],
                            "assinaturas_alerta": [{"canal": "telegram", "ativo": True, "destino": "MORADOR"}]})
        self.assertIsNone(chat_id_do_usuario(cliente, "u-coordenacao"))

    def test_usa_o_vinculo_do_proprio_usuario(self) -> None:
        cliente = _Cliente({"voluntarios": [{"usuario_id": "u1", "telegram_chat_id": "111"},
                                            {"usuario_id": "u2", "telegram_chat_id": "222"}]})
        self.assertEqual(chat_id_do_usuario(cliente, "u2"), "222")


if __name__ == "__main__":
    unittest.main()
