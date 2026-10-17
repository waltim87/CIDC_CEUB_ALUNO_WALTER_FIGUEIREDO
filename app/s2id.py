"""Ficha para o S2iD (resposta).

Rascunho em PDF com afetados, desalojados, desabrigados, óbitos informados,
danos a casas e instalações e ajuda entregue, montado com os dados do app.
Deixa claro que é rascunho para lançar no S2iD oficial.

Dados vêm de pessoas_afetadas (comunidade × data) e ajuda_movimentos.
Somente quem pode registrar afetados do município pode editar.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Any

import streamlit as st

FUSO_MANHAS = timezone(timedelta(hours=-4))


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _numero(valor: Any) -> str:
    if valor is None:
        return "—"
    numero = float(valor)
    return f"{numero:,.0f}".replace(",", ".") if numero.is_integer() else f"{numero:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def renderizar_s2id(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("📄 Ficha S2iD (rascunho)")
    st.caption("Rascunho da ficha oficial do S2iD (sistema federal) com afetados, "
               "desalojados, desabrigados, óbitos informados, danos a casas e "
               "instalações e ajuda entregue. **É rascunho:** preencha e revise "
               "antes de lançar no S2iD oficial.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "s2id")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_editar = perfil["perfil"] in {"coordenador_municipal", "administrador", "agente_campo"}

    try:
        comunidades = (cliente.table("comunidades")
                       .select("id,nome")
                       .eq("municipio_id", municipio_id)
                       .order("nome")
                       .execute().data or [])
        fichas = (cliente.table("pessoas_afetadas")
                  .select("id,comunidade_id,data,familias,pessoas,desalojados,desabrigados,"
                          "obitos,danos_casas,danos_instalacoes,necessidades,fonte_afetados,"
                          "observacoes,criado_em,atualizado_em")
                  .execute().data or [])
        # Filtra só as deste município (via comunidade_id)
        ids_comunidade = {c["id"]: c["nome"] for c in comunidades}
        fichas_municipio = [f for f in fichas if str(f.get("comunidade_id")) in ids_comunidade]
    except Exception as erro:
        st.error(f"Não foi possível carregar as fichas (aplique a migration 202610140020): {erro}")
        return

    # ---------- KPIs ----------
    total_familias = sum(f.get("familias") or 0 for f in fichas_municipio)
    total_pessoas = sum(f.get("pessoas") or 0 for f in fichas_municipio)
    total_desalojados = sum(f.get("desalojados") or 0 for f in fichas_municipio)
    total_desabrigados = sum(f.get("desabrigados") or 0 for f in fichas_municipio)
    total_obitos = sum(f.get("obitos") or 0 for f in fichas_municipio)
    total_com_danos = sum(1 for f in fichas_municipio if f.get("danos_casas") or f.get("danos_instalacoes"))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Fichas cadastradas", len(fichas_municipio))
    c2.metric("Famílias", _numero(total_familias))
    c3.metric("Pessoas", _numero(total_pessoas))
    c4.metric("Desalojados / Desabrigados", f"{_numero(total_desalojados)} / {_numero(total_desabrigados)}")
    c5.metric("Óbitos informados", _numero(total_obitos))

    # ---------- Cadastro / edição de ficha ----------
    st.subheader("Cadastrar ou atualizar ficha de afetados")

    if pode_editar and comunidades:
        comunidade_opcoes = {c["id"]: c["nome"] for c in comunidades}
        comunidade_id = st.selectbox("Comunidade", list(comunidade_opcoes),
                                     format_func=lambda i: comunidade_opcoes[i],
                                     key="s2id-comunidade")
        data_ficha = st.date_input("Data de referência", value=date.today(), format="DD/MM/YYYY",
                                   key="s2id-data")

        # Busca ficha existente para esta comunidade e data
        existente = next((f for f in fichas_municipio
                          if str(f["comunidade_id"]) == comunidade_id
                          and str(f["data"]).startswith(data_ficha.isoformat())), None)

        with st.form("form_ficha_s2id", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            familias = c1.number_input("Famílias afetadas", min_value=0, step=1,
                                       value=int(existente.get("familias") or 0) if existente else 0)
            pessoas = c2.number_input("Pessoas afetadas", min_value=0, step=1,
                                      value=int(existente.get("pessoas") or 0) if existente else 0)
            desalojados = c3.number_input("Desalojados", min_value=0, step=1,
                                          value=int(existente.get("desalojados") or 0) if existente else 0)

            c1, c2, c3 = st.columns(3)
            desabrigados = c1.number_input("Desabrigados", min_value=0, step=1,
                                           value=int(existente.get("desabrigados") or 0) if existente else 0)
            obitos = c2.number_input("Óbitos informados", min_value=0, step=1,
                                     value=int(existente.get("obitos") or 0) if existente else 0)
            danos_casas = c3.number_input("Casas com danos", min_value=0, step=1,
                                          value=int(existente.get("danos_casas") or 0) if existente else 0)

            danos_instalacoes = st.text_input("Danos a instalações (escolas, pontes, unidades de saúde, etc.)",
                                              max_chars=500,
                                              value=existente.get("danos_instalacoes") or "" if existente else "")
            fonte_afetados = st.text_input("Fonte dos dados", max_chars=200,
                                           placeholder="Ex.: Defesa Civil Municipal, ACS, liderança comunitária",
                                           value=existente.get("fonte_afetados") or "" if existente else "")
            necessidades = st.text_input("Necessidades principais (separadas por vírgula)",
                                         max_chars=300,
                                         placeholder="Ex.: água, cestas básicas, lona, medicamentos",
                                         value=", ".join(existente.get("necessidades") or []) if existente else "")
            observacoes = st.text_area("Observações", max_chars=1000,
                                       value=existente.get("observacoes") or "" if existente else "")

            if st.form_submit_button("Salvar ficha S2iD", type="primary"):
                try:
                    nec_list = [n.strip() for n in necessidades.split(",") if n.strip()] or None
                    cliente.rpc("cidc_pessoas_afetadas_cadastrar", {
                        "p_comunidade_id": comunidade_id,
                        "p_data": data_ficha.isoformat(),
                        "p_familias": int(familias) or None,
                        "p_pessoas": int(pessoas) or None,
                        "p_desalojados": int(desalojados) or None,
                        "p_desabrigados": int(desabrigados) or None,
                        "p_obitos": int(obitos) or None,
                        "p_danos_casas": int(danos_casas) or None,
                        "p_danos_instalacoes": danos_instalacoes.strip() or None,
                        "p_necessidades": nec_list,
                        "p_fonte_afetados": fonte_afetados.strip() or None,
                        "p_observacoes": observacoes.strip() or None,
                    }).execute()
                    st.success("Ficha S2iD salva com sucesso.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível salvar: {erro}")
    elif not pode_editar:
        st.info("Cadastro e edição de fichas S2iD estão disponíveis para coordenação, administração e agente de campo.")
    elif not comunidades:
        st.info("Nenhuma comunidade cadastrada neste município.")

    # ---------- Lista de fichas ----------
    st.subheader("Fichas cadastradas")
    if not fichas_municipio:
        st.success("Nenhuma ficha S2iD cadastrada neste município ainda.")
    else:
        linhas_tabela = [
            {
                "Comunidade": ids_comunidade.get(str(f.get("comunidade_id")), "—"),
                "Data": _data_br(f.get("data")),
                "Famílias": f.get("familias") or 0,
                "Pessoas": f.get("pessoas") or 0,
                "Desalojados": f.get("desalojados") or 0,
                "Desabrigados": f.get("desabrigados") or 0,
                "Óbitos": f.get("obitos") or 0,
                "Danos casas": f.get("danos_casas") or 0,
                "Fonte": f.get("fonte_afetados") or "—",
                "Atualizado em": str(f.get("atualizado_em") or "")[:16].replace("T", " "),
            }
            for f in sorted(fichas_municipio, key=lambda x: str(x.get("data") or ""), reverse=True)
        ]
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Relatório PDF (rascunho S2iD) ----------
    st.subheader("Gerar rascunho PDF para o S2iD")
    st.warning("⚠️ Este PDF é um **rascunho**. Revise os dados antes de lançar no S2iD oficial.", icon="⚠️")

    if fichas_municipio:
        linhas_pdf = []
        total_geral = {"familias": 0, "pessoas": 0, "desalojados": 0, "desabrigados": 0,
                       "obitos": 0, "danos_casas": 0}
        for f in sorted(fichas_municipio, key=lambda x: (str(x.get("comunidade_id")), str(x.get("data") or ""))):
            linhas_pdf.append({
                "Comunidade": ids_comunidade.get(str(f.get("comunidade_id")), "—"),
                "Data": _data_br(f.get("data")),
                "Famílias": f.get("familias") or 0,
                "Pessoas": f.get("pessoas") or 0,
                "Desalojados": f.get("desalojados") or 0,
                "Desabrigados": f.get("desabrigados") or 0,
                "Óbitos": f.get("obitos") or 0,
                "Danos casas": f.get("danos_casas") or 0,
                "Danos instalações": f.get("danos_instalacoes") or "—",
                "Fonte": f.get("fonte_afetados") or "—",
                "Observações": f.get("observacoes") or "—",
            })
            total_geral["familias"] += f.get("familias") or 0
            total_geral["pessoas"] += f.get("pessoas") or 0
            total_geral["desalojados"] += f.get("desalojados") or 0
            total_geral["desabrigados"] += f.get("desabrigados") or 0
            total_geral["obitos"] += f.get("obitos") or 0
            total_geral["danos_casas"] += f.get("danos_casas") or 0

        resumo = {
            "Município": nome_municipio,
            "Total famílias": total_geral["familias"],
            "Total pessoas": total_geral["pessoas"],
            "Total desalojados": total_geral["desalojados"],
            "Total desabrigados": total_geral["desabrigados"],
            "Total óbitos": total_geral["obitos"],
            "Com danos a casas": total_geral["danos_casas"],
        }

        # Tenta incluir ajuda entregue (últimos 30 dias)
        try:
            desde = (date.today() - timedelta(days=30)).isoformat()
            ajuda = (cliente.table("ajuda_movimentos")
                     .select("item,quantidade,motivo,registrado_em")
                     .eq("municipio_id", municipio_id)
                     .gte("registrado_em", desde)
                     .execute().data or [])
            entregas = [a for a in ajuda if a.get("motivo", "").startswith("entrega")]
            total_cestas = sum(abs(float(a.get("quantidade") or 0)) for a in entregas
                               if a.get("item") == "cesta_basica")
            resumo["Cestas entregas (30 dias)"] = _numero(total_cestas)
        except Exception:
            pass

        painel_relatorio(
            "Ficha S2iD — rascunho",
            [("Fichas por comunidade", linhas_pdf)],
            subtitulo=nome_municipio,
            resumo=resumo,
        )
    else:
        st.info("Cadastre pelo menos uma ficha para gerar o rascunho PDF.")
