"""Entrada com autenticação e navegação conforme perfil autorizado."""

from __future__ import annotations

import sys
from pathlib import Path

# O Streamlit Cloud não põe a raiz do repositório no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.auth import (
    cliente_publico,
    encerrar_sessao,
    obter_perfil,
    renderizar_login,
)
from app.paineis import (
    renderizar_alertas,
    renderizar_administracao,
    renderizar_agente_campo,
    renderizar_gestor,
    renderizar_painel_principal,
    renderizar_pesquisador,
    renderizar_publico,
    renderizar_saude,
    renderizar_logistica,
    renderizar_coordenador,
    renderizar_monitoramento,
)

st.set_page_config(page_title="CIDC | Defesa Civil", page_icon="🌧️", layout="wide")

try:
    cliente = cliente_publico()
    perfil = obter_perfil(cliente)
except PermissionError as erro:
    st.error(str(erro))
    if st.button("Sair desta conta", use_container_width=True):
        try:
            encerrar_sessao(cliente)
            st.rerun()
        except Exception as falha:
            st.error(f"A sessão local foi encerrada, mas o logout remoto falhou: {falha}")
    st.stop()
except Exception as erro:
    st.error(f"Não foi possível iniciar a aplicação: {erro}")
    st.stop()

pagina_publica = st.Page(renderizar_publico, title="Situação pública", icon="🌎")

if perfil is None:
    st.navigation(
        [
            st.Page(renderizar_login, title="Entrar", icon="🔐", default=True),
            pagina_publica,
        ],
        position="sidebar",
    ).run()
else:
    st.sidebar.success(f"{perfil['nome']} · {perfil['perfil']}")
    if st.sidebar.button("Sair", use_container_width=True):
        try:
            encerrar_sessao(cliente)
            st.rerun()
        except Exception as erro:
            st.error(f"A sessão local foi encerrada, mas o logout remoto falhou: {erro}")

    paginas = [
        st.Page(renderizar_painel_principal, title="Painel principal", icon="📊"),
        pagina_publica,
    ]
    nome_perfil = perfil["perfil"]
    if nome_perfil in {"gestor_nacional", "gestor_estadual", "administrador"}:
        paginas.insert(
            1,
            st.Page(renderizar_gestor, title="Visão estadual/nacional", icon="🗺️"),
        )
    if nome_perfil in {
        "gestor_nacional",
        "gestor_estadual",
        "administrador",
        "operador_monitoramento",
        "coordenador_municipal",
    }:
        paginas.append(
            st.Page(renderizar_alertas, title="Revisão de alertas", icon="🚨")
        )
    if nome_perfil in {"coordenador_municipal", "administrador"}:
        paginas.append(
            st.Page(renderizar_coordenador, title="Gestão municipal", icon="🏘️")
        )
    if nome_perfil in {"operador_monitoramento", "administrador"}:
        paginas.append(
            st.Page(renderizar_monitoramento, title="Sala de monitoramento", icon="📡")
        )
    if nome_perfil in {"agente_campo", "coordenador_municipal", "administrador"}:
        paginas.append(
            st.Page(renderizar_agente_campo, title="Registro de campo", icon="📍")
        )
    if nome_perfil in {"saude_assistencia", "coordenador_municipal", "administrador"}:
        paginas.append(
            st.Page(renderizar_saude, title="Saúde e assistência", icon="🏥")
        )
    if nome_perfil in {"logistica_abastecimento", "coordenador_municipal", "administrador"}:
        paginas.append(
            st.Page(renderizar_logistica, title="Logística e recursos", icon="🚤")
        )
    if nome_perfil in {"pesquisador", "administrador"}:
        paginas.append(
            st.Page(renderizar_pesquisador, title="Dados e metodologia", icon="📚")
        )
    if nome_perfil == "administrador":
        paginas.append(
            st.Page(renderizar_administracao, title="Administração", icon="⚙️")
        )
    st.navigation(paginas, position="sidebar").run()
