"""Autenticação Supabase Auth e resolução do perfil autorizado."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError


def _segredo(nome: str) -> str | None:
    try:
        valor = st.secrets.get(nome)
    except StreamlitSecretNotFoundError:
        valor = None
    return valor or os.environ.get(nome)


def cliente_publico() -> Any:
    load_dotenv()
    url = _segredo("SUPABASE_URL")
    chave = _segredo("SUPABASE_ANON_KEY")
    if not url or not chave:
        raise RuntimeError(
            "Configure SUPABASE_URL e SUPABASE_ANON_KEY nos Secrets do Streamlit "
            "ou no ambiente local. A chave service_role não deve ser usada no painel."
        )
    from supabase import create_client

    cliente = create_client(url, chave)
    sessao_salva = st.session_state.get("supabase_auth")
    if sessao_salva:
        try:
            cliente.auth.set_session(
                sessao_salva["access_token"],
                sessao_salva["refresh_token"],
            )
            sessao_atual = cliente.auth.get_session()
            if sessao_atual:
                st.session_state["supabase_auth"] = {
                    "access_token": sessao_atual.access_token,
                    "refresh_token": sessao_atual.refresh_token,
                    "user_id": sessao_atual.user.id,
                }
            else:
                st.session_state.pop("supabase_auth", None)
                st.session_state.pop("cidc_perfil", None)
                st.warning("Sessão expirada; entre novamente.")
        except Exception as erro:
            st.session_state.pop("supabase_auth", None)
            st.session_state.pop("cidc_perfil", None)
            st.warning(f"Sessão expirada; entre novamente. Detalhe: {erro}")
    return cliente


def obter_perfil(cliente: Any) -> dict[str, Any] | None:
    sessao = cliente.auth.get_session()
    if not sessao:
        st.session_state.pop("cidc_perfil", None)
        return None

    usuario_id = sessao.user.id
    resultado = (
        cliente.table("usuarios")
        .select("id,nome,perfil,municipio_id,auth_id")
        .eq("auth_id", usuario_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise PermissionError(
            "Sua conta autenticou, mas ainda não recebeu um perfil CIDC. "
            "Peça ao administrador para associar seu usuário Auth a um perfil."
        )
    perfil = resultado.data[0]
    if perfil["perfil"] not in {
        "gestor_nacional",
        "gestor_estadual",
        "coordenador_municipal",
        "operador_monitoramento",
        "agente_campo",
        "saude_assistencia",
        "logistica_abastecimento",
        "pesquisador",
        "administrador",
    }:
        raise PermissionError(f"Perfil CIDC não reconhecido: {perfil['perfil']}")
    perfil["municipio_id"] = (
        perfil["municipio_id"].strip() if perfil.get("municipio_id") else None
    )
    st.session_state["cidc_perfil"] = perfil
    return perfil


def autenticar(email: str, senha: str) -> dict[str, str]:
    cliente = cliente_publico()
    resposta = cliente.auth.sign_in_with_password(
        {"email": email.strip(), "password": senha}
    )
    sessao = resposta.session
    if not sessao or not sessao.user:
        raise RuntimeError("O Supabase Auth não retornou uma sessão válida")
    st.session_state["supabase_auth"] = {
        "access_token": sessao.access_token,
        "refresh_token": sessao.refresh_token,
        "user_id": sessao.user.id,
    }
    st.session_state.pop("cidc_perfil", None)
    return {"user_id": sessao.user.id}


def encerrar_sessao(cliente: Any) -> None:
    try:
        cliente.auth.sign_out()
    finally:
        st.session_state.pop("supabase_auth", None)
        st.session_state.pop("cidc_perfil", None)


def renderizar_login() -> None:
    st.title("Entrar na plataforma")
    st.caption("Entre com uma conta criada no Supabase Auth e vinculada a um perfil CIDC.")
    with st.form("formulario-login"):
        email = st.text_input("E-mail", autocomplete="email")
        senha = st.text_input("Senha", type="password", autocomplete="current-password")
        enviado = st.form_submit_button("Entrar")
    if enviado:
        if not email.strip() or not senha:
            st.error("Informe e-mail e senha.")
            return
        try:
            autenticar(email, senha)
            st.rerun()
        except Exception as erro:
            st.error(f"Não foi possível autenticar: {erro}")
    st.info(
        "O cadastro de usuários e a atribuição de perfis são controlados pelo "
        "administrador. Não use uma conta sem município/perfil autorizado."
    )
