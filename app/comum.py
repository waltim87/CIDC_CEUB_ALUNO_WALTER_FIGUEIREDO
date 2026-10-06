"""Componentes compartilhados pelos painéis Streamlit."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError

AVISO_PROTOTIPO = (
    "Protótipo, sem validação oficial; confirme nos órgãos oficiais. "
    "Pesos e regras são hipóteses iniciais."
)


def cliente_supabase() -> Any:
    load_dotenv()
    try:
        url_secret = st.secrets.get("SUPABASE_URL")
        chave_secret = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    except StreamlitSecretNotFoundError:
        url_secret = None
        chave_secret = None
    url = url_secret or os.environ.get("SUPABASE_URL")
    chave = chave_secret or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError(
            "Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY nos Secrets "
            "do Streamlit ou no ambiente local. Não publique a chave no código."
        )
    from supabase import create_client

    return create_client(url, chave)


def mostrar_aviso() -> None:
    st.warning(AVISO_PROTOTIPO, icon="⚠️")


def carregar_pesos(cliente: Any) -> tuple[dict[str, float], bool]:
    from core.indice import carregar_pesos_supabase

    return carregar_pesos_supabase(cliente)


def carregar_municipios(cliente: Any) -> dict[str, dict[str, str]]:
    resultado = (
        cliente.table("municipios")
        .select("id_ibge,nome,uf")
        .order("nome")
        .limit(1000)
        .execute()
    )
    return {
        municipio["id_ibge"].strip(): municipio
        for municipio in (resultado.data or [])
    }
