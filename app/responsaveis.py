"""Responsáveis por área: matriz de quem responde por cada área em cada município.

O titular de uma área recebe automaticamente as tarefas do plano e as ocorrências passadas
para a equipe daquela área (migration 202610140027). Escrita só pela coordenação/admin.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

AREAS = {
    "coordenacao_geral": ("🏛️ Coordenação geral", "Plano de contingência, aprovação de alertas, decretos", "coordenador_municipal"),
    "monitoramento_alerta": ("📡 Monitoramento e alerta", "Estações, réguas, robô, meteorologia", "operador_monitoramento"),
    "campo_vistorias": ("📍 Campo e vistorias", "Registro de campo, famílias afetadas, áreas de risco", "agente_campo"),
    "saude": ("🏥 Saúde", "Atendimento nos abrigos e comunidades, vacinas, medicamentos", "saude_assistencia"),
    "assistencia_social": ("🤝 Assistência social", "Cadastro das famílias, benefícios, documentos", None),
    "logistica_estoque": ("📦 Logística e estoque", "Ajuda humanitária, combustível, distribuição", "logistica_abastecimento"),
    "abrigos": ("🏠 Abrigos", "Abertura, vistoria e ocupação dos abrigos", None),
    "embarcacoes_transporte": ("⛵ Embarcações e transporte", "Barcos, pilotos, rotas", None),
    "comunicacao_populacao": ("📢 Comunicação com a população", "Rádio, igrejas, escolas, Telegram", None),
    "voluntarios": ("🙋 Voluntários", "Cadastro, termo, relatos de campo, chat", "voluntario"),
    "obras_mitigacao": ("🏗️ Obras e mitigação", "Contenções, poços, elevação de casas", None),
    "areas_risco": ("⚠️ Áreas de risco", "Mapeamento e atualização das áreas de risco", None),
    "recuperacao_retorno": ("🔁 Recuperação e retorno", "Retorno das famílias, danos, reconstrução", None),
    "s2id_registro": ("📄 Registro no S2iD", "Ficha de afetados e danos para o sistema federal", None),
}
PERFIS_TELA = {"coordenador_municipal", "administrador", "gestor_nacional", "gestor_estadual",
               "operador_monitoramento", "agente_campo", "saude_assistencia", "logistica_abastecimento", "voluntario"}


def matriz(atribuicoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uma linha por área, com titular e suplente ativos (ou 'a definir')."""
    ativos = {(a["area"], a["papel"]): a for a in atribuicoes if not a.get("ate")}
    linhas = []
    for area, (rotulo, escopo, _funcao) in AREAS.items():
        titular, suplente = ativos.get((area, "titular")), ativos.get((area, "suplente"))
        linhas.append({
            "Área": rotulo, "O que cobre": escopo,
            "Titular": titular["nome_exibicao"] if titular else "⚠️ a definir",
            "Suplente": suplente["nome_exibicao"] if suplente else "—",
            "Contato": (titular or {}).get("contato_institucional") or "",
            "Desde": str((titular or {}).get("desde") or "")[:10],
        })
    return linhas


def areas_sem_titular(atribuicoes: list[dict[str, Any]]) -> list[str]:
    com_titular = {a["area"] for a in atribuicoes if not a.get("ate") and a["papel"] == "titular"}
    return [AREAS[a][0] for a in AREAS if a not in com_titular]


def renderizar_responsaveis() -> None:
    from app.comum import carregar_municipios, exigir_perfil
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("👥 Responsáveis por área")
    st.caption("Quem responde por cada área no município. O titular recebe automaticamente as tarefas do "
               "plano e as ocorrências passadas para a equipe da área dele; o suplente assume se não houver titular.")
    if st.session_state.get("_aviso_responsaveis"):
        st.success(st.session_state.pop("_aviso_responsaveis"))
    try:
        cliente, perfil = exigir_perfil(PERFIS_TELA)
        municipio_id = _municipio_da_tela(cliente, perfil, "responsaveis")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipio = carregar_municipios(cliente).get(municipio_id)
        atribuicoes = (cliente.table("responsaveis_area").select("*").eq("municipio_id", municipio_id)
                       .order("atribuido_em", desc=True).limit(500).execute().data or [])
    except PermissionError as erro:
        st.error(str(erro))
        return
    except Exception as erro:
        st.error(f"Não foi possível carregar (aplique a migration 202610140027): {erro}")
        return
    pode_editar = perfil["perfil"] == "administrador" or (
        perfil["perfil"] == "coordenador_municipal" and perfil.get("municipio_id") == municipio_id)

    faltando = areas_sem_titular(atribuicoes)
    c1, c2 = st.columns(2)
    c1.metric("Áreas com titular", f"{len(AREAS) - len(faltando)} de {len(AREAS)}")
    c2.metric("Áreas sem titular", len(faltando))
    if faltando:
        st.warning("Sem titular: " + ", ".join(faltando) + ". Tarefas e ocorrências dessas áreas ficam só com a "
                   "equipe, sem uma pessoa responsável.")
    linhas = matriz(atribuicoes)
    st.dataframe(linhas, hide_index=True, width="stretch")

    if pode_editar:
        with st.expander("✏️ Definir ou trocar responsável", expanded=bool(faltando)):
            try:
                pessoas = {p["id"]: f"{p['nome']} ({p['perfil']})" for p in cliente.rpc("cidc_chat_pessoas", {}).execute().data or []
                           if str(p.get("municipio_id") or "").strip() == municipio_id}
            except Exception:
                pessoas = {}
            pessoas[perfil["id"]] = f"{perfil['nome']} (você)"
            area = st.selectbox("Área", list(AREAS), format_func=lambda a: AREAS[a][0], key=f"resp-area-{municipio_id}")
            with st.form(f"resp-form-{municipio_id}-{area}", clear_on_submit=True):
                c1, c2 = st.columns(2)
                papel = c1.radio("Papel", ["titular", "suplente"], horizontal=True,
                                 format_func={"titular": "Titular", "suplente": "Suplente"}.get)
                usuario_id = c2.selectbox("Pessoa com conta no CIDC", [None] + list(pessoas),
                                          format_func=lambda i: "— pessoa sem conta (informe o nome) —" if i is None else pessoas[i])
                c1, c2 = st.columns(2)
                nome_externo = c1.text_input("Nome (se a pessoa não tem conta)", max_chars=120,
                                             placeholder="Ex.: Secretaria Municipal de Saúde - Ana Souza")
                contato = c2.text_input("Contato institucional (opcional)", max_chars=120,
                                        placeholder="Ex.: (97) 3331-0000 / defesacivil@prefeitura")
                observacao = st.text_input("Observação", max_chars=300)
                st.caption("Use telefone ou e-mail institucional. Telefone pessoal só com autorização da pessoa (LGPD).")
                if st.form_submit_button("Salvar", type="primary"):
                    if not usuario_id and len(nome_externo.strip()) < 3:
                        st.error("Escolha uma pessoa com conta ou escreva o nome.")
                    else:
                        try:
                            cliente.rpc("cidc_responsavel_area_definir", {
                                "p_municipio_id": municipio_id, "p_area": area, "p_papel": papel,
                                "p_usuario_id": usuario_id, "p_nome_externo": nome_externo or None,
                                "p_contato": contato or None, "p_observacao": observacao or None}).execute()
                        except Exception as erro:
                            st.error(f"Não foi possível salvar: {getattr(erro, 'message', None) or erro}")
                        else:
                            st.session_state["_aviso_responsaveis"] = f"{AREAS[area][0]}: {papel} atualizado."
                            st.rerun()
            ativos = {a["id"]: a for a in atribuicoes if not a.get("ate")}
            if ativos:
                encerrar = st.selectbox("Encerrar uma atribuição", [None] + list(ativos), key=f"resp-encerrar-{municipio_id}",
                                        format_func=lambda i: "—" if i is None else
                                        f"{AREAS[ativos[i]['area']][0]} · {ativos[i]['papel']} · {ativos[i]['nome_exibicao']}")
                if encerrar and st.button("Encerrar", key=f"resp-btn-encerrar-{municipio_id}"):
                    try:
                        cliente.rpc("cidc_responsavel_area_encerrar", {"p_id": encerrar}).execute()
                    except Exception as erro:
                        st.error(f"Não foi possível encerrar: {getattr(erro, 'message', None) or erro}")
                    else:
                        st.session_state["_aviso_responsaveis"] = "Atribuição encerrada."
                        st.rerun()
    else:
        st.caption("Quem define os responsáveis é a coordenação municipal.")

    historico = [{"Área": AREAS.get(a["area"], (a["area"],))[0], "Papel": a["papel"], "Pessoa": a["nome_exibicao"],
                  "Desde": str(a["desde"])[:10], "Até": str(a.get("ate") or "atual")[:10],
                  "Observação": a.get("observacao") or ""} for a in atribuicoes]
    if historico:
        with st.expander(f"Histórico de atribuições ({len(historico)})"):
            st.dataframe(historico, hide_index=True, width="stretch")
    painel_relatorio(
        "Responsáveis por área",
        [("Matriz de responsáveis", linhas), ("Histórico", historico)],
        subtitulo=f"{municipio['nome']}/{municipio['uf']}" if municipio else municipio_id,
        resumo={"Áreas com titular": f"{len(AREAS) - len(faltando)} de {len(AREAS)}",
                "Sem titular": ", ".join(faltando) or "nenhuma"},
    )
