"""Robô do Telegram: inscrições por consentimento e envio automático de alertas aprovados.

Roda a cada 15 minutos no GitHub Actions (``python -m core.telegram_robo``):

1. Lê as mensagens enviadas ao robô (getUpdates) e trata os comandos:
   - ``/start`` -> boas-vindas e instruções;
   - ``/start <código>`` (link do cadastro de voluntário) -> vincula o Telegram ao
     voluntário e inscreve no município dele;
   - nome de uma cidade do AM ou ``/cidade Lábrea`` -> inscreve o chat na cidade;
   - ``/sair`` -> cancela todas as inscrições do chat.
   A inscrição parte da própria pessoa (consentimento, LGPD); o sistema guarda só o
   chat_id e o município.
2. Envia os alertas com status "aprovado" e ainda não emitidos para as inscrições
   ativas do município e marca o alerta como "enviado". A aprovação humana no
   painel continua obrigatória; nada é enviado sem ela.
"""

from __future__ import annotations

import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{metodo}"
RODAPE = "\n\nConfirme sempre nos canais oficiais. Emergência: ligue 199 (Defesa Civil)."
BOAS_VINDAS = (
    "Olá! Este é o robô de alertas do Centro de Inteligência da Defesa Civil (protótipo).\n\n"
    "Para receber os alertas APROVADOS pela Defesa Civil, envie o nome da sua cidade "
    "do Amazonas (ex.: Lábrea). Você pode se inscrever em mais de uma cidade.\n"
    "Para parar de receber, envie /sair.\n\n"
    "Guardamos apenas o número deste chat e a cidade escolhida, só para enviar os alertas."
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().replace("-", " ").split())


class Telegram:
    def __init__(self, token: str, sessao: Any = requests) -> None:
        self.token, self.sessao = token, sessao

    def chamar(self, metodo: str, **dados: Any) -> Any:
        try:
            resposta = self.sessao.post(API.format(token=self.token, metodo=metodo), json=dados, timeout=30)
            corpo = resposta.json()
        except Exception as erro:
            raise RuntimeError(f"Telegram inacessível ({type(erro).__name__})") from None
        if not corpo.get("ok"):
            raise RuntimeError(f"Telegram: {corpo.get('description')}")
        return corpo.get("result")

    def responder(self, chat_id: Any, texto: str) -> None:
        try:
            self.chamar("sendMessage", chat_id=chat_id, text=texto)
        except Exception as erro:
            LOGGER.warning("Não foi possível responder ao chat ***%s: %s", str(chat_id)[-4:], erro)


def _inscrever(cliente: Any, chat_id: str, municipio_id: str) -> None:
    agora = datetime.now(timezone.utc).isoformat()
    cliente.table("assinaturas_alerta").upsert(
        {"municipio_id": municipio_id, "canal": "telegram", "destino": chat_id,
         "ativo": True, "confirmado_em": agora},
        on_conflict="municipio_id,canal,destino",
    ).execute()


def processar_mensagens(cliente: Any, telegram: Telegram) -> dict[str, int]:
    resumo = {"mensagens": 0, "inscricoes": 0, "voluntarios": 0, "saidas": 0}
    atualizacoes = telegram.chamar("getUpdates", timeout=0, allowed_updates=["message"]) or []
    if not atualizacoes:
        return resumo
    municipios = {
        _normalizar(m["nome"]): (str(m["id_ibge"]).strip(), m["nome"])
        for m in cliente.table("municipios").select("id_ibge,nome").execute().data or []
    }
    for atualizacao in atualizacoes:
        mensagem = atualizacao.get("message") or {}
        chat = mensagem.get("chat") or {}
        texto = (mensagem.get("text") or "").strip()
        if not chat.get("id") or not texto:
            continue
        resumo["mensagens"] += 1
        chat_id = str(chat["id"])
        comando, _, argumento = texto.partition(" ")
        comando = comando.split("@")[0].lower()
        try:
            if comando == "/start" and argumento.strip():
                voluntario = (
                    cliente.table("voluntarios").select("id,nome,municipio_id")
                    .eq("telegram_codigo", argumento.strip()).limit(1).execute().data or []
                )
                if not voluntario:
                    telegram.responder(chat_id, "Código de voluntário não encontrado. " + BOAS_VINDAS)
                    continue
                v = voluntario[0]
                cliente.table("voluntarios").update({"telegram_chat_id": chat_id}).eq("id", v["id"]).execute()
                _inscrever(cliente, chat_id, str(v["municipio_id"]).strip())
                resumo["voluntarios"] += 1
                telegram.responder(
                    chat_id,
                    f"Obrigado, {v['nome'].split()[0]}! Seu Telegram foi vinculado ao cadastro de "
                    "voluntário. Você receberá os alertas aprovados do seu município. "
                    "Envie o nome de outra cidade para acompanhar também, ou /sair para cancelar.",
                )
            elif comando in {"/start", "/ajuda", "/help"}:
                telegram.responder(chat_id, BOAS_VINDAS)
            elif comando in {"/sair", "/parar", "/stop"}:
                cliente.table("assinaturas_alerta").update({"ativo": False}).eq("canal", "telegram").eq("destino", chat_id).execute()
                resumo["saidas"] += 1
                telegram.responder(chat_id, "Pronto: você não receberá mais alertas. Para voltar, envie o nome da cidade.")
            else:
                nome = argumento if comando == "/cidade" else texto
                encontrado = municipios.get(_normalizar(nome))
                if not encontrado:
                    telegram.responder(
                        chat_id,
                        f"Não encontrei a cidade \"{nome[:40]}\" no Amazonas. Envie o nome como no mapa "
                        "(ex.: Lábrea, Boca do Acre, Manaus).",
                    )
                    continue
                _inscrever(cliente, chat_id, encontrado[0])
                resumo["inscricoes"] += 1
                telegram.responder(
                    chat_id,
                    f"Inscrição confirmada: você receberá os alertas aprovados de {encontrado[1]}. "
                    "Para cancelar, envie /sair." + RODAPE,
                )
        except Exception:
            LOGGER.exception("Falha ao processar mensagem do chat ***%s", chat_id[-4:])
    # Confirma ao Telegram que as mensagens foram lidas (não voltam na próxima execução).
    telegram.chamar("getUpdates", offset=atualizacoes[-1]["update_id"] + 1, timeout=0)
    return resumo


def formatar_alerta(alerta: dict[str, Any], municipio: str) -> str:
    return f"⚠️ ALERTA {str(alerta['classe']).upper()} — {municipio}\n\n{alerta['texto']}{RODAPE}"


def enviar_aprovados(cliente: Any, telegram: Telegram) -> dict[str, int]:
    """Entrega alertas aprovados e não emitidos; marca como enviado quando houve entrega."""
    resumo = {"alertas": 0, "entregas": 0, "falhas": 0, "sem_inscritos": 0}
    alertas = (
        cliente.table("alertas").select("id,municipio_id,classe,texto,status,emitido_em")
        .eq("status", "aprovado").is_("emitido_em", "null").limit(50).execute().data or []
    )
    nomes = {
        str(m["id_ibge"]).strip(): m["nome"]
        for m in cliente.table("municipios").select("id_ibge,nome").execute().data or []
    }
    for alerta in alertas:
        municipio_id = str(alerta["municipio_id"]).strip()
        inscritos = (
            cliente.table("assinaturas_alerta").select("id,destino")
            .eq("municipio_id", municipio_id).eq("canal", "telegram").eq("ativo", True)
            .not_.is_("confirmado_em", "null").execute().data or []
        )
        if not inscritos:
            resumo["sem_inscritos"] += 1
            LOGGER.info("Alerta %s aprovado, mas %s não tem inscritos no Telegram", alerta["id"], nomes.get(municipio_id))
            continue
        ja_entregues = {
            e["assinatura_id"]
            for e in cliente.table("entregas_alerta").select("assinatura_id")
            .eq("alerta_id", alerta["id"]).eq("status", "enviado").execute().data or []
        }
        texto = formatar_alerta(alerta, nomes.get(municipio_id, municipio_id))
        entregues = len(ja_entregues)
        for inscrito in inscritos:
            if inscrito["id"] in ja_entregues:
                continue
            status, erro = "enviado", None
            try:
                telegram.chamar("sendMessage", chat_id=inscrito["destino"], text=texto)
                entregues += 1
                resumo["entregas"] += 1
            except Exception as falha:
                status, erro = "falha", str(falha)[:200]
                resumo["falhas"] += 1
                if "blocked" in erro or "chat not found" in erro:
                    cliente.table("assinaturas_alerta").update({"ativo": False}).eq("id", inscrito["id"]).execute()
            cliente.table("entregas_alerta").insert({
                "alerta_id": alerta["id"], "assinatura_id": inscrito["id"], "canal": "telegram",
                "destino_mascarado": f"***{str(inscrito['destino'])[-4:]}", "status": status, "erro": erro,
            }).execute()
        if entregues:
            cliente.table("alertas").update(
                {"status": "enviado", "emitido_em": datetime.now(timezone.utc).isoformat()}
            ).eq("id", alerta["id"]).eq("status", "aprovado").execute()
            resumo["alertas"] += 1
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    if not token:
        LOGGER.error("Defina o secret TELEGRAM_BOT_TOKEN no GitHub (Settings > Secrets > Actions)")
        return 1
    cliente, telegram = create_client(url, chave), Telegram(token)
    try:
        LOGGER.info("Mensagens: %s", processar_mensagens(cliente, telegram))
    except Exception:
        LOGGER.exception("Falha ao processar mensagens do Telegram")
    LOGGER.info("Envios: %s", enviar_aprovados(cliente, telegram))
    return 0


if __name__ == "__main__":
    sys.exit(main())
