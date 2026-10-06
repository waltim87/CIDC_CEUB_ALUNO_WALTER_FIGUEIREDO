"""Envio de alertas aprovados por Telegram e SMTP."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Callable

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

logger = logging.getLogger(__name__)
Transportes = dict[str, Callable[[str, str], None]]


def _segredo(nome: str) -> str | None:
    try:
        valor = st.secrets.get(nome)
    except StreamlitSecretNotFoundError:
        valor = None
    return str(valor) if valor else os.environ.get(nome)


def _enviar_telegram(destino: str, texto: str) -> None:
    token = _segredo("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    resposta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": destino, "text": texto},
        timeout=20,
    )
    resposta.raise_for_status()
    corpo = resposta.json()
    if not corpo.get("ok"):
        raise RuntimeError("Telegram não confirmou a entrega")


def _enviar_email(destino: str, texto: str) -> None:
    host = _segredo("SMTP_HOST")
    usuario = _segredo("SMTP_USER")
    senha = _segredo("SMTP_PASSWORD")
    remetente = _segredo("SMTP_FROM") or usuario
    porta_texto = _segredo("SMTP_PORT") or "587"
    if not host or not usuario or not senha or not remetente:
        raise RuntimeError("Credenciais SMTP não configuradas")
    try:
        porta = int(porta_texto)
    except ValueError as erro:
        raise RuntimeError("SMTP_PORT deve ser numérica") from erro
    mensagem = EmailMessage()
    mensagem["Subject"] = "Alerta da Defesa Civil — revisão humana"
    mensagem["From"] = remetente
    mensagem["To"] = destino
    mensagem.set_content(texto)
    contexto = ssl.create_default_context()
    if porta == 465:
        with smtplib.SMTP_SSL(host, porta, context=contexto, timeout=20) as servidor:
            servidor.login(usuario, senha)
            servidor.send_message(mensagem)
    else:
        with smtplib.SMTP(host, porta, timeout=20) as servidor:
            servidor.ehlo()
            servidor.starttls(context=contexto)
            servidor.ehlo()
            servidor.login(usuario, senha)
            servidor.send_message(mensagem)


def _mascarar_destino(canal: str, destino: str) -> str:
    if canal == "email":
        partes = destino.split("@", 1)
        if len(partes) == 2:
            nome = partes[0]
            return f"{nome[:1]}***@{partes[1]}"
    return f"***{destino[-4:]}" if len(destino) > 4 else "***"


def enviar_alerta_aprovado(
    cliente: Any,
    alerta_id: str,
    *,
    transportes: Transportes | None = None,
) -> dict[str, int]:
    """Entrega apenas alertas já aprovados a assinaturas confirmadas.

    As falhas de destinatários são registradas individualmente e não interrompem
    os demais envios. Se houver qualquer falha, o alerta permanece aprovado e
    pode ser reenviado sem duplicar entregas anteriormente confirmadas.
    """
    alertas = (
        cliente.table("alertas")
        .select("id,municipio_id,texto,status,emitido_em")
        .eq("id", alerta_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not alertas:
        raise LookupError("Alerta não encontrado ou indisponível no seu escopo")
    alerta = alertas[0]
    if alerta["status"] != "aprovado":
        raise ValueError("Somente alertas aprovados podem ser enviados")

    assinaturas = (
        cliente.table("assinaturas_alerta")
        .select("id,canal,destino")
        .eq("municipio_id", alerta["municipio_id"])
        .eq("ativo", True)
        .not_.is_("confirmado_em", "null")
        .order("id")
        .execute()
        .data
        or []
    )
    if not assinaturas:
        raise ValueError("Não há assinaturas ativas e confirmadas para este município")

    entregas = (
        cliente.table("entregas_alerta")
        .select("assinatura_id")
        .eq("alerta_id", alerta_id)
        .eq("status", "enviado")
        .execute()
        .data
        or []
    )
    ja_enviadas = {entrega["assinatura_id"] for entrega in entregas}
    pendentes = [item for item in assinaturas if item["id"] not in ja_enviadas]
    enviado = len(ja_enviadas)
    falhou = 0
    por_canal: Transportes = (
        transportes
        if transportes is not None
        else {"telegram": _enviar_telegram, "email": _enviar_email}
    )

    for assinatura in pendentes:
        canal = assinatura["canal"]
        destino = assinatura["destino"]
        status = "enviado"
        erro_registro = None
        try:
            transporte = por_canal.get(canal)
            if transporte is None:
                raise RuntimeError(f"Canal sem transportador configurado: {canal}")
            transporte(destino, alerta["texto"])
        except Exception as erro:
            status = "falha"
            erro_registro = f"Falha no envio ({type(erro).__name__})"
            falhou += 1
            logger.warning(
                "Falha no envio do alerta %s pelo canal %s (%s)",
                alerta_id,
                canal,
                type(erro).__name__,
            )
        resultado = (
            cliente.table("entregas_alerta")
            .insert(
                {
                    "alerta_id": alerta_id,
                    "assinatura_id": assinatura["id"],
                    "canal": canal,
                    "destino_mascarado": _mascarar_destino(canal, destino),
                    "status": status,
                    "erro": erro_registro,
                }
            )
            .execute()
        )
        if not resultado.data:
            raise RuntimeError(
                "Entrega não registrada no banco; não é seguro repetir sem conferência."
            )
        if status == "enviado":
            enviado += 1

    if enviado and not alerta.get("emitido_em"):
        emitido_em = datetime.now(timezone.utc).isoformat()
        atualizado = (
            cliente.table("alertas")
            .update({"emitido_em": emitido_em})
            .eq("id", alerta_id)
            .eq("status", "aprovado")
            .is_("emitido_em", "null")
            .execute()
        )
        if not atualizado.data:
            raise RuntimeError(
                "Há entregas concluídas, mas o horário de emissão não foi registrado."
            )

    if falhou:
        raise RuntimeError(
            f"Envio parcial: {enviado} destino(s) entregues; {falhou} falha(s). "
            "O alerta permanece aprovado para revisão e reenvio."
        )
    return {"enviados": enviado, "falhas": 0}


def mascara_destino(canal: str, destino: str) -> str:
    """Exposto para telas administrativas sem revelar contatos cadastrados."""
    return _mascarar_destino(canal, destino)
