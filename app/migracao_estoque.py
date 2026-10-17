"""Migração do estoque antigo (resposta/logística).

Migra os dados da tabela antiga ``recursos`` (aba "Pré-posicionamento")
para o novo estoque ``ajuda_movimentos`` / ``ajuda_saldo``, como entrada
do tipo "ajuste" com observação, sem perder os dados antigos.

Somente logística ou coordenação do município podem executar a migração.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Any

import streamlit as st

FUSO_MANHAS = timezone(timedelta(hours=-4))


def _numero(valor: Any) -> str:
    if valor is None:
        return "—"
    numero = float(valor)
    return f"{numero:,.0f}".replace(",", ".") if numero.is_integer() else f"{numero:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def renderizar_migracao_estoque(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("🔄 Migração do estoque antigo")
    st.caption("Migra os recursos da tabela antiga ``recursos`` (pré-posicionamento) "
               "para o novo estoque ``ajuda_movimentos``, como entrada do tipo "
               "\"ajuste\" com observação. Os dados antigos são preservados.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "migracao_estoque")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_migrar = perfil["perfil"] in {"coordenador_municipal", "administrador", "logistica_abastecimento"}

    try:
        recursos = (cliente.table("recursos")
                    .select("id,tipo,quantidade,unidade,local_armazenamento,validade,responsavel,observacoes,atualizado_em")
                    .eq("municipio_id", municipio_id)
                    .order("tipo")
                    .execute().data or [])
        movimentos_ja_migrados = (cliente.table("ajuda_movimentos")
                                  .select("item,quantidade,motivo,observacao,registrado_em")
                                  .eq("municipio_id", municipio_id)
                                  .eq("motivo", "ajuste")
                                  .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar os dados (aplique as migrations necessárias): {erro}")
        return

    # Mapeamento de tipos antigos para itens novos
    MAPEAMENTO_TIPOS = {
        "agua": "agua_potavel",
        "alimento": "cesta_basica",
        "medicamento": "kit_higiene",
        "oxigenio": "outro",
        "combustivel": "combustivel",
        "purificador": "filtro_agua",
    }

    # Identificar quais recursos ainda não foram migrados
    itens_ja_migrados = set()
    for m in movimentos_ja_migrados:
        obs = m.get("observacao") or ""
        if "migracao_recursos" in obs:
            itens_ja_migrados.add(m["item"])

    recursos_pendentes = [r for r in recursos if MAPEAMENTO_TIPOS.get(r["tipo"], r["tipo"]) not in itens_ja_migrados]

    # ---------- KPIs ----------
    c1, c2, c3 = st.columns(3)
    c1.metric("Recursos antigos", len(recursos))
    c2.metric("Já migrados", len(itens_ja_migrados))
    c3.metric("Pendentes de migração", len(recursos_pendentes))

    if not recursos:
        st.success("Nenhum recurso antigo cadastrado neste município.")
        return

    # ---------- Lista de recursos ----------
    st.subheader("Recursos antigos (tabela recursos)")
    linhas_recursos = []
    for r in recursos:
        item_novo = MAPEAMENTO_TIPOS.get(r["tipo"], r["tipo"])
        ja_migrado = item_novo in itens_ja_migrados
        status = "✅ Migrado" if ja_migrado else "⏳ Pendente"
        linhas_recursos.append({
            "Tipo": r["tipo"],
            "Item novo": item_novo,
            "Quantidade": _numero(r["quantidade"]),
            "Unidade": r.get("unidade") or "",
            "Local": r.get("local_armazenamento") or "—",
            "Validade": _data_br(r.get("validade")),
            "Responsável": r.get("responsavel") or "—",
            "Status": status,
        })
    st.dataframe(linhas_recursos, hide_index=True, width="stretch")

    # ---------- Execução da migração ----------
    st.subheader("Executar migração")

    if not pode_migrar:
        st.info("Migração de estoque está disponível para coordenação, administração e logística.")
        return

    if not recursos_pendentes:
        st.success("Todos os recursos já foram migrados para o novo estoque.")
        return

    st.write("Os recursos pendentes serão migrados como entrada do tipo **ajuste** "
             "na tabela ``ajuda_movimentos``, com observação indicando a origem "
             "da tabela antiga ``recursos``.")

    itens_para_migrar = st.multiselect(
        "Selecionar itens para migrar",
        options=[r["tipo"] for r in recursos_pendentes],
        default=[r["tipo"] for r in recursos_pendentes],
        key="migracao-itens",
        help="Cada item será inserido como uma entrada (quantidade positiva) "
             "com motivo 'ajuste' no novo estoque.",
    )

    observacao_geral = st.text_input(
        "Observação (opcional)",
        value="Migração da tabela antiga recursos para ajuda_movimentos",
        max_chars=500,
        key="migracao-obs",
    )

    if st.button("Migrar itens selecionados", type="primary", key="migracao-executar"):
        executados = 0
        erros = 0
        for r in recursos_pendentes:
            if r["tipo"] not in itens_para_migrar:
                continue
            item_novo = MAPEAMENTO_TIPOS.get(r["tipo"], r["tipo"])
            try:
                cliente.rpc("cidc_estoque_movimentar", {
                    "p_municipio_id": municipio_id,
                    "p_item": item_novo,
                    "p_quantidade": float(r["quantidade"]),
                    "p_motivo": "ajuste",
                    "p_origem_destino": None,
                    "p_observacao": (observacao_geral or "") + f" | origem: recursos.id={r['id']} | tipo_antigo={r['tipo']} | unidade_antiga={r.get('unidade') or ''} | validade={r.get('validade') or ''}",
                }).execute()
                executados += 1
            except Exception as erro:
                st.error(f"Erro ao migrar {r['tipo']}: {erro}")
                erros += 1

        if executados:
            st.success(f"{executados} item(ns) migrado(s) com sucesso para o novo estoque.")
        if erros:
            st.error(f"{erros} item(ns) com erro na migração.")
        st.rerun()

    # ---------- Relatório ----------
    st.subheader("Relatório de migração")
    linhas_relatorio = []
    for r in recursos:
        item_novo = MAPEAMENTO_TIPOS.get(r["tipo"], r["tipo"])
        ja_migrado = item_novo in itens_ja_migrados
        linhas_relatorio.append({
            "Tipo antigo": r["tipo"],
            "Item novo": item_novo,
            "Quantidade": r["quantidade"],
            "Unidade": r.get("unidade") or "",
            "Local armazenamento": r.get("local_armazenamento") or "",
            "Validade": _data_br(r.get("validade")),
            "Responsável": r.get("responsavel") or "",
            "Observações antigas": r.get("observacoes") or "",
            "Migrado": "Sim" if ja_migrado else "Não",
        })
    painel_relatorio(
        "Migração de estoque antigo",
        [("Recursos e migração", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Recursos antigos": len(recursos),
                "Já migrados": len(itens_ja_migrados),
                "Pendentes": len(recursos_pendentes)},
    )
