"""Avisos por Telegram para responsáveis de tarefas e ocorrências (resposta).

Reaproveita a classe ``Telegram`` de ``core/telegram_robo.py`` para enviar
mensagens. Sempre opt-in: só envia para quem vinculou o PRÓPRIO Telegram no robô
(voluntarios.telegram_chat_id). Assinaturas de alertas públicos não pertencem a usuários e
nunca são usadas aqui.

O token do Telegram vem do secret TELEGRAM_BOT_TOKEN (Streamlit Cloud secrets
ou variável de ambiente local).
"""

from __future__ import annotations

import os
from typing import Any

from core.telegram_robo import Telegram


def obter_token_telegram() -> str | None:
    """Lê o token do Telegram das variáveis de ambiente/secrets do Streamlit."""
    import streamlit as st

    # Tenta secrets do Streamlit Cloud primeiro, depois variável de ambiente.
    try:
        token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    except Exception:
        token = None
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None
    return token


def chat_id_do_usuario(cliente: Any, usuario_id: str) -> str | None:
    """Busca o chat_id do Telegram de um usuário.

    Só o vínculo do próprio usuário (voluntarios.telegram_chat_id, feito por ele no robô).
    Sem vínculo, não envia (opt-in).
    """
    try:
        # 1. Vínculo direto via cadastro de voluntário.
        v = (
            cliente.table("voluntarios")
            .select("telegram_chat_id")
            .eq("usuario_id", usuario_id)
            .not_.is_("telegram_chat_id", "null")
            .limit(1)
            .execute()
            .data
        )
        if v:
            return v[0].get("telegram_chat_id")

        # NÃO usar assinaturas_alerta: elas são da população (opt-in de alertas públicos) e não
        # pertencem a nenhum usuário. A versão anterior pegava a PRIMEIRA assinatura ativa de
        # qualquer pessoa e mandava avisos internos para um morador aleatório.
    except Exception:
        return None
    return None


def enviar_aviso_telegram(
    cliente: Any,
    chat_id: str,
    texto: str,
) -> tuple[bool, str | None]:
    """Envia uma mensagem pelo Telegram.

    Retorna (sucesso, erro_mensagem). Sucesso é True se o Telegram aceitou
    a mensagem, False se houve falha (rede, bot bloqueado, etc.).
    """
    token = obter_token_telegram()
    if not token:
        return False, "Token do Telegram não configurado (TELEGRAM_BOT_TOKEN)."

    try:
        telegram = Telegram(token)
        telegram.chamar("sendMessage", chat_id=chat_id, text=texto)
        return True, None
    except Exception as erro:
        return False, str(erro)[:300]


def registrar_notificacao(
    cliente: Any,
    municipio_id: str,
    tipo: str,
    entidade_id: str,
    usuario_id: str,
    chat_id: str,
    mensagem: str,
    sucesso: bool,
    erro: str | None = None,
) -> None:
    """Registra a notificação na tabela notificacoes_telegram (auditoria)."""
    try:
        cliente.table("notificacoes_telegram").insert({
            "municipio_id": municipio_id,
            "tipo": tipo,
            "entidade_id": entidade_id,
            "usuario_id": usuario_id,
            "chat_id": f"***{str(chat_id)[-4:]}",  # mascarado, LGPD
            "mensagem": mensagem,
            "status": "enviado" if sucesso else "falha",
            "erro": erro,
        }).execute()
    except Exception:
        pass  # não deixa a notificação falhar o fluxo principal


def notificar_responsavel_tarefa(
    cliente: Any,
    municipio_id: str,
    usuario_id: str,
    chat_id: str,
    descricao_tarefa: str,
    prazo: str | None = None,
    acao_id: str | None = None,
) -> None:
    """Envia aviso de nova tarefa do plano para o responsável via Telegram."""
    texto = (
        "✅ *Nova tarefa do Plano de Contingência*\n\n"
        f"{descricao_tarefa}\n"
    )
    if prazo:
        texto += f"\nPrazo: {prazo}"
    texto += "\n\nResponda no app para marcar como concluída.\n"
    texto += "\nConfirme sempre nos canais oficiais. Emergência: ligue 199 (Defesa Civil)."

    sucesso, erro = enviar_aviso_telegram(cliente, chat_id, texto)
    registrar_notificacao(
        cliente, municipio_id, "tarefa_plano", acao_id or "", usuario_id,
        chat_id, texto, sucesso, erro,
    )


def notificar_responsavel_ocorrencia(
    cliente: Any,
    municipio_id: str,
    usuario_id: str,
    chat_id: str,
    numero_ocorrencia: int | str,
    titulo: str,
    status: str,
    ocorrencia_id: str | None = None,
) -> None:
    """Envia aviso de ocorrência atribuída ao responsável via Telegram."""
    texto = (
        "🚑 *Nova ocorrência atribuída*\n\n"
        f"#{numero_ocorrencia} · {titulo}\n"
        f"Situação: {status}\n\n"
        "Acesse o app para ver os detalhes e atualizar o atendimento.\n"
        "\nConfirme sempre nos canais oficiais. Emergência: ligue 199 (Defesa Civil)."
    )

    sucesso, erro = enviar_aviso_telegram(cliente, chat_id, texto)
    registrar_notificacao(
        cliente, municipio_id, "ocorrencia", ocorrencia_id or "", usuario_id,
        chat_id, texto, sucesso, erro,
    )


def notificar_responsaveis_por_funcao(
    cliente: Any,
    municipio_id: str,
    funcao: str,
    descricao_tarefa: str,
    prazo: str | None = None,
    acao_id: str | None = None,
) -> None:
    """Envia aviso de nova tarefa para todos os usuários da função no município que têm Telegram vinculado.

    Opt-in: só envia para quem tem telegram_chat_id (voluntários) ou assinatura ativa no Telegram.
    """
    usuarios = (
        cliente.table("usuarios")
        .select("id, nome")
        .eq("perfil", funcao)
        .eq("municipio_id", municipio_id)
        .execute().data or []
    )
    for u in usuarios:
        chat_id = chat_id_do_usuario(cliente, u["id"])
        if not chat_id:
            continue
        texto = (
            "✅ *Nova tarefa do Plano de Contingência*\n\n"
            f"{descricao_tarefa}\n"
        )
        if prazo:
            texto += f"\nPrazo: {prazo}"
        texto += "\n\nResponda no app para marcar como concluída.\n"
        texto += "\nConfirme sempre nos canais oficiais. Emergência: ligue 199 (Defesa Civil)."

        sucesso, erro = enviar_aviso_telegram(cliente, chat_id, texto)
        registrar_notificacao(
            cliente, municipio_id, "tarefa_plano", acao_id or "", u["id"],
            chat_id, texto, sucesso, erro,
        )
