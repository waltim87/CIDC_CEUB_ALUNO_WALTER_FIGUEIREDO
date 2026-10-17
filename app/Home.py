"""Entrada com autenticação e navegação conforme perfil autorizado."""

from __future__ import annotations

import sys
from pathlib import Path

# O Streamlit Cloud não põe a raiz do repositório no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.auth import (
    CadastroIncompleto,
    cliente_publico,
    processar_retorno_google,
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
from app.voluntarios import renderizar_meu_cadastro, renderizar_relatos
from app.meteorologia import renderizar_meteorologia
from app.familias import renderizar_familias, usuario_coordena_abrigo
from app.familias_retorno import renderizar_familias_retorno
from app.licoes_aprendidas import renderizar_licoes_aprendidas
from app.permissoes import renderizar_permissoes
from app.chat import PERFIS_CHAT, renderizar_chat
from app.ajuda import PERFIS_TELA as PERFIS_AJUDA, renderizar_ajuda
from app.areas_risco import renderizar_areas_risco
from app.abrigo_vistoria import renderizar_abrigo_vistoria
from app.s2id import renderizar_s2id
from app.calendario_risco import renderizar_calendario_risco
from app.ocorrencias import PERFIS_TELA as PERFIS_OCORRENCIAS, renderizar_ocorrencias
from app.plano import PERFIS_EQUIPE, PERFIS_LEITURA, _municipio_da_tela, renderizar_minhas_tarefas, renderizar_plano

st.set_page_config(page_title="CIDC | Defesa Civil", page_icon="🌧️", layout="wide")

processar_retorno_google()

try:
    cliente = cliente_publico()
    perfil = obter_perfil(cliente)
except CadastroIncompleto as pendente:
    from app.comum import carregar_municipios
    from app.voluntarios import formulario_completar_cadastro

    if formulario_completar_cadastro(cliente, carregar_municipios(cliente), pendente.usuario):
        st.session_state.pop("cidc_perfil", None)
        st.rerun()
    if st.button("Sair desta conta"):
        encerrar_sessao(cliente)
        st.rerun()
    st.stop()
except PermissionError as erro:
    st.error(str(erro))
    if st.button("Sair desta conta", width="stretch"):
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
    if st.sidebar.button("Sair", width="stretch"):
        try:
            encerrar_sessao(cliente)
            st.rerun()
        except Exception as erro:
            st.error(f"A sessão local foi encerrada, mas o logout remoto falhou: {erro}")

    if st.sidebar.button("🔄 Atualizar dados", width="stretch",
                         help="Os dados das coletas ficam guardados por até 10 minutos para o site abrir rápido."):
        st.cache_data.clear()
        st.session_state.pop("cidc_perfil", None)
        st.rerun()

    paginas = [
        st.Page(renderizar_painel_principal, title="Painel principal", icon="📊"),
        pagina_publica,
    ]
    nome_perfil = perfil["perfil"]
    leitor = nome_perfil == "voluntario"  # lê tudo, não aprova alertas nem edita cadastros
    if nome_perfil != "pesquisador":
        paginas.insert(1, st.Page(renderizar_relatos, title="Relatos de campo", icon="📢"))
    if nome_perfil in PERFIS_EQUIPE and nome_perfil != "coordenador_municipal":
        paginas.insert(1, st.Page(renderizar_minhas_tarefas, title="Minhas tarefas", icon="✅"))
    if nome_perfil in PERFIS_AJUDA or usuario_coordena_abrigo(cliente, perfil["id"]):
        paginas.insert(1, st.Page(renderizar_ajuda, title="Ajuda humanitária", icon="📦"))
    paginas.insert(1, st.Page(lambda: renderizar_abrigo_vistoria(cliente, perfil), title="Abrigo pronto", icon="🏘️"))
    paginas.insert(1, st.Page(lambda: renderizar_s2id(cliente, perfil), title="Ficha S2iD", icon="📄"))
    paginas.insert(1, st.Page(lambda: renderizar_familias_retorno(cliente, perfil), title="Retorno famílias", icon="🏠"))
    paginas.insert(1, st.Page(lambda: renderizar_licoes_aprendidas(cliente, perfil), title="Lições aprendidas", icon="📋"))
    paginas.insert(1, st.Page(lambda: renderizar_areas_risco(cliente, perfil), title="Áreas de risco", icon="⚠️"))
    paginas.insert(1, st.Page(lambda: renderizar_calendario_risco(cliente, perfil), title="Calendário de risco", icon="📅"))
    if nome_perfil in PERFIS_OCORRENCIAS:
        paginas.insert(1, st.Page(renderizar_ocorrencias, title="Ocorrências", icon="🚑"))
    if nome_perfil in PERFIS_LEITURA:
        paginas.insert(1, st.Page(renderizar_plano, title="Plano de contingência", icon="📋"))
    if nome_perfil in PERFIS_CHAT:
        paginas.insert(1, st.Page(renderizar_chat, title="Chat interno", icon="💬"))
    paginas.insert(1, st.Page(renderizar_meteorologia, title="Meteorologia", icon="🌦️"))
    if leitor:
        paginas.insert(1, st.Page(renderizar_meu_cadastro, title="Meu cadastro", icon="🙋"))
    if nome_perfil in {"gestor_nacional", "gestor_estadual", "administrador"} or leitor:
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
    } or leitor:
        paginas.append(
            st.Page(renderizar_alertas, title="Alertas" if leitor else "Revisão de alertas", icon="🚨")
        )
    if nome_perfil in {"coordenador_municipal", "administrador"} or leitor:
        paginas.append(
            st.Page(renderizar_coordenador, title="Gestão municipal", icon="🏘️")
        )
    if nome_perfil in {"operador_monitoramento", "administrador"} or leitor:
        paginas.append(
            st.Page(renderizar_monitoramento, title="Sala de monitoramento", icon="📡")
        )
    if nome_perfil in {"agente_campo", "coordenador_municipal", "administrador"}:
        paginas.append(
            st.Page(renderizar_agente_campo, title="Registro de campo", icon="📍")
        )
    if nome_perfil in {"saude_assistencia", "coordenador_municipal", "administrador"} or leitor:
        paginas.append(
            st.Page(renderizar_saude, title="Saúde e assistência", icon="🏥")
        )
    if nome_perfil in {"logistica_abastecimento", "coordenador_municipal", "administrador"} or leitor:
        paginas.append(
            st.Page(renderizar_logistica, title="Logística e recursos", icon="🚤")
        )
    if nome_perfil in {"pesquisador", "administrador"}:
        paginas.append(
            st.Page(renderizar_pesquisador, title="Dados e metodologia", icon="📚")
        )
    if nome_perfil in {"administrador", "coordenador_municipal", "saude_assistencia"} or usuario_coordena_abrigo(
        cliente, perfil["id"]
    ):
        paginas.append(st.Page(renderizar_familias, title="Famílias abrigadas", icon="👪"))
    if nome_perfil in {"administrador", "coordenador_municipal"}:
        paginas.append(st.Page(renderizar_permissoes, title="Usuários e permissões", icon="🔑"))
    if nome_perfil == "administrador":
        paginas.append(
            st.Page(renderizar_administracao, title="Administração", icon="⚙️")
        )
    st.navigation(paginas, position="sidebar").run()
