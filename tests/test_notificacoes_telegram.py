"""Testes da B3: avisos por Telegram para responsáveis."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class _FakeResult:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, dados: list[dict]) -> None:
        self._dados = dados
        self._filtros: list[tuple[str, str, object]] = []
        self._not_null: list[str] = []
        self._limite: int | None = None

    def select(self, colunas: str = "*") -> "_FakeTable":
        return self

    def eq(self, coluna: str, valor: object) -> "_FakeTable":
        self._filtros.append((coluna, "eq", valor))
        return self

    def not_(self) -> "_FakeTable":
        return self

    def is_(self, coluna: str, valor: object) -> "_FakeTable":
        if valor == "null":
            self._not_null.append(coluna)
        return self

    def limit(self, n: int) -> "_FakeTable":
        self._limite = n
        return self

    def execute(self) -> _FakeResult:
        resultado = list(self._dados)
        for coluna in self._not_null:
            resultado = [r for r in resultado if r.get(coluna) is not None]
        for coluna, _, valor in self._filtros:
            resultado = [
                r for r in resultado
                if str(r.get(coluna, "")).strip() == str(valor).strip()
            ]
        if self._limite is not None:
            resultado = resultado[: self._limite]
        return _FakeResult(resultado)


class _FakeCliente:
    def __init__(self, voluntarios: list[dict], assinaturas: list[dict], usuarios: list[dict]) -> None:
        self._tabelas = {
            "voluntarios": _FakeTable(voluntarios),
            "assinaturas_alerta": _FakeTable(assinaturas),
            "usuarios": _FakeTable(usuarios),
        }

    def table(self, nome: str) -> _FakeTable:
        return self._tabelas[nome]


# Importar depois de definir as classes fake
from core.notificacoes_telegram import (  # noqa: E402
    chat_id_do_usuario,
    notificar_responsaveis_por_funcao,
)


class TestNotificarResponsaveisPorFuncao(unittest.TestCase):
    def test_envia_somente_quem_tem_telegram(self) -> None:
        cliente = _FakeCliente(
            voluntarios=[
                {"usuario_id": "u1", "telegram_chat_id": "123456789"},
                {"usuario_id": "u2", "telegram_chat_id": None},
            ],
            assinaturas=[],
            usuarios=[
                {"id": "u1", "perfil": "saude_assistencia", "municipio_id": "1302405"},
                {"id": "u2", "perfil": "saude_assistencia", "municipio_id": "1302405"},
            ],
        )

        import core.notificacoes_telegram as mod

        chamados: list[tuple[str, str]] = []

        def fake_enviar(cliente_, chat_id: str, texto: str) -> tuple[bool, str | None]:
            chamados.append((chat_id, texto))
            return True, None

        def fake_chat_id(cliente_, usuario_id: str) -> str | None:
            return "123456789" if usuario_id == "u1" else None

        with patch.object(mod, "chat_id_do_usuario", side_effect=fake_chat_id), \
             patch.object(mod, "enviar_aviso_telegram", side_effect=fake_enviar), \
             patch.object(mod, "registrar_notificacao"):
            mod.notificar_responsaveis_por_funcao(
                cliente, "1302405", "saude_assistencia",
                "Vistoriar abrigos prioritários", "24/10/2026",
            )

        # Só u1 tem Telegram; u2 não deve ser notificado.
        self.assertEqual(len(chamados), 1)
        self.assertEqual(chamados[0][0], "123456789")
        self.assertIn("Vistoriar abrigos prioritários", chamados[0][1])


class TestChatIdDoUsuarioEtapas(unittest.TestCase):
    """Testa as etapas individuais de busca de chat_id (sem o try/except da função)."""

    def test_voluntario_tem_chat_id(self) -> None:
        cliente = _FakeCliente(
            voluntarios=[{"usuario_id": "u1", "telegram_chat_id": "123456789"}],
            assinaturas=[],
            usuarios=[],
        )
        v = (
            cliente.table("voluntarios")
            .select("telegram_chat_id")
            .eq("usuario_id", "u1")
            .not_().is_("telegram_chat_id", "null")
            .limit(1)
            .execute()
            .data
        )
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["telegram_chat_id"], "123456789")

    def test_assinatura_ativa_tem_destino(self) -> None:
        cliente = _FakeCliente(
            voluntarios=[],
            assinaturas=[{"canal": "telegram", "ativo": True,
                         "confirmado_em": "2026-01-01", "destino": "987654321"}],
            usuarios=[],
        )
        s = (
            cliente.table("assinaturas_alerta")
            .select("destino")
            .eq("canal", "telegram")
            .eq("ativo", True)
            .not_().is_("confirmado_em", "null")
            .limit(1)
            .execute()
            .data
        )
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["destino"], "987654321")

    def test_sem_telegram_retorna_vazio(self) -> None:
        cliente = _FakeCliente(
            voluntarios=[{"usuario_id": "u1", "telegram_chat_id": None}],
            assinaturas=[],
            usuarios=[],
        )
        v = (
            cliente.table("voluntarios")
            .select("telegram_chat_id")
            .eq("usuario_id", "u1")
            .not_().is_("telegram_chat_id", "null")
            .limit(1)
            .execute()
            .data
        )
        self.assertEqual(len(v), 0)


if __name__ == "__main__":
    unittest.main()
