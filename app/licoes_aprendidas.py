"""Lições aprendidas (recuperação).

Relatório automático de um acionamento do plano: linha do tempo,
alertas, tarefas concluídas e atrasadas, ocorrências e ajuda entregue.
Sirve para alimentar a prevenção do ano seguinte, fechando o ciclo dos
5 eixos da Lei 12.608/2012.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Any

import streamlit as st

FUSO_MANHAS = timezone(timedelta(hours=-4))


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _hora_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]} {texto[11:16]}" if len(texto) >= 16 else _data_br(texto)


def _sim_nao(valor: Any) -> str:
    if valor is None:
        return "—"
    return "Sim" if valor else "Não"


def renderizar_licoes_aprendidas(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela, NIVEIS, AMEACAS, STATUS
    from app.relatorio_menu import painel_relatorio

    st.title("📋 Lições aprendidas")
    st.caption("Relatório automático de um acionamento do Plano de Contingência: "
               "linha do tempo, alertas, tarefas concluídas e atrasadas, ocorrências "
               "e ajuda entregue. Usado para alimentar a prevenção do ano seguinte.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "licoes_aprendidas")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    try:
        # Acionamentos do plano
        acionamentos = (cliente.table("plano_acionamentos")
                        .select("*")
                        .eq("municipio_id", municipio_id)
                        .order("acionado_em", desc=True)
                        .execute().data or [])

        # Tarefas do município
        tarefas = (cliente.table("acoes")
                   .select("*")
                   .eq("municipio_id", municipio_id)
                   .execute().data or [])

        # Alertas do município
        alertas = (cliente.table("alertas")
                   .select("id,classe,texto,status,criado_em,aprovado_por,emitido_em")
                   .eq("municipio_id", municipio_id)
                   .order("criado_em", desc=True)
                   .execute().data or [])

        # Ocorrências do município
        ocorrencias = (cliente.table("ocorrencias")
                       .select("id,numero,tipo,prioridade,status,titulo,aberta_em,resolvida_em,resultado")
                       .eq("municipio_id", municipio_id)
                       .order("aberta_em", desc=True)
                       .execute().data or [])

        # Ajuda entregue (últimos 30 dias ou do acionamento selecionado)
        desde = (date.today() - timedelta(days=90)).isoformat()
        ajuda = (cliente.table("ajuda_movimentos")
                 .select("item,quantidade,motivo,registrado_em,familia_id,comunidade_id,abrigo_id")
                 .eq("municipio_id", municipio_id)
                 .gte("registrado_em", desde)
                 .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar os dados (aplique as migrations necessárias): {erro}")
        return

    if not acionamentos:
        st.info("Nenhum acionamento do Plano de Contingência encontrado neste município. "
                "O relatório de lições aprendidas é gerado a partir de um acionamento.")
        return

    # ---------- Seleção do acionamento ----------
    st.subheader("Selecionar acionamento para o relatório")
    acao_opcoes = {}
    for a in acionamentos:
        label = (f"{NIVEIS.get(a['nivel'], a['nivel'])} · {AMEACAS.get(a['ameaca'], a['ameaca'])} · "
                 f"{_hora_br(a['acionado_em'])} · {a['tarefas_criadas']} tarefas")
        acao_opcoes[a["id"]] = label
    acionamento_id = st.selectbox("Acionamento", list(acao_opcoes),
                                  format_func=lambda i: acao_opcoes[i],
                                  key="licoes-acionamento")

    selecionado = next((a for a in acionamentos if a["id"] == acionamento_id), None)
    if not selecionado:
        return

    # ---------- Resumo do acionamento ----------
    st.subheader("Resumo do acionamento")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nível", NIVEIS.get(selecionado["nivel"], selecionado["nivel"]))
    c2.metric("Ameaça", AMEACAS.get(selecionado["ameaca"], selecionado["ameaca"]))
    c3.metric("Origem", "Alerta aprovado" if selecionado["origem"] == "alerta_aprovado" else "Manual")
    c4.metric("Tarefas criadas", selecionado["tarefas_criadas"])

    st.caption(f"Acionado em {_hora_br(selecionado['acionado_em'])} "
               f"{'· Encerrado em ' + _hora_br(selecionado.get('encerrado_em')) if selecionado.get('encerrado_em') else ''}")
    if selecionado.get("observacao"):
        st.info(f"Motivo: {selecionado['observacao']}")

    # ---------- Tarefas do acionamento ----------
    tarefas_acionamento = [t for t in tarefas if t.get("acionamento_id") == acionamento_id]
    tarefas_concluidas = [t for t in tarefas_acionamento if t["status"] == "concluida"]
    tarefas_atrasadas = [t for t in tarefas_acionamento if t["status"] in ("pendente", "em_andamento")]
    total_tarefas = len(tarefas_acionamento)
    pct_concluidas = (len(tarefas_concluidas) / total_tarefas * 100) if total_tarefas else 0

    st.subheader("Tarefas do acionamento")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", total_tarefas)
    c2.metric("Concluídas", len(tarefas_concluidas), f"{pct_concluidas:.0f}%")
    c3.metric("Pendentes/atrasadas", len(tarefas_atrasadas))

    if tarefas_atrasadas:
        st.warning(f"⚠️ {len(tarefas_atrasadas)} tarefa(s) ainda não foram concluídas.")
        with st.expander("Ver tarefas pendentes"):
            for t in tarefas_atrasadas:
                st.write(f"• {t['descricao']} (prazo: {_data_br(t.get('prazo'))})")

    # ---------- Linha do tempo ----------
    st.subheader("Linha do tempo")
    eventos = []
    if selecionado.get("acionado_em"):
        eventos.append({
            "quando": selecionado["acionado_em"],
            "o_que": "Plano acionado",
            "detalhe": f"Nível {selecionado['nivel']} · {selecionado['ameaca']}",
        })
    for a in alertas:
        if a.get("status") == "aprovado":
            eventos.append({
                "quando": a.get("criado_em"),
                "o_que": "Alerta aprovado",
                "detalhe": f"{a.get('classe')} · {a.get('texto', '')[:100]}",
            })
    for o in ocorrencias:
        if o.get("aberta_em"):
            eventos.append({
                "quando": o.get("aberta_em"),
                "o_que": "Ocorrência aberta",
                "detalhe": f"#{o['numero']} · {o.get('titulo', '')[:80]}",
            })
    for t in tarefas_concluidas:
        if t.get("concluida_em"):
            eventos.append({
                "quando": t.get("concluida_em"),
                "o_que": "Tarefa concluída",
                "detalhe": t.get("descricao", "")[:100],
            })
    eventos.sort(key=lambda e: e["quando"] or "", reverse=True)

    for ev in eventos[:20]:
        st.write(f"• {_hora_br(ev['quando'])} — **{ev['o_que']}**: {ev['detalhe']}")

    # ---------- Ocorrências ----------
    st.subheader("Ocorrências atendidas")
    if ocorrencias:
        linhas_ocorrencias = [
            {
                "Nº": o["numero"],
                "Título": o.get("titulo", ""),
                "Tipo": o.get("tipo", ""),
                "Prioridade": o.get("prioridade", ""),
                "Status": STATUS.get(o["status"], o["status"]),
                "Aberta em": _data_br(o.get("aberta_em")),
                "Resolvida em": _data_br(o.get("resolvida_em")) or "—",
            }
            for o in ocorrencias
        ]
        st.dataframe(linhas_ocorrencias, hide_index=True, width="stretch")
    else:
        st.info("Nenhuma ocorrência registrada neste município.")

    # ---------- Ajuda entregue ----------
    st.subheader("Ajuda entregra (últimos 90 dias)")
    entregas = [a for a in ajuda if a.get("motivo", "").startswith("entrega")]
    if entregas:
        total_itens = len(entregas)
        total_quantidade = sum(abs(float(a.get("quantidade") or 0)) for a in entregas)
        c1, c2 = st.columns(2)
        c1.metric("Entregas registradas", total_itens)
        c2.metric("Itens entregues", f"{total_quantidade:g}")
        st.caption("Período: últimos 90 dias.")
    else:
        st.info("Nenhuma entrega de ajuda registrada nos últimos 90 dias.")

    # ---------- Relatório PDF ----------
    st.subheader("Gerar relatório de lições aprendidas")
    st.info("Este relatório consolida os dados do acionamento para apoiar a prevenção do ano seguinte.")

    linhas_relatorio = [
        {
            "Acionamento": _hora_br(selecionado["acionado_em"]),
            "Nível": NIVEIS.get(selecionado["nivel"], selecionado["nivel"]),
            "Ameaça": AMEACAS.get(selecionado["ameaca"], selecionado["ameaca"]),
            "Origem": "Alerta aprovado" if selecionado["origem"] == "alerta_aprovado" else "Manual",
            "Tarefas criadas": selecionado["tarefas_criadas"],
            "Tarefas concluídas": len(tarefas_concluidas),
            "Tarefas pendentes": len(tarefas_atrasadas),
            "Ocorrências": len(ocorrencias),
            "Entregas (90 dias)": len(entregas),
        }
    ]
    painel_relatorio(
        "Lições aprendidas — acionamento do plano",
        [("Resumo do acionamento", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Nível": selecionado["nivel"],
                "Tarefas concluídas": f"{len(tarefas_concluidas)}/{total_tarefas}",
                "Ocorrências": len(ocorrencias),
                "Entregas (90 dias)": len(entregas)},
    )
