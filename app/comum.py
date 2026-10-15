"""Componentes compartilhados pelos painéis Streamlit."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.auth import cliente_publico, obter_perfil

AVISO_PROTOTIPO = (
    "Protótipo, sem validação oficial; confirme nos órgãos oficiais. "
    "Pesos e regras são hipóteses iniciais."
)


# Dados que só mudam com a coleta (a cada 3 h) ficam em cache por alguns minutos.
# Tabelas públicas: cache único. Tabelas com RLS por perfil: cache separado por usuário.
TTL_COLETA_S = 600
TTL_CADASTRO_S = 3600


def chave_usuario() -> str:
    return (st.session_state.get("supabase_auth") or {}).get("user_id") or "anonimo"


def cliente_supabase() -> Any:
    return cliente_publico()


def exigir_perfil(perfis: set[str]) -> tuple[Any, dict[str, Any]]:
    cliente = cliente_supabase()
    perfil = obter_perfil(cliente)
    if not perfil or perfil["perfil"] not in perfis:
        raise PermissionError("Seu perfil não tem acesso a este painel.")
    return cliente, perfil


def mostrar_aviso() -> None:
    st.warning(AVISO_PROTOTIPO, icon="⚠️")


def carregar_pesos(cliente: Any) -> tuple[dict[str, float], bool]:
    from core.indice import carregar_pesos_supabase

    return carregar_pesos_supabase(cliente)


def carregar_municipios(cliente: Any) -> dict[str, dict[str, str]]:
    return _municipios(cliente)


@st.cache_data(ttl=TTL_CADASTRO_S, show_spinner=False)
def _municipios(_cliente: Any) -> dict[str, dict[str, str]]:
    # municipios tem leitura pública (RLS using true): o mesmo resultado para todos.
    cliente = _cliente
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
