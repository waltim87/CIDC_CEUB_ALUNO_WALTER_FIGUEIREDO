"""Embarcações e equipes (resposta).

Cadastro de barcos (capacidade, piloto, combustível) e vínculo com as ocorrências.
Somente coordenação, administração e logística podem cadastrar/editar/excluir.
A leitura segue o município do usuário (RLS no banco).
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

import streamlit as st

TIPOS = {
    "lancha": ("🚤 Lancha"),
    "balsa": ("🚢 Balsa"),
    "canoa_motorizada": ("🛶 Canoa motorizada"),
    "jet_ski": ("⚡ Jet ski"),
    "outro": ("❓ Outro"),
}
STATUS = {
    "disponível": ("🟢 Disponível"),
    "em_uso": ("🟠 Em uso"),
    "manutencao": ("🔴 Manutenção"),
    "fora_de_servico": ("⚫ Fora de serviço"),
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


def renderizar_embarcacoes(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("⛵ Embarcações e equipes")
    st.caption("Cadastro de barcos (capacidade, piloto, combustível) e vínculo com as "
               "ocorrências. Somente coordenação, administração e logística podem "
               "cadastrar ou editar embarcações.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "embarcacoes")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    pode_gerenciar = perfil["perfil"] in {"coordenador_municipal", "administrador", "logistica_abastecimento"}

    try:
        embarcacoes = (cliente.table("embarcacoes")
                       .select("id,nome,tipo,capacidade,piloto,telefone_piloto,combustivel,"
                               "quantidade_combustivel,status,observacoes,registrado_em,atualizado_em")
                       .eq("municipio_id", municipio_id)
                       .order("nome")
                       .execute().data or [])
        ocorrencias_ativas = (cliente.table("ocorrencias")
                              .select("id,numero,titulo,status,embarcacao_id")
                              .eq("municipio_id", municipio_id)
                              .in_("status", ["aberta", "atribuida", "em_deslocamento", "em_atendimento"])
                              .order("numero")
                              .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar as embarcações (aplique a migration 202610140022): {erro}")
        return

    # ---------- KPIs ----------
    total = len(embarcacoes)
    disponiveis = sum(1 for e in embarcacoes if e.get("status") == "disponível")
    em_uso = sum(1 for e in embarcacoes if e.get("status") == "em_uso")
    manutencao = sum(1 for e in embarcacoes if e.get("status") == "manutencao")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Embarcações", total)
    c2.metric("Disponíveis", disponiveis)
    c3.metric("Em uso", em_uso)
    c4.metric("Manutenção", manutencao)

    # ---------- Cadastro / edição ----------
    st.subheader("Cadastrar ou editar embarcação")

    if pode_gerenciar:
        embarcacao_opcoes = {e["id"]: e["nome"] for e in embarcacoes}
        embarcacao_id = st.selectbox(
            "Embarcação (para editar) ou deixe em branco para nova",
            [None] + list(embarcacao_opcoes),
            format_func=lambda i: "Nova embarcação" if i is None else embarcacao_opcoes[i],
            key="embarcacao-selecao",
        )
        existente = next((e for e in embarcacoes if e["id"] == embarcacao_id), None) if embarcacao_id else None

        with st.form("form_embarcacao", clear_on_submit=False):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome da embarcação *", max_chars=100,
                                 value=existente.get("nome") if existente else "",
                                 placeholder="Ex.: Barco Resgate 01")
            tipo = c2.selectbox("Tipo", list(TIPOS),
                                index=list(TIPOS).index(existente.get("tipo")) if existente and existente.get("tipo") in TIPOS else 0,
                                format_func=lambda t: TIPOS[t][0])
            c1, c2, c3 = st.columns(3)
            capacidade = c1.number_input("Capacidade (pessoas)", min_value=1, step=1,
                                         value=int(existente.get("capacidade")) if existente and existente.get("capacidade") else 1)
            piloto = c2.text_input("Piloto (nome)", max_chars=100,
                                   value=existente.get("piloto") if existente else "")
            telefone = c3.text_input("Telefone do piloto", max_chars=20,
                                     value=existente.get("telefone_piloto") if existente else "")
            c1, c2 = st.columns(2)
            combustivel = c1.text_input("Combustível", max_chars=50,
                                        value=existente.get("combustivel") if existente else "")
            qtd_combustivel = c2.number_input("Quantidade de combustível", min_value=0.0, step=1.0,
                                              value=float(existente.get("quantidade_combustivel")) if existente and existente.get("quantidade_combustivel") else 0.0)
            status = st.selectbox("Status", list(STATUS),
                                  index=list(STATUS).index(existente.get("status")) if existente and existente.get("status") in STATUS else 0,
                                  format_func=lambda s: STATUS[s][0])
            observacoes = st.text_area("Observações", max_chars=500,
                                       value=existente.get("observacoes") if existente else "")
            if st.form_submit_button("Salvar embarcação", type="primary"):
                if len(nome.strip()) < 3:
                    st.error("Informe o nome da embarcação (mínimo 3 caracteres).")
                else:
                    try:
                        cliente.rpc("cidc_embarcacao_cadastrar", {
                            "p_id": embarcacao_id,
                            "p_municipio_id": municipio_id,
                            "p_nome": nome.strip(),
                            "p_tipo": tipo,
                            "p_capacidade": int(capacidade),
                            "p_piloto": piloto.strip() or None,
                            "p_telefone_piloto": telefone.strip() or None,
                            "p_combustivel": combustivel.strip() or None,
                            "p_quantidade_combustivel": qtd_combustivel or None,
                            "p_status": status,
                            "p_observacoes": observacoes.strip() or None,
                        }).execute()
                        st.success("Embarcação salva com sucesso.")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Não foi possível salvar: {erro}")
    elif not pode_gerenciar:
        st.info("Cadastro e edição de embarcações estão disponíveis para coordenação, administração e logística.")

    # ---------- Lista ----------
    st.subheader("Embarcações cadastradas")
    if not embarcacoes:
        st.success("Nenhuma embarcação cadastrada neste município ainda.")
    else:
        linhas_tabela = []
        for e in embarcacoes:
            linhas_tabela.append({
                "Nome": e["nome"],
                "Tipo": TIPOS[e["tipo"]][0],
                "Capacidade": e.get("capacidade") or 0,
                "Piloto": e.get("piloto") or "—",
                "Telefone": e.get("telefone_piloto") or "—",
                "Combustível": e.get("combustivel") or "—",
                "Qtd. combustível": _numero(e.get("quantidade_combustivel")),
                "Status": STATUS[e["status"]][0],
                "Registrado em": _hora_local(e.get("registrado_em")),
            })
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Vincular embarcação a ocorrência ----------
    st.subheader("Vincular embarcação a ocorrência")
    if pode_gerenciar and ocorrencias_ativas:
        ocorrencia_opcoes = {o["id"]: f"#{o['numero']} · {o.get('titulo', '')[:60]} · {o['status']}"
                             for o in ocorrencias_ativas}
        embarcacao_disp_opcoes = {e["id"]: f"{e['nome']} ({TIPOS[e['tipo']][0]})"
                                  for e in embarcacoes if e.get("status") == "disponível"}

        c1, c2 = st.columns(2)
        ocorrencia_id = c1.selectbox("Ocorrência ativa", list(ocorrencia_opcoes),
                                     format_func=lambda i: ocorrencia_opcoes[i],
                                     key="vinculo-ocorrencia")
        embarcacao_vinculo = c2.selectbox("Embarcação disponível",
                                          [None] + list(embarcacao_disp_opcoes),
                                          format_func=lambda i: "Desvincular" if i is None else embarcacao_disp_opcoes[i],
                                          key="vinculo-embarcacao")
        if st.button("Salvar vínculo", type="primary", key="vinculo-salvar"):
            try:
                cliente.rpc("cidc_ocorrencia_atribuir_embarcacao", {
                    "p_ocorrencia": ocorrencia_id,
                    "p_embarcacao_id": embarcacao_vinculo,
                }).execute()
                st.success("Vínculo salvo com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar o vínculo: {erro}")
    elif not pode_gerenciar:
        st.info("Vinculação de embarcação a ocorrência está disponível para coordenação, administração e logística.")
    elif not ocorrencias_ativas:
        st.info("Nenhuma ocorrência ativa neste município para vincular embarcação.")

    # ---------- Relatório ----------
    linhas_relatorio = []
    for e in embarcacoes:
        # Buscar ocorrência vinculada
        oc_vinculada = next((o for o in ocorrencias_ativas if o.get("embarcacao_id") == e["id"]), None)
        linhas_relatorio.append({
            "Embarcação": e["nome"],
            "Tipo": TIPOS[e["tipo"]][0],
            "Capacidade": e.get("capacidade") or 0,
            "Piloto": e.get("piloto") or "—",
            "Status": STATUS[e["status"]][0],
            "Ocorrência vinculada": f"#{oc_vinculada['numero']}" if oc_vinculada else "—",
            "Registrado em": _hora_local(e.get("registrado_em")),
        })
    painel_relatorio(
        "Embarcações e equipes",
        [("Embarcações cadastradas", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Embarcações": total, "Disponíveis": disponiveis,
                "Em uso": em_uso, "Manutenção": manutencao},
    )
