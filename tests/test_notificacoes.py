from __future__ import annotations

import unittest
from typing import Any

from core.alertas import marcar_enviado
from core.notificacoes import enviar_alerta_aprovado, mascara_destino


class ConsultaSimulada:
    def __init__(self, cliente: "ClienteSimulado", tabela: str) -> None:
        self.cliente = cliente
        self.tabela = tabela
        self.operacao = "select"
        self.filtros: list[tuple[str, str, Any]] = []
        self.payload: dict[str, Any] | None = None
        self.negado = False

    def select(self, *_args: Any, **_kwargs: Any) -> "ConsultaSimulada":
        self.operacao = "select"
        return self

    def eq(self, coluna: str, valor: Any) -> "ConsultaSimulada":
        self.filtros.append((coluna, "eq", valor))
        return self

    @property
    def not_(self) -> "ConsultaSimulada":
        self.negado = True
        return self

    def is_(self, coluna: str, valor: Any) -> "ConsultaSimulada":
        operador = "not_is" if self.negado else "is"
        self.filtros.append((coluna, operador, valor))
        self.negado = False
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "ConsultaSimulada":
        return self

    def limit(self, *_args: Any, **_kwargs: Any) -> "ConsultaSimulada":
        return self

    def insert(self, payload: dict[str, Any]) -> "ConsultaSimulada":
        self.operacao = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "ConsultaSimulada":
        self.operacao = "update"
        self.payload = payload
        return self

    def execute(self) -> Any:
        if self.operacao == "insert":
            self.cliente.entregas.append(dict(self.payload or {}))
            return type("Resposta", (), {"data": [dict(self.payload or {})]})()
        if self.operacao == "update":
            dados = [self.cliente.alerta] if self.tabela == "alertas" else []
            for coluna, operador, valor in self.filtros:
                if operador == "eq":
                    dados = [linha for linha in dados if linha.get(coluna) == valor]
                elif operador == "is" and valor == "null":
                    dados = [linha for linha in dados if linha.get(coluna) is None]
            for linha in dados:
                linha.update(self.payload or {})
            return type("Resposta", (), {"data": [dict(linha) for linha in dados]})()
        if self.tabela == "alertas":
            dados = [self.cliente.alerta]
        elif self.tabela == "assinaturas_alerta":
            dados = self.cliente.assinaturas
        elif self.tabela == "entregas_alerta":
            dados = self.cliente.entregas
        else:
            dados = []
        for coluna, operador, valor in self.filtros:
            if operador == "eq":
                dados = [linha for linha in dados if linha.get(coluna) == valor]
            elif operador == "not_is" and valor == "null":
                dados = [linha for linha in dados if linha.get(coluna) is not None]
        return type("Resposta", (), {"data": [dict(linha) for linha in dados]})()


class ClienteSimulado:
    def __init__(self, status: str = "aprovado") -> None:
        self.alerta = {
            "id": "alerta-1",
            "municipio_id": "1302405",
            "texto": "Mensagem revisada.",
            "status": status,
        }
        self.assinaturas = [
            {
                "id": "assinatura-telegram",
                "municipio_id": "1302405",
                "canal": "telegram",
                "destino": "123456789",
                "ativo": True,
                "confirmado_em": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "assinatura-email",
                "municipio_id": "1302405",
                "canal": "email",
                "destino": "contato@example.org",
                "ativo": True,
                "confirmado_em": "2026-01-01T00:00:00+00:00",
            },
        ]
        self.entregas: list[dict[str, Any]] = []

    def table(self, tabela: str) -> ConsultaSimulada:
        return ConsultaSimulada(self, tabela)


class TestNotificacoes(unittest.TestCase):
    def test_recusa_envio_de_alerta_nao_aprovado(self) -> None:
        cliente = ClienteSimulado(status="rascunho")
        with self.assertRaisesRegex(ValueError, "Somente alertas aprovados"):
            enviar_alerta_aprovado(
                cliente,
                "alerta-1",
                transportes={"telegram": lambda _destino, _texto: None},
            )
        self.assertEqual(cliente.entregas, [])

    def test_nao_envia_a_assinaturas_nao_confirmadas_ou_inativas(self) -> None:
        cliente = ClienteSimulado()
        cliente.assinaturas[0]["confirmado_em"] = None
        cliente.assinaturas[1]["ativo"] = False
        with self.assertRaisesRegex(ValueError, "Não há assinaturas ativas"):
            enviar_alerta_aprovado(
                cliente,
                "alerta-1",
                transportes={
                    "telegram": lambda _destino, _texto: self.fail(
                        "não deveria enviar para assinatura não confirmada"
                    ),
                    "email": lambda _destino, _texto: self.fail(
                        "não deveria enviar para assinatura inativa"
                    ),
                },
            )

    def test_envia_a_destinos_confirmados_e_registra_entregas(self) -> None:
        cliente = ClienteSimulado()
        destinos: list[str] = []

        def enviar(destino: str, texto: str) -> None:
            destinos.append(destino)
            self.assertEqual(texto, "Mensagem revisada.")

        resultado = enviar_alerta_aprovado(
            cliente,
            "alerta-1",
            transportes={"telegram": enviar, "email": enviar},
        )
        self.assertEqual(resultado, {"enviados": 2, "falhas": 0})
        self.assertEqual(destinos, ["123456789", "contato@example.org"])
        self.assertEqual([item["status"] for item in cliente.entregas], ["enviado"] * 2)
        self.assertEqual(
            cliente.entregas[1]["destino_mascarado"], "c***@example.org"
        )
        self.assertIsNotNone(cliente.alerta["emitido_em"])
        primeiro_horario = cliente.alerta["emitido_em"]
        marcar_enviado(cliente, "alerta-1")
        self.assertEqual(cliente.alerta["status"], "enviado")
        self.assertEqual(cliente.alerta["emitido_em"], primeiro_horario)

    def test_falha_de_um_destino_nao_interrompe_os_demais(self) -> None:
        cliente = ClienteSimulado()
        enviados: list[str] = []

        def enviar_telegram(_destino: str, _texto: str) -> None:
            raise TimeoutError("erro de transporte")

        def enviar_email(destino: str, _texto: str) -> None:
            enviados.append(destino)

        with self.assertRaisesRegex(RuntimeError, "Envio parcial: 1 destino"):
            enviar_alerta_aprovado(
                cliente,
                "alerta-1",
                transportes={
                    "telegram": enviar_telegram,
                    "email": enviar_email,
                },
            )
        self.assertEqual(enviados, ["contato@example.org"])
        self.assertEqual([item["status"] for item in cliente.entregas], ["falha", "enviado"])
        self.assertEqual(
            cliente.entregas[0]["erro"], "Falha no envio (TimeoutError)"
        )

    def test_reenvio_pula_destinos_ja_entregues(self) -> None:
        cliente = ClienteSimulado()
        cliente.entregas.append(
            {
                "alerta_id": "alerta-1",
                "assinatura_id": "assinatura-telegram",
                "status": "enviado",
            }
        )
        destinos: list[str] = []
        resultado = enviar_alerta_aprovado(
            cliente,
            "alerta-1",
            transportes={
                "telegram": lambda destino, _texto: destinos.append(destino),
                "email": lambda destino, _texto: destinos.append(destino),
            },
        )
        self.assertEqual(resultado, {"enviados": 2, "falhas": 0})
        self.assertEqual(destinos, ["contato@example.org"])

    def test_mascara_enderecos_antes_de_exibi_los(self) -> None:
        self.assertEqual(mascara_destino("email", "ana@example.org"), "a***@example.org")
        self.assertEqual(mascara_destino("telegram", "123456789"), "***6789")


if __name__ == "__main__":
    unittest.main()
