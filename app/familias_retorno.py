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
    if st.session_state.get("_aviso_retorno"):
        st.success(st.session_state.pop("_aviso_retorno"))

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

    from app.familias import usuario_coordena_abrigo

    # Mesmo critério do banco: coordenação, saúde/assistência, administração e o coordenador do
    # abrigo (que só vê as famílias do seu abrigo).
    pode_editar = perfil["perfil"] in {"coordenador_municipal", "administrador", "saude_assistencia"} or         usuario_coordena_abrigo(cliente, perfil["id"])

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
    # Quem já voltou para casa não conta como abrigada (mesmo em registro antigo sem data de saída).
    ainda_abrigadas = [f for f in familias if f.get("data_saida") is None and f.get("data_retorno") is None]
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
    # Família que precisa dos dois conta uma vez só.
    c5.metric("Precisa de documentos/benefícios", len({f["id"] for f in precisa_documentos + precisa_beneficios}))

    # ---------- Cadastro / atualização de retorno ----------
    st.subheader("Atualizar retorno de família")

    if pode_editar and familias:
        familia_opcoes = {f["id"]: f"{f['responsavel_nome']} · {abrigos_opcoes.get(f.get('abrigo_id'), 'sem abrigo')}"
                          for f in familias}
        familia_id = st.selectbox("Família", list(familia_opcoes),
                                  format_func=lambda i: familia_opcoes[i],
                                  key="retorno-familia")
        existente = next((f for f in familias if f["id"] == familia_id), None) or {}
        # Campos vêm com o que já foi registrado e o nome interno muda com a família escolhida:
        # antes vinham em branco e salvar apagava as marcações anteriores.
        sufixo = familia_id
        anterior_retorno = existente.get("data_retorno")

        c1, c2 = st.columns(2)
        data_retorno = c1.date_input("Data de retorno (se já voltou)",
                                     value=date.fromisoformat(str(anterior_retorno)[:10]) if anterior_retorno else None,
                                     format="DD/MM/YYYY", key=f"retorno-data-{sufixo}")
        endereco_retorno = c2.text_input("Endereço atual (se voltou para casa)", max_chars=300,
                                         value=existente.get("endereco_retorno") or "",
                                         key=f"retorno-endereco-{sufixo}")

        opcoes_destino = ["—", "Sim", "Não"]
        destino_atual = {True: "Sim", False: "Não"}.get(existente.get("tem_para_onde_ir"), "—")
        c1, c2, c3 = st.columns(3)
        tem_para_onde = c1.selectbox("Tem para onde ir?", opcoes_destino, index=opcoes_destino.index(destino_atual),
                                     key=f"retorno-tem-para-onde-{sufixo}")
        precisa_reforma_c = c2.checkbox("Precisa de reforma", value=bool(existente.get("precisa_reforma")),
                                        key=f"retorno-reforma-{sufixo}")
        precisa_documentos_c = c3.checkbox("Precisa de documentos", value=bool(existente.get("precisa_documentos")),
                                           key=f"retorno-documentos-{sufixo}")

        c1, c2 = st.columns(2)
        precisa_beneficios_c = c1.checkbox("Precisa de benefícios", value=bool(existente.get("precisa_beneficios")),
                                           key=f"retorno-beneficios-{sufixo}")
        motivo_sem_retorno = c2.text_input("Motivo sem retorno (se não tem para onde ir)",
                                           max_chars=500, value=existente.get("motivo_sem_retorno") or "",
                                           key=f"retorno-motivo-{sufixo}")
        observacoes_retorno = st.text_area("Observações", max_chars=1000,
                                           value=existente.get("observacoes_retorno") or "",
                                           key=f"retorno-obs-{sufixo}")
        if data_retorno:
            st.caption("Ao salvar com data de retorno, a família sai da contagem de abrigadas.")

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
            except Exception as erro:
                st.error(f"Não foi possível salvar: {getattr(erro, 'message', None) or erro}")
            else:
                st.session_state["_aviso_retorno"] = "Retorno da família atualizado."
                st.rerun()
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
