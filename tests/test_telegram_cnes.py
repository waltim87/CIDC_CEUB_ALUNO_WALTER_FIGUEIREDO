from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from collectors import cnes
from core import telegram_robo


class Consulta:
    def __init__(self, banco: "Banco", tabela: str) -> None:
        self.banco, self.tabela, self.filtros = banco, tabela, {}
        self.operacao: tuple[str, Any] | None = None

    def __getattr__(self, nome: str) -> Any:
        if nome == "not_":
            return self
        return lambda *a, **k: self._encadear(nome, a, k)

    def _encadear(self, nome: str, args: tuple, kwargs: dict) -> "Consulta":
        if nome in {"insert", "update", "upsert"}:
            self.operacao = (nome, args[0])
        elif nome == "eq":
            self.filtros[args[0]] = args[1]
        return self

    def execute(self) -> Any:
        if self.operacao:
            self.banco.escritas.append((self.tabela, self.operacao[0], self.operacao[1], dict(self.filtros)))
            return type("R", (), {"data": [self.operacao[1]]})()
        dados = [
            linha for linha in self.banco.dados.get(self.tabela, [])
            if all(str(linha.get(k)) == str(v) for k, v in self.filtros.items() if k in linha)
        ]
        return type("R", (), {"data": dados})()


class Banco:
    def __init__(self, dados: dict[str, list]) -> None:
        self.dados, self.escritas = dados, []

    def table(self, nome: str) -> Consulta:
        return Consulta(self, nome)

    def escritas_em(self, tabela: str, operacao: str) -> list:
        return [e for e in self.escritas if e[0] == tabela and e[1] == operacao]


class TelegramFalso(telegram_robo.Telegram):
    def __init__(self, atualizacoes: list[dict], falhar_para: set[str] | None = None) -> None:
        super().__init__("token-falso")
        self.atualizacoes, self.falhar_para = atualizacoes, falhar_para or set()
        self.enviadas: list[tuple[str, str]] = []
        self.offset = None

    def chamar(self, metodo: str, **dados: Any) -> Any:
        if metodo == "getUpdates":
            if "offset" in dados:
                self.offset = dados["offset"]
                return []
            return self.atualizacoes
        if metodo == "sendMessage":
            if str(dados["chat_id"]) in self.falhar_para:
                raise RuntimeError("Telegram: Forbidden: bot was blocked by the user")
            self.enviadas.append((str(dados["chat_id"]), dados["text"]))
            return {}
        raise AssertionError(metodo)


def mensagem(update_id: int, chat_id: int, texto: str) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": texto}}


MUNICIPIOS = [{"id_ibge": "1302405", "nome": "Lábrea"}, {"id_ibge": "1300706", "nome": "Boca do Acre"}]


class TestInscricoes(unittest.TestCase):
    def test_nome_da_cidade_inscreve_com_consentimento(self) -> None:
        banco = Banco({"municipios": MUNICIPIOS})
        telegram = TelegramFalso([mensagem(10, 555, "labrea")])
        resumo = telegram_robo.processar_mensagens(banco, telegram)
        self.assertEqual(resumo["inscricoes"], 1)
        _, _, dados, _ = banco.escritas_em("assinaturas_alerta", "upsert")[0]
        self.assertEqual((dados["municipio_id"], dados["destino"], dados["ativo"]), ("1302405", "555", True))
        self.assertIsNotNone(dados["confirmado_em"])
        self.assertIn("Lábrea", telegram.enviadas[0][1])
        self.assertEqual(telegram.offset, 11)  # mensagens confirmadas ao Telegram

    def test_codigo_do_voluntario_vincula_telegram(self) -> None:
        banco = Banco({"municipios": MUNICIPIOS, "voluntarios": [
            {"id": "v1", "nome": "Ana Souza", "municipio_id": "1300706", "telegram_codigo": "abc123def456"}]})
        resumo = telegram_robo.processar_mensagens(banco, TelegramFalso([mensagem(1, 777, "/start abc123def456")]))
        self.assertEqual(resumo["voluntarios"], 1)
        self.assertEqual(banco.escritas_em("voluntarios", "update")[0][2], {"telegram_chat_id": "777"})
        self.assertEqual(banco.escritas_em("assinaturas_alerta", "upsert")[0][2]["municipio_id"], "1300706")

    def test_sair_desativa_e_cidade_desconhecida_responde_ajuda(self) -> None:
        banco = Banco({"municipios": MUNICIPIOS})
        telegram = TelegramFalso([mensagem(1, 9, "/sair"), mensagem(2, 9, "Cidade Inexistente")])
        resumo = telegram_robo.processar_mensagens(banco, telegram)
        self.assertEqual(resumo["saidas"], 1)
        self.assertEqual(banco.escritas_em("assinaturas_alerta", "update")[0][2], {"ativo": False})
        self.assertIn("Não encontrei", telegram.enviadas[1][1])


class TestEnvioAutomatico(unittest.TestCase):
    def test_envia_aprovado_registra_entregas_e_marca_enviado(self) -> None:
        banco = Banco({
            "municipios": MUNICIPIOS,
            "alertas": [{"id": "a1", "municipio_id": "1302405", "classe": "Alerta", "texto": "Rio perto da seca recorde.",
                         "status": "aprovado", "emitido_em": None}],
            "assinaturas_alerta": [
                {"id": "s1", "destino": "555", "municipio_id": "1302405", "canal": "telegram", "ativo": True},
                {"id": "s2", "destino": "666", "municipio_id": "1302405", "canal": "telegram", "ativo": True},
            ],
            "entregas_alerta": [],
        })
        telegram = TelegramFalso([], falhar_para={"666"})
        resumo = telegram_robo.enviar_aprovados(banco, telegram)
        self.assertEqual((resumo["entregas"], resumo["falhas"], resumo["alertas"]), (1, 1, 1))
        self.assertIn("ALERTA ALERTA — Lábrea", telegram.enviadas[0][1])
        self.assertIn("199", telegram.enviadas[0][1])
        status = [e[2]["status"] for e in banco.escritas_em("entregas_alerta", "insert")]
        self.assertEqual(status, ["enviado", "falha"])
        # Quem bloqueou o robô é desativado; o alerta passa a "enviado".
        self.assertIn(({"ativo": False}), [e[2] for e in banco.escritas_em("assinaturas_alerta", "update")])
        self.assertEqual(banco.escritas_em("alertas", "update")[0][2]["status"], "enviado")

    def test_sem_inscritos_mantem_aprovado(self) -> None:
        banco = Banco({"municipios": MUNICIPIOS, "assinaturas_alerta": [], "entregas_alerta": [], "alertas": [
            {"id": "a1", "municipio_id": "1302405", "classe": "Alerta", "texto": "x", "status": "aprovado", "emitido_em": None}]})
        resumo = telegram_robo.enviar_aprovados(banco, TelegramFalso([]))
        self.assertEqual(resumo["sem_inscritos"], 1)
        self.assertEqual(banco.escritas_em("alertas", "update"), [])


REGISTRO_CNES = {
    "codigo_cnes": 2018756, "nome_fantasia": "CENTRO DE SAUDE SEBASTIANA MAIA DE SOUZA",
    "codigo_tipo_unidade": 2, "codigo_municipio": 130240, "codigo_uf": 13,
    "endereco_estabelecimento": "RUA 22 DE OUTUBRO", "numero_estabelecimento": "3977",
    "bairro_estabelecimento": "VILA FALCAO", "numero_telefone_estabelecimento": "(97 ) 3331-1316",
    "latitude_estabelecimento_decimo_grau": -7.2535, "longitude_estabelecimento_decimo_grau": -64.79,
    "estabelecimento_possui_atendimento_hospitalar": 0, "data_atualizacao": "2025-09-03",
}


class TestCnes(unittest.TestCase):
    def test_normaliza_estabelecimento_com_endereco_telefone_e_coordenadas(self) -> None:
        linha = cnes.normalizar(REGISTRO_CNES, {"130240": "1302405"})
        self.assertEqual(linha["municipio_id"], "1302405")
        self.assertEqual(linha["tipo_unidade"], "Centro de saúde / UBS")
        self.assertEqual(linha["endereco"], "RUA 22 DE OUTUBRO, 3977")
        self.assertEqual(linha["telefone"], "(97) 3331-1316")
        self.assertEqual(linha["geom"], "SRID=4326;POINT(-64.79 -7.2535)")
        self.assertIn("CNES/DATASUS", linha["fonte"])

    def test_ignora_municipio_fora_do_am(self) -> None:
        self.assertIsNone(cnes.normalizar({**REGISTRO_CNES, "codigo_municipio": 999999}, {"130240": "1302405"}))

    def test_nao_reimporta_antes_de_7_dias(self) -> None:
        agora = datetime(2026, 10, 14, tzinfo=timezone.utc)
        banco = Banco({"fontes": [{"nome": cnes.NOME_FONTE, "ultima_coleta": (agora - timedelta(days=2)).isoformat()}]})
        self.assertEqual(cnes.importar(banco, agora=agora)["status"], "em_dia")


if __name__ == "__main__":
    unittest.main()
