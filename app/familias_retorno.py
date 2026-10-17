"""Retorno das famílias (recuperação).

Acompanha quem voltou para casa, quem não tem para onde ir e o que falta
(reforma, documentos, benefícios). Respeita a LGPD: dados das famílias
são visíveis a quem já pode vê-las (coordenação, saúde/assistência,
coordenador do abrigo, administração).
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Any

import streamlit as st

FUSO_MANHAS = timezone(timedelta(hours=-4))


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _sim_nao(valor: Any) -> str:
    if valor is None:
        return "—"
    return "Sim" if valor else "Não"


def renderizar_familias_retorno(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("🏠 Retorno das famílias")
    st.caption("Acompanha quem voltou para casa, quem não tem para onde ir e o que falta "
               "(reforma, documentos, benefícios). Dados respeitam a LGPD.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "familias_retorno")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_editar = perfil["perfil"] in {"coordenador_municipal", "administrador", "saude_assistencia"}

    try:
        abrigos = (cliente.table("abrigos")
                   .select("id,nome")
                   .eq("municipio_id", municipio_id)
                   .order("nome")
                   .execute().data or [])
        abrigos_opcoes = {a["id"]: a["nome"] for a in abrigos}

        familias = (cliente.table("familias_abrigadas")
                    .select("id,abrigo_id,municipio_id,responsavel_nome,responsavel_cpf,"
                            "data_entrada,data_saida,data_retorno,endereco_retorno,"
                            "tem_para_onde_ir,motivo_sem_retorno,precisa_reforma,"
                            "precisa_documentos,precisa_beneficios,observacoes_retorno,"
                            "retorno_atualizado_em,situacao_imovel")
                    .eq("municipio_id", municipio_id)
                    .order("responsavel_nome")
                    .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar as famílias (aplique a migration 202610140021): {erro}")
        return

    # ---------- KPIs ----------
    ainda_abrigadas = [f for f in familias if f.get("data_saida") is None]
    retornaram = [f for f in familias if f.get("data_retorno") is not None]
    sem_para_onde = [f for f in familias if f.get("tem_para_onde_ir") is False]
    precisa_reforma = [f for f in familias if f.get("precisa_reforma")]
    precisa_documentos = [f for f in familias if f.get("precisa_documentos")]
    precisa_beneficios = [f for f in familias if f.get("precisa_beneficios")]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ainda abrigadas", len(ainda_abrigadas))
    c2.metric("Retornaram para casa", len(retornaram))
    c3.metric("Sem para onde ir", len(sem_para_onde))
    c4.metric("Precisa de reforma", len(precisa_reforma))
    c5.metric("Precisa de documentos/benefícios", len(precisa_documentos) + len(precisa_beneficios))

    # ---------- Cadastro / atualização de retorno ----------
    st.subheader("Atualizar retorno de família")

    if pode_editar and familias:
        familia_opcoes = {f["id"]: f"{f['responsavel_nome']} · {abrigos_opcoes.get(f.get('abrigo_id'), 'sem abrigo')}"
                          for f in familias}
        familia_id = st.selectbox("Família", list(familia_opcoes),
                                  format_func=lambda i: familia_opcoes[i],
                                  key="retorno-familia")
        existente = next((f for f in familias if f["id"] == familia_id), None)

        c1, c2 = st.columns(2)
        data_retorno = c1.date_input("Data de retorno (se já voltou)", value=None,
                                     format="DD/MM/YYYY", key="retorno-data")
        endereco_retorno = c2.text_input("Endereço atual (se voltou para casa)", max_chars=300,
                                         key="retorno-endereco")

        c1, c2, c3 = st.columns(3)
        tem_para_onde = c1.selectbox("Tem para onde ir?", ["—", "Sim", "Não"],
                                     key="retorno-tem-para-onde")
        precisa_reforma_c = c2.checkbox("Precisa de reforma", key="retorno-reforma")
        precisa_documentos_c = c3.checkbox("Precisa de documentos", key="retorno-documentos")

        c1, c2 = st.columns(2)
        precisa_beneficios_c = c1.checkbox("Precisa de benefícios", key="retorno-beneficios")
        motivo_sem_retorno = c2.text_input("Motivo sem retorno (se não tem para onde ir)",
                                           max_chars=500, key="retorno-motivo")
        observacoes_retorno = st.text_area("Observações", max_chars=1000, key="retorno-obs")

        if st.button("Salvar retorno", type="primary", key="retorno-salvar"):
            try:
                tp = None if tem_para_onde == "—" else (tem_para_onde == "Sim")
                cliente.rpc("cidc_familia_retorno_atualizar", {
                    "p_familia_id": familia_id,
                    "p_data_retorno": data_retorno.isoformat() if data_retorno else None,
                    "p_endereco_retorno": endereco_retorno.strip() or None,
                    "p_tem_para_onde_ir": tp,
                    "p_motivo_sem_retorno": motivo_sem_retorno.strip() or None,
                    "p_precisa_reforma": precisa_reforma_c,
                    "p_precisa_documentos": precisa_documentos_c,
                    "p_precisa_beneficios": precisa_beneficios_c,
                    "p_observacoes_retorno": observacoes_retorno.strip() or None,
                }).execute()
                st.success("Retorno da família atualizado com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar: {erro}")
    elif not pode_editar:
        st.info("Atualização de retorno está disponível para coordenação, administração e saúde/assistência.")
    elif not familias:
        st.info("Nenhuma família cadastrada neste município.")

    # ---------- Lista ----------
    st.subheader("Situação de retorno das famílias")
    if not familias:
        st.success("Nenhuma família cadastrada neste município ainda.")
    else:
        linhas_tabela = []
        for f in familias:
            abrigo_nome = abrigos_opcoes.get(f.get("abrigo_id"), "—")
            if f.get("data_retorno"):
                status = "Retornou"
            elif f.get("data_saida"):
                status = "Saiu do abrigo"
            elif f.get("tem_para_onde_ir") is False:
                status = "Sem para onde ir"
            else:
                status = "Ainda abrigada"
            linhas_tabela.append({
                "Família (responsável)": f["responsavel_nome"],
                "Abrigo": abrigo_nome,
                "Status": status,
                "Data retorno": _data_br(f.get("data_retorno")) if f.get("data_retorno") else "—",
                "Tem para onde ir": _sim_nao(f.get("tem_para_onde_ir")),
                "Reforma": "Sim" if f.get("precisa_reforma") else "Não",
                "Documentos": "Sim" if f.get("precisa_documentos") else "Não",
                "Benefícios": "Sim" if f.get("precisa_beneficios") else "Não",
                "Atualizado em": str(f.get("retorno_atualizado_em") or "")[:16].replace("T", " "),
            })
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Relatório ----------
    linhas_relatorio = []
    for f in familias:
        if f.get("data_retorno") or f.get("tem_para_onde_ir") is False or \
           f.get("precisa_reforma") or f.get("precisa_documentos") or f.get("precisa_beneficios"):
            linhas_relatorio.append({
                "Família": f["responsavel_nome"],
                "CPF (mascarado)": f"***{f['responsavel_cpf'][-2:]}" if f.get("responsavel_cpf") else "—",
                "Abrigo": abrigos_opcoes.get(f.get("abrigo_id"), "—"),
                "Data entrada": _data_br(f.get("data_entrada")),
                "Data retorno": _data_br(f.get("data_retorno")) or "—",
                "Tem para onde ir": "Sim" if f.get("tem_para_onde_ir") else ("Não" if f.get("tem_para_onde_ir") is False else "—"),
                "Motivo sem retorno": f.get("motivo_sem_retorno") or "—",
                "Precisa reforma": "Sim" if f.get("precisa_reforma") else "Não",
                "Precisa documentos": "Sim" if f.get("precisa_documentos") else "Não",
                "Precisa benefícios": "Sim" if f.get("precisa_beneficios") else "Não",
                "Observações": f.get("observacoes_retorno") or "—",
            })
    painel_relatorio(
        "Retorno das famílias",
        [("Situação de retorno", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Ainda abrigadas": len(ainda_abrigadas), "Retornaram": len(retornaram),
                "Sem para onde ir": len(sem_para_onde),
                "Precisa reforma": len(precisa_reforma),
                "Precisa documentos/benefícios": len(precisa_documentos) + len(precisa_beneficios)},
    )
