"""Checklist de abrigo pronto (preparação).

Vistoria periódica dos abrigos: água, energia, banheiros, cozinha,
acessibilidade, kits e colchões. Gera selo "pronto" e avisa quando
a vistoria tem mais de 90 dias.

Somente coordenação, administração ou coordenador do abrigo podem
registrar vistorias. A leitura segue o município do usuário (RLS).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

ITENS_CHECKLIST = [
    ("agua", "💧 Água potável"),
    ("energia", "⚡ Energia elétrica"),
    ("banheiros", "🚿 Banheiros funcionando"),
    ("cozinha", "🍳 Cozinha equipada"),
    ("acessibilidade", "♿ Acessibilidade"),
    ("kits", "📦 Kits de emergência"),
    ("colchoes", "🛏️ Colchões disponíveis"),
]
PERFIS_TELA = {
    "coordenador_municipal", "administrador", "gestor_nacional",
    "gestor_estadual", "operador_monitoramento", "voluntario",
    "agente_campo", "saude_assistencia", "logistica_abastecimento",
    "pesquisador",
}


def _numero(valor: Any) -> str:
    if valor is None:
        return "—"
    numero = float(valor)
    return f"{numero:,.0f}".replace(",", ".") if numero.is_integer() else f"{numero:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _hora_local(valor: str | None) -> str:
    """UTC ISO -> 'dd/mm HH:MM (Manaus)'; Manaus = UTC-4."""
    if not valor:
        return "—"
    from datetime import datetime, timezone
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m %H:%M") + " (Manaus)"


def _dias_atras(valor: date | str | None) -> int | None:
    if not valor:
        return None
    if isinstance(valor, str):
        valor = date.fromisoformat(valor[:10])
    return (date.today() - valor).days


def renderizar_abrigo_vistoria(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("🏘️ Checklist de abrigo pronto")
    st.caption("Vistoria periódica dos abrigos: água, energia, banheiros, cozinha, "
               "acessibilidade, kits e colchões. O selo \"pronto\" aparece quando "
               "todos os itens estão em ordem. Aviso quando a vistoria tem mais de 90 dias.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "abrigo_vistoria")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_vistoriar = perfil["perfil"] in {"coordenador_municipal", "administrador"}

    try:
        abrigos = (cliente.table("abrigos")
                   .select("id,nome,capacidade,ocupacao")
                   .eq("municipio_id", municipio_id)
                   .order("nome")
                   .execute().data or [])
        vistorias = (cliente.table("abrigo_vistorias")
                     .select("id,abrigo_id,vistoriado_por,data_vistoria,agua,energia,banheiros,"
                             "cozinha,acessibilidade,kits,colchoes,selo_pronto,observacoes,criado_em")
                     .eq("municipio_id", municipio_id)
                     .order("data_vistoria", desc=True)
                     .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar os abrigos e vistorias (aplique a migration 202610140018): {erro}")
        return

    # Última vistoria por abrigo.
    ultima_por_abrigo: dict[str, dict[str, Any]] = {}
    for v in vistorias:
        aid = str(v["abrigo_id"])
        if aid not in ultima_por_abrigo or v["data_vistoria"] > ultima_por_abrigo[aid]["data_vistoria"]:
            ultima_por_abrigo[aid] = v

    # ---------- KPIs ----------
    total_abrigos = len(abrigos)
    vistorias_count = len(ultima_por_abrigo)
    prontos = sum(1 for v in ultima_por_abrigo.values() if v.get("selo_pronto"))
    vencidas = sum(1 for v in ultima_por_abrigo.values()
                   if _dias_atras(v.get("data_vistoria")) is not None
                   and _dias_atras(v.get("data_vistoria")) > 90)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Abrigos cadastrados", total_abrigos)
    c2.metric("Com vistoria", vistorias_count)
    c3.metric("Selo \"pronto\"", prontos)
    c4.metric("Vistoria vencida (>90 dias)", vencidas)

    # ---------- Cadastro / edição de vistoria ----------
    st.subheader("Registrar vistoria de abrigo")

    if pode_vistoriar and abrigos:
        abrigo_opcoes = {a["id"]: a["nome"] for a in abrigos}
        abrigo_id = st.selectbox("Abrigo", list(abrigo_opcoes),
                                 format_func=lambda i: abrigo_opcoes[i],
                                 key="vistoria-abrigo")
        ultima = ultima_por_abrigo.get(abrigo_id)
        if ultima:
            st.caption(f"Última vistoria: {ultima['data_vistoria']} · "
                       f"{'Selo pronto ✅' if ultima.get('selo_pronto') else 'Sem selo'}")

        with st.form("form_vistoria_abrigo", clear_on_submit=True):
            valores = {}
            colunas = st.columns(4)
            for posicao, (chave, rotulo) in enumerate(ITENS_CHECKLIST):
                padrao = bool(ultima.get(chave)) if ultima else False
                valores[chave] = colunas[posicao % 4].checkbox(rotulo, value=padrao,
                                                               key=f"vist-{chave}")
            observacao = st.text_input("Observações (opcional)", max_chars=1000,
                                       key="vist-obs")
            if st.form_submit_button("Salvar vistoria", type="primary"):
                try:
                    cliente.rpc("cidc_abrigo_vistoria_registrar", {
                        "p_abrigo_id": abrigo_id,
                        "p_agua": valores["agua"],
                        "p_energia": valores["energia"],
                        "p_banheiros": valores["banheiros"],
                        "p_cozinha": valores["cozinha"],
                        "p_acessibilidade": valores["acessibilidade"],
                        "p_kits": valores["kits"],
                        "p_colchoes": valores["colchoes"],
                        "p_observacao": observacao.strip() or None,
                    }).execute()
                    st.success("Vistoria registrada com sucesso.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível salvar a vistoria: {erro}")
    elif not pode_vistoriar:
        st.info("Registro de vistorias está disponível para a coordenação municipal e a administração.")
    elif not abrigos:
        st.info("Nenhum abrigo cadastrado neste município.")

    # ---------- Lista de abrigos com status ----------
    st.subheader("Situação dos abrigos")
    if not abrigos:
        st.success("Nenhum abrigo cadastrado neste município ainda.")
    else:
        linhas_tabela = []
        for a in abrigos:
            v = ultima_por_abrigo.get(a["id"])
            dias = _dias_atras(v.get("data_vistoria")) if v else None
            vencida = dias is not None and dias > 90
            selo = v.get("selo_pronto") if v else False
            itens_ok = sum(1 for chave, _ in ITENS_CHECKLIST if v and v.get(chave)) if v else 0
            total_itens = len(ITENS_CHECKLIST)
            linhas_tabela.append({
                "Abrigo": a["nome"],
                "Capacidade": _numero(a.get("capacidade")),
                "Ocupação": _numero(a.get("ocupacao")),
                "Última vistoria": v.get("data_vistoria") if v else "—",
                "Dias atrás": dias if dias is not None else "—",
                "Selo pronto": "✅ Sim" if selo else "❌ Não",
                "Vencida (>90d)": "⚠️ Sim" if vencida else "Não",
                "Itens OK": f"{itens_ok}/{total_itens}" if v else "0/7",
            })
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")
        st.caption("Vistoria vencida = mais de 90 dias sem vistoria ou com data antiga.")

    # ---------- Relatório ----------
    linhas_relatorio = []
    for a in abrigos:
        v = ultima_por_abrigo.get(a["id"])
        dias = _dias_atras(v.get("data_vistoria")) if v else None
        vencida = dias is not None and dias > 90
        itens_ok = sum(1 for chave, _ in ITENS_CHECKLIST if v and v.get(chave)) if v else 0
        linhas_relatorio.append({
            "Abrigo": a["nome"],
            "Capacidade": a.get("capacidade"),
            "Ocupação": a.get("ocupacao"),
            "Última vistoria": v.get("data_vistoria") if v else "—",
            "Selo pronto": bool(v.get("selo_pronto")) if v else False,
            "Vencida (>90 dias)": vencida,
            "Itens OK": itens_ok,
            "Total itens": len(ITENS_CHECKLIST),
        })
    painel_relatorio(
        "Checklist de abrigo pronto",
        [("Situação dos abrigos", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Abrigos cadastrados": total_abrigos, "Com vistoria": vistorias_count,
                "Selo pronto": prontos, "Vistoria vencida (>90 dias)": vencidas},
    )
