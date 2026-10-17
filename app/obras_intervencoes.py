"""Obras e intervenções (mitigação).

Cadastro de obras com status, valor, fonte do recurso e comunidades
beneficiadas. Indicador: quantas pessoas saíram da área de risco com cada
ação.

Somente coordenação e administração podem cadastrar/editar/excluir.
A leitura segue o município do usuário (RLS no banco).
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

import streamlit as st

TIPOS = {
    "contencao_margem": ("🌊 Contenção de margem"),
    "eleve_casas": ("🏠 Elevação de casas (marombas)"),
    "poço": ("💧 Poço"),
    "ponte": ("🌉 Ponte"),
    "outro": ("❓ Outro"),
}
STATUS = {
    "planejada": ("⏳ Planejada"),
    "em_andamento": ("🔧 Em andamento"),
    "concluida": ("✅ Concluída"),
    "cancelada": ("🚫 Cancelada"),
    "suspensa": ("⏸️ Suspensa"),
}
PERFIS_TELA = {
    "coordenador_municipal", "administrador", "gestor_nacional",
    "gestor_estadual", "operador_monitoramento", "voluntario",
    "agente_campo", "saude_assistencia", "logistica_abastecimento",
    "pesquisador",
}
FUSO_MANHAS = timezone(timedelta(hours=-4))


def _numero(valor: Any) -> str:
    if valor is None:
        return "—"
    numero = float(valor)
    return f"{numero:,.0f}".replace(",", ".") if numero.is_integer() else f"{numero:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _moeda(valor: Any) -> str:
    if valor is None:
        return "—"
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _hora_local(valor: str | None) -> str:
    """UTC ISO -> 'dd/mm HH:MM (Manaus)'; Manaus = UTC-4."""
    if not valor:
        return "—"
    from datetime import datetime
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(FUSO_MANHAS).strftime("%d/%m %H:%M") + " (Manaus)"


def renderizar_obras_intervencoes(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("🏗️ Obras e intervenções")
    st.caption("Cadastro de obras de mitigação com status, valor, fonte do recurso e "
               "comunidades beneficiadas. Indicador: pessoas retiradas da área de risco.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "obras_intervencoes")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_gerenciar = perfil["perfil"] in {"coordenador_municipal", "administrador"}

    try:
        obras = (cliente.table("obras_intervencoes")
                 .select("id,nome,descricao,tipo,status,valor,fonte_recurso,"
                         "comunidades_beneficiadas,pessoas_retiradas_risco,"
                         "data_inicio,data_previsao_termino,data_termino,"
                         "responsavel,observacoes,registrado_em,atualizado_em")
                 .eq("municipio_id", municipio_id)
                 .order("registrado_em", desc=True)
                 .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar as obras (aplique a migration 202610140023): {erro}")
        return

    # ---------- KPIs ----------
    total = len(obras)
    concluidas = sum(1 for o in obras if o.get("status") == "concluida")
    em_andamento = sum(1 for o in obras if o.get("status") == "em_andamento")
    valor_total = sum(float(o.get("valor") or 0) for o in obras)
    pessoas_retiradas = sum(int(o.get("pessoas_retiradas_risco") or 0) for o in obras)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Obras cadastradas", total)
    c2.metric("Concluídas", concluidas)
    c3.metric("Em andamento", em_andamento)
    c4.metric("Pessoas retiradas de risco", pessoas_retiradas)

    # ---------- Cadastro / edição ----------
    st.subheader("Cadastrar ou editar obra")

    if pode_gerenciar:
        obra_opcoes = {o["id"]: o["nome"] for o in obras}
        obra_id = st.selectbox(
            "Obra (para editar) ou deixe em branco para nova",
            [None] + list(obra_opcoes),
            format_func=lambda i: "Nova obra" if i is None else obra_opcoes[i],
            key="obra-selecao",
        )
        existente = next((o for o in obras if o["id"] == obra_id), None) if obra_id else None

        with st.form("form_obra", clear_on_submit=False):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome da obra *", max_chars=200,
                                 value=existente.get("nome") if existente else "",
                                 placeholder="Ex.: Contenção da margem do rio São Raimundo")
            tipo = c2.selectbox("Tipo", list(TIPOS),
                                index=list(TIPOS).index(existente.get("tipo")) if existente and existente.get("tipo") in TIPOS else 0,
                                format_func=lambda t: TIPOS[t][0])
            c1, c2 = st.columns(2)
            status = c1.selectbox("Status", list(STATUS),
                                  index=list(STATUS).index(existente.get("status")) if existente and existente.get("status") in STATUS else 0,
                                  format_func=lambda s: STATUS[s][0])
            valor = c2.number_input("Valor (R$)", min_value=0.0, step=100.0,
                                    value=float(existente.get("valor")) if existente and existente.get("valor") else 0.0)
            c1, c2 = st.columns(2)
            fonte_recurso = c1.text_input("Fonte do recurso", max_chars=200,
                                          value=existente.get("fonte_recurso") if existente else "",
                                          placeholder="Ex.: Defesa Civil Estadual, Governo Federal")
            responsavel = c2.text_input("Responsável", max_chars=200,
                                        value=existente.get("responsavel") if existente else "")
            comunidades = st.multiselect(
                "Comunidades beneficiadas",
                options=[],  # será preenchido abaixo
                default=existente.get("comunidades_beneficiadas") or [] if existente else [],
                key="obra-comunidades",
            )
            # Carrega comunidades do município para o multiselect
            try:
                coms = (cliente.table("comunidades")
                        .select("id,nome")
                        .eq("municipio_id", municipio_id)
                        .order("nome")
                        .execute().data or [])
                st.session_state["obra-comunidades"] = [c["nome"] for c in coms]
                com_map = {c["nome"]: c["id"] for c in coms}
            except Exception:
                com_map = {}
            pessoas_retiradas_input = st.number_input(
                "Pessoas retiradas da área de risco", min_value=0, step=1,
                value=int(existente.get("pessoas_retiradas_risco") or 0) if existente else 0)
            c1, c2, c3 = st.columns(3)
            data_inicio = c1.date_input("Data de início", value=None,
                                        format="DD/MM/YYYY", key="obra-data-inicio")
            data_previsao = c2.date_input("Previsão de término", value=None,
                                          format="DD/MM/YYYY", key="obra-data-previsao")
            data_termino = c3.date_input("Data de término", value=None,
                                         format="DD/MM/YYYY", key="obra-data-termino")
            observacoes = st.text_area("Observações", max_chars=1000,
                                       value=existente.get("observacoes") if existente else "")
            if st.form_submit_button("Salvar obra", type="primary"):
                if len(nome.strip()) < 5:
                    st.error("Informe o nome da obra (mínimo 5 caracteres).")
                else:
                    try:
                        cliente.rpc("cidc_obra_cadastrar", {
                            "p_id": obra_id,
                            "p_municipio_id": municipio_id,
                            "p_nome": nome.strip(),
                            "p_descricao": None,
                            "p_tipo": tipo,
                            "p_status": status,
                            "p_valor": valor or None,
                            "p_fonte_recurso": fonte_recurso.strip() or None,
                            "p_comunidades_beneficiadas": comunidades or None,
                            "p_pessoas_retiradas_risco": int(pessoas_retiradas_input) or None,
                            "p_data_inicio": data_inicio.isoformat() if data_inicio else None,
                            "p_data_previsao_termino": data_previsao.isoformat() if data_previsao else None,
                            "p_data_termino": data_termino.isoformat() if data_termino else None,
                            "p_responsavel": responsavel.strip() or None,
                            "p_observacoes": observacoes.strip() or None,
                        }).execute()
                        st.success("Obra salva com sucesso.")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Não foi possível salvar: {erro}")
    elif not pode_gerenciar:
        st.info("Cadastro e edição de obras estão disponíveis para coordenação e administração.")

    # ---------- Lista ----------
    st.subheader("Obras cadastradas")
    if not obras:
        st.success("Nenhuma obra cadastrada neste município ainda.")
    else:
        linhas_tabela = []
        for o in obras:
            linhas_tabela.append({
                "Obra": o["nome"],
                "Tipo": TIPOS[o["tipo"]][0],
                "Status": STATUS[o["status"]][0],
                "Valor": _moeda(o.get("valor")),
                "Fonte": o.get("fonte_recurso") or "—",
                "Comunidades": ", ".join(o.get("comunidades_beneficiadas") or []),
                "Pessoas de risco": o.get("pessoas_retiradas_risco") or 0,
                "Início": _data_br(o.get("data_inicio")),
                "Término": _data_br(o.get("data_termino")),
                "Responsável": o.get("responsavel") or "—",
            })
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Relatório ----------
    linhas_relatorio = []
    for o in obras:
        linhas_relatorio.append({
            "Obra": o["nome"],
            "Tipo": TIPOS[o["tipo"]][0],
            "Status": STATUS[o["status"]][0],
            "Valor": o.get("valor") or 0,
            "Fonte do recurso": o.get("fonte_recurso") or "",
            "Comunidades beneficiadas": ", ".join(o.get("comunidades_beneficiadas") or []),
            "Pessoas retiradas de risco": o.get("pessoas_retiradas_risco") or 0,
            "Data início": _data_br(o.get("data_inicio")),
            "Data término": _data_br(o.get("data_termino")),
            "Responsável": o.get("responsavel") or "",
            "Observações": o.get("observacoes") or "",
        })
    painel_relatorio(
        "Obras e intervenções",
        [("Obras cadastradas", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Obras cadastradas": total, "Concluídas": concluidas,
                "Em andamento": em_andamento,
                "Valor total (R$)": valor_total,
                "Pessoas retiradas de risco": pessoas_retiradas},
    )
