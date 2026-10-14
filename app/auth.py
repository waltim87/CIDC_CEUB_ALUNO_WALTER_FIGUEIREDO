"""Autenticação Supabase Auth e resolução do perfil autorizado."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import requests

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError


URL_APP_PADRAO = "https://sistematizacao-defesa-civil-walter-ceub-eng-ia.streamlit.app"


class CadastroIncompleto(PermissionError):
    """Conta autenticada (ex.: Google) que ainda não completou os dados do CIDC."""

    def __init__(self, usuario: Any) -> None:
        super().__init__("Complete seus dados para usar o CIDC.")
        self.usuario = usuario


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

    def consultar() -> Any:
        return (
            cliente.table("usuarios")
            .select("id,nome,perfil,municipio_id,auth_id")
            .eq("auth_id", usuario_id)
            .limit(1)
            .execute()
        )

    resultado = consultar()
    if not resultado.data:
        # Autocadastro de voluntário: conclui no primeiro login com os dados guardados na conta.
        from app.voluntarios import concluir_cadastro_pendente

        try:
            if concluir_cadastro_pendente(cliente, getattr(sessao.user, "user_metadata", None) or {}):
                resultado = consultar()
        except Exception as erro:
            raise PermissionError(f"Não foi possível concluir o cadastro de voluntário: {erro}") from erro
    if not resultado.data:
        # Ex.: primeiro acesso com Google. A tela "Complete seus dados" cria o perfil.
        raise CadastroIncompleto(sessao.user)
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
        "voluntario",
    }:
        raise PermissionError(f"Perfil CIDC não reconhecido: {perfil['perfil']}")
    perfil["municipio_id"] = (
        perfil["municipio_id"].strip() if perfil.get("municipio_id") else None
    )
    st.session_state["cidc_perfil"] = perfil
    return perfil


def _guardar_sessao(access_token: str, refresh_token: str, user_id: str) -> None:
    st.session_state["supabase_auth"] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
    }
    st.session_state.pop("cidc_perfil", None)


# ---------------------------------------------------------------- login com Google
# Fluxo OAuth com PKCE do Supabase Auth: o verificador fica guardado no servidor (nunca
# vai para o navegador) e é identificado por um código aleatório que volta na URL.
@st.cache_resource(show_spinner=False)
def _logins_pendentes() -> dict[str, tuple[str, float]]:
    return {}


# Curto: ao ativar o Google no Supabase, o botão aparece em até 1 minuto.
@st.cache_data(ttl=60, show_spinner=False)
def google_habilitado(url: str, chave: str) -> bool:
    try:
        resposta = requests.get(f"{url}/auth/v1/settings", headers={"apikey": chave}, timeout=10)
        return bool((resposta.json().get("external") or {}).get("google"))
    except Exception:
        return False


def link_google() -> str | None:
    url, chave = _segredo("SUPABASE_URL"), _segredo("SUPABASE_ANON_KEY")
    if not url or not chave or not google_habilitado(url, chave):
        return None
    pendentes = _logins_pendentes()
    agora = time.time()
    for estado in [e for e, (_, criado) in pendentes.items() if agora - criado > 900]:
        pendentes.pop(estado, None)
    estado = st.session_state.get("cidc_estado_google")
    if not estado or estado not in pendentes:
        estado = secrets.token_urlsafe(16)
        pendentes[estado] = (secrets.token_urlsafe(64), agora)
        st.session_state["cidc_estado_google"] = estado
    desafio = base64.urlsafe_b64encode(hashlib.sha256(pendentes[estado][0].encode()).digest()).rstrip(b"=").decode()
    retorno = f"{(_segredo('APP_URL') or URL_APP_PADRAO).rstrip('/')}/?cidc_estado={estado}"
    return f"{url}/auth/v1/authorize?" + urlencode({
        "provider": "google", "redirect_to": retorno,
        "code_challenge": desafio, "code_challenge_method": "s256",
    })


def processar_retorno_google() -> None:
    """Conclui o login quando o Google/Supabase devolve o usuário com ?code=... na URL."""
    parametros = st.query_params
    if parametros.get("error_description") or parametros.get("error"):
        st.error(f"Login com Google não concluído: {parametros.get('error_description') or parametros.get('error')}")
        st.query_params.clear()
        return
    codigo, estado = parametros.get("code"), parametros.get("cidc_estado")
    if not codigo:
        return
    st.query_params.clear()
    pendente = _logins_pendentes().pop(estado or "", None)
    if not pendente:
        st.warning("O link de login expirou. Toque em \"Entrar com Google\" de novo.")
        return
    url, chave = _segredo("SUPABASE_URL"), _segredo("SUPABASE_ANON_KEY")
    try:
        resposta = requests.post(
            f"{url}/auth/v1/token?grant_type=pkce",
            headers={"apikey": chave, "Content-Type": "application/json"},
            json={"auth_code": codigo, "code_verifier": pendente[0]},
            timeout=20,
        )
        corpo = resposta.json()
        if resposta.status_code != 200:
            raise RuntimeError(corpo.get("msg") or corpo.get("error_description") or resposta.status_code)
        _guardar_sessao(corpo["access_token"], corpo["refresh_token"], corpo["user"]["id"])
    except Exception as erro:
        st.error(f"Não foi possível concluir o login com Google: {erro}")
        return
    st.rerun()


def autenticar(email: str, senha: str) -> dict[str, str]:
    cliente = cliente_publico()
    resposta = cliente.auth.sign_in_with_password(
        {"email": email.strip(), "password": senha}
    )
    sessao = resposta.session
    if not sessao or not sessao.user:
        raise RuntimeError("O Supabase Auth não retornou uma sessão válida")
    _guardar_sessao(sessao.access_token, sessao.refresh_token, sessao.user.id)
    return {"user_id": sessao.user.id}


def encerrar_sessao(cliente: Any) -> None:
    try:
        cliente.auth.sign_out()
    finally:
        st.session_state.pop("supabase_auth", None)
        st.session_state.pop("cidc_perfil", None)


def renderizar_login() -> None:
    st.title("Centro de Inteligência da Defesa Civil")
    aba_entrar, aba_voluntario = st.tabs(["🔐 Entrar", "🙋 Quero ser voluntário"])
    with aba_voluntario:
        if link_google():
            st.info("Tem conta Google? Use **Entrar com Google** na aba Entrar: no primeiro acesso "
                    "você completa estes dados e aceita o termo, sem criar senha.")
        from app.comum import carregar_municipios
        from app.voluntarios import formulario_cadastro_voluntario

        try:
            formulario_cadastro_voluntario(carregar_municipios(cliente_publico()))
        except Exception as erro:
            st.error(f"Cadastro de voluntário indisponível: {erro}")
    with aba_entrar:
        _formulario_login()


def _formulario_login() -> None:
    link = link_google()
    if link:
        st.link_button("Entrar com Google", link, type="primary", icon=":material/account_circle:")
        st.caption("Abre o Google em uma nova aba; depois de escolher a conta, você volta ao CIDC já conectado. "
                   "No primeiro acesso, completa seus dados.")
        st.divider()
    st.caption("Ou entre com seu e-mail e senha.")
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
        "Equipes da Defesa Civil: contas criadas pelo administrador. Voluntários: "
        "cadastrem-se na aba \"Quero ser voluntário\"."
    )
