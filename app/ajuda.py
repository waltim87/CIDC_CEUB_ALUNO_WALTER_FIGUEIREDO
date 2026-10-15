"""Ajuda humanitária: estoque por movimentos e entregas a famílias, comunidades e abrigos.

Saldo, permissões e o aviso de entrega repetida ficam no banco (migration 202610140016).
Nomes das famílias só aparecem para quem já pode vê-las (RLS de familias_abrigadas).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

ITENS = {
    "cesta_basica": ("🧺 Cesta básica", "un"), "agua_potavel": ("💧 Água potável", "litros"),
    "kit_higiene": ("🧼 Kit de higiene", "un"), "kit_limpeza": ("🧹 Kit de limpeza", "un"),
    "colchao": ("🛏️ Colchão", "un"), "rede": ("🪢 Rede", "un"), "cobertor": ("🧣 Cobertor", "un"),
    "roupas": ("👕 Roupas", "peças"), "kit_dormitorio": ("🛌 Kit dormitório", "un"),
    "filtro_agua": ("🚰 Filtro de água", "un"), "hipoclorito": ("🧪 Hipoclorito", "frascos"),
    "racao_animal": ("🐾 Ração animal", "kg"), "combustivel": ("⛽ Combustível", "litros"), "outro": ("📦 Outro", "un"),
}
ITENS_FAMILIA = ["cesta_basica", "agua_potavel", "kit_higiene", "kit_limpeza", "colchao", "rede", "cobertor",
                 "roupas", "kit_dormitorio", "filtro_agua", "hipoclorito"]
ENTRADAS = {"doacao": "Doação", "compra": "Compra", "envio_estadual": "Envio do Estado",
            "envio_federal": "Envio federal", "transferencia": "Transferência de outro município",
            "perda": "Perda / avaria (saída)", "ajuste": "Ajuste de inventário (+/-)"}
MOTIVOS = {**ENTRADAS, "entrega_familia": "Entrega a família", "entrega_comunidade": "Entrega a comunidade",
           "entrega_abrigo": "Entrega ao abrigo"}
PERFIS_TELA = {"logistica_abastecimento", "coordenador_municipal", "saude_assistencia", "administrador",
               "voluntario", "gestor_estadual", "gestor_nacional", "agente_campo", "operador_monitoramento"}
JANELA_DIAS = 7
FUSO = timezone(timedelta(hours=-4))


def _instante(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        quando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def _br(valor: Any) -> str:
    quando = _instante(valor)
    return quando.astimezone(FUSO).strftime("%d/%m %H:%M") if quando else ""


def _numero(valor: Any) -> str:
    numero = float(valor or 0)
    return f"{numero:,.0f}".replace(",", ".") if numero.is_integer() else f"{numero:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def familias_sem_item(cobertura: list[dict[str, Any]], campo: str = "ultima_cesta", dias: int = JANELA_DIAS,
                      agora: datetime | None = None) -> list[dict[str, Any]]:
    """Famílias ainda abrigadas que nunca receberam o item ou receberam há mais de ``dias``."""
    limite = (agora or datetime.now(timezone.utc)) - timedelta(days=dias)
    return [c for c in cobertura if not _instante(c.get(campo)) or _instante(c.get(campo)) < limite]


def itens_preenchidos(valores: dict[str, Any]) -> dict[str, float]:
    return {item: float(qtd) for item, qtd in valores.items() if qtd and float(qtd) > 0}


def _mensagem(erro: Exception) -> str:
    return getattr(erro, "message", None) or str(erro)


def _aviso(texto: str) -> None:
    st.session_state["_aviso_ajuda"] = texto
    st.rerun()


def _campos_itens(prefixo: str, itens: list[str]) -> dict[str, float]:
    valores = {}
    colunas = st.columns(4)
    for posicao, item in enumerate(itens):
        rotulo, unidade = ITENS[item]
        valores[item] = colunas[posicao % 4].number_input(f"{rotulo} ({unidade})", min_value=0.0, step=1.0,
                                                           value=0.0, key=f"{prefixo}-{item}")
    return itens_preenchidos(valores)


def _bloco_estoque(cliente: Any, municipio_id: str, saldos: dict[str, float], movimenta: bool) -> list[dict]:
    if saldos:
        principais = [i for i in ITENS if i in saldos][:8]
        colunas = st.columns(4)
        for posicao, item in enumerate(principais):
            rotulo, unidade = ITENS[item]
            colunas[posicao % 4].metric(rotulo, f"{_numero(saldos[item])} {unidade}")
    else:
        st.info("Estoque vazio. Registre a primeira entrada abaixo (doação, compra ou envio do Estado).")
    linhas = [{"Item": ITENS[i][0], "Saldo": saldos[i], "Unidade": ITENS[i][1]} for i in ITENS if i in saldos]
    if not movimenta:
        st.caption("Entradas e ajustes são feitos pela logística ou pela coordenação do município.")
        return linhas
    with st.form(f"entrada-{municipio_id}", clear_on_submit=True):
        st.markdown("**Registrar entrada, perda ou ajuste**")
        c1, c2, c3 = st.columns(3)
        item = c1.selectbox("Item", list(ITENS), format_func=lambda i: f"{ITENS[i][0]} ({ITENS[i][1]})")
        quantidade = c2.number_input("Quantidade", value=0.0, step=1.0,
                                     help="No ajuste, use número negativo para diminuir o saldo.")
        motivo = c3.selectbox("Motivo", list(ENTRADAS), format_func=ENTRADAS.get)
        c1, c2 = st.columns(2)
        origem = c1.text_input("De onde veio / para onde foi", max_chars=200,
                               placeholder="Ex.: Defesa Civil do Amazonas, ofício 123")
        observacao = c2.text_input("Observação", max_chars=500)
        if st.form_submit_button("Registrar", type="primary"):
            try:
                cliente.rpc("cidc_estoque_movimentar", {
                    "p_municipio_id": municipio_id, "p_item": item, "p_quantidade": quantidade, "p_motivo": motivo,
                    "p_origem_destino": origem, "p_observacao": observacao}).execute()
            except Exception as erro:
                st.error(f"Não registrado: {_mensagem(erro)}")
                return linhas
            _aviso(f"{ENTRADAS[motivo]} de {_numero(abs(quantidade))} {ITENS[item][1]} de {ITENS[item][0]} registrada.")
    return linhas


def _bloco_familias(cliente: Any, municipio_id: str, familias: list[dict], abrigos: dict[str, str],
                    movimentos: list[dict], saldos: dict[str, float]) -> None:
    if not familias:
        st.info("Nenhuma família abrigada visível para você neste município. Quem registra entregas a famílias: "
                "coordenação, saúde/assistência, logística e o coordenador de cada abrigo.")
        return
    filtro = st.selectbox("Abrigo", ["todos"] + sorted(abrigos, key=abrigos.get),
                          format_func=lambda a: "Todos" if a == "todos" else abrigos[a], key=f"abrigo-{municipio_id}")
    visiveis = [f for f in familias if filtro == "todos" or f.get("abrigo_id") == filtro]
    if not visiveis:
        st.info("Nenhuma família neste abrigo.")
        return
    por_id = {f["id"]: f for f in visiveis}
    familia_id = st.selectbox("Família (responsável)", list(por_id), key=f"familia-{municipio_id}",
                              format_func=lambda i: f"{por_id[i]['responsavel_nome']} · "
                                                    f"{abrigos.get(por_id[i].get('abrigo_id'), 'sem abrigo')}")
    recebidas = [m for m in movimentos if m.get("familia_id") == familia_id]
    if recebidas:
        st.caption("Já recebeu: " + "; ".join(f"{_br(m['registrado_em'])} {ITENS[m['item']][0]} "
                                              f"{_numero(-m['quantidade'])}" for m in recebidas[:8]))
    else:
        st.caption("Esta família ainda não recebeu nenhuma entrega registrada.")
    with st.form(f"entrega-familia-{municipio_id}", clear_on_submit=True):
        itens = _campos_itens(f"fam-{municipio_id}", ITENS_FAMILIA)
        c1, c2 = st.columns(2)
        justificativa = c1.text_input(f"Justificativa (só se repetir item em menos de {JANELA_DIAS} dias)", max_chars=300,
                                      placeholder="Ex.: família cresceu; perdeu os itens na enchente")
        observacao = c2.text_input("Observação", max_chars=500)
        if st.form_submit_button("Registrar entrega", type="primary"):
            if not itens:
                st.error("Informe a quantidade de pelo menos um item.")
                return
            falta = [ITENS[i][0] for i, q in itens.items() if saldos.get(i, 0) < q]
            if falta:
                st.error("Saldo insuficiente: " + ", ".join(falta) + ". Registre a entrada no estoque primeiro.")
                return
            try:
                resposta = cliente.rpc("cidc_ajuda_entregar", {
                    "p_municipio_id": municipio_id, "p_itens": itens, "p_familia_id": familia_id,
                    "p_justificativa": justificativa or None, "p_observacao": observacao or None,
                    "p_janela_dias": JANELA_DIAS}).execute().data or {}
            except Exception as erro:
                mensagem = _mensagem(erro)
                if "REPETIDA" in mensagem:
                    st.warning(mensagem.replace("REPETIDA: ", "⚠️ ") + ".")
                else:
                    st.error(f"Entrega não registrada: {mensagem}")
                return
            extra = " (entrega repetida justificada)" if resposta.get("repetidos") else ""
            _aviso(f"Entrega registrada para {por_id[familia_id]['responsavel_nome']}{extra}; estoque atualizado.")


def _bloco_comunidades(cliente: Any, municipio_id: str, comunidades: dict[str, str], abrigos: dict[str, str],
                       saldos: dict[str, float]) -> None:
    destinos = {f"c:{i}": f"🛶 {n}" for i, n in comunidades.items()} | {f"a:{i}": f"🏠 {n}" for i, n in abrigos.items()}
    if not destinos:
        st.info("Cadastre comunidades e abrigos em Gestão municipal para registrar entregas a eles.")
        return
    with st.form(f"entrega-comunidade-{municipio_id}", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        destino = c1.selectbox("Destino", list(destinos), format_func=destinos.get)
        pessoas = c2.number_input("Pessoas atendidas", min_value=0, step=1, value=0)
        itens = _campos_itens(f"com-{municipio_id}", list(ITENS))
        observacao = st.text_input("Observação (barco, responsável pela entrega, etc.)", max_chars=500)
        if st.form_submit_button("Registrar entrega", type="primary"):
            if not itens:
                st.error("Informe a quantidade de pelo menos um item.")
                return
            falta = [ITENS[i][0] for i, q in itens.items() if saldos.get(i, 0) < q]
            if falta:
                st.error("Saldo insuficiente: " + ", ".join(falta) + ".")
                return
            tipo, identificador = destino.split(":", 1)
            try:
                cliente.rpc("cidc_ajuda_entregar", {
                    "p_municipio_id": municipio_id, "p_itens": itens,
                    "p_comunidade_id": identificador if tipo == "c" else None,
                    "p_abrigo_id": identificador if tipo == "a" else None,
                    "p_pessoas": int(pessoas) or None, "p_observacao": observacao or None}).execute()
            except Exception as erro:
                st.error(f"Entrega não registrada: {_mensagem(erro)}")
                return
            _aviso(f"Entrega registrada para {destinos[destino][2:]}; estoque atualizado.")


def renderizar_ajuda() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.familias import usuario_coordena_abrigo
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("📦 Ajuda humanitária")
    st.caption("Estoque com entradas e saídas, e entregas a famílias abrigadas, comunidades e abrigos. "
               "Cada entrega baixa o estoque e fica registrada; repetir o mesmo item para a mesma família em "
               f"menos de {JANELA_DIAS} dias exige justificativa.")
    mostrar_aviso()
    if st.session_state.get("_aviso_ajuda"):
        st.success(st.session_state.pop("_aviso_ajuda"))
    try:
        from app.comum import cliente_supabase
        from app.auth import obter_perfil

        cliente = cliente_supabase()
        perfil = obter_perfil(cliente)
        if not perfil or (perfil["perfil"] not in PERFIS_TELA and not usuario_coordena_abrigo(cliente, perfil["id"])):
            raise PermissionError("Seu perfil não tem acesso a este painel.")
        municipio_id = _municipio_da_tela(cliente, perfil, "ajuda")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipio = carregar_municipios(cliente).get(municipio_id)
        saldos = {s["item"]: float(s["saldo"]) for s in cliente.table("ajuda_saldo").select("item,saldo")
                  .eq("municipio_id", municipio_id).execute().data or [] if float(s["saldo"]) != 0}
        desde = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        movimentos = (cliente.table("ajuda_movimentos").select("*").eq("municipio_id", municipio_id)
                      .gte("registrado_em", desde).order("registrado_em", desc=True).limit(3000).execute().data or [])
        abrigos = {a["id"]: a["nome"] for a in cliente.table("abrigos").select("id,nome")
                   .eq("municipio_id", municipio_id).execute().data or []}
        comunidades = {c["id"]: c["nome"] for c in cliente.table("comunidades").select("id,nome")
                       .eq("municipio_id", municipio_id).order("nome").execute().data or []}
        familias = (cliente.table("familias_abrigadas").select("id,responsavel_nome,abrigo_id")
                    .eq("municipio_id", municipio_id).is_("data_saida", "null").order("responsavel_nome")
                    .limit(2000).execute().data or [])
        cobertura = (cliente.table("ajuda_cobertura_familias").select("*").eq("municipio_id", municipio_id)
                     .execute().data or []) if familias else []
    except PermissionError as erro:
        st.error(str(erro))
        return
    except Exception as erro:
        st.error(f"Não foi possível carregar a ajuda humanitária (aplique a migration 202610140016): {erro}")
        return
    movimenta = perfil["perfil"] == "administrador" or (
        perfil["perfil"] in {"coordenador_municipal", "logistica_abastecimento"} and perfil.get("municipio_id") == municipio_id)

    saidas = [m for m in movimentos if m["quantidade"] < 0 and m["motivo"].startswith("entrega")]
    sem_cesta = familias_sem_item(cobertura)
    c = st.columns(4)
    c[0].metric("Entregas (30 dias)", len({m.get("entrega_id") for m in saidas}))
    c[1].metric("Cestas entregues (30 dias)", _numero(-sum(m["quantidade"] for m in saidas if m["item"] == "cesta_basica")))
    c[2].metric("Água entregue (30 dias)", f"{_numero(-sum(m['quantidade'] for m in saidas if m['item'] == 'agua_potavel'))} L")
    c[3].metric(f"Famílias sem cesta há {JANELA_DIAS}+ dias", len(sem_cesta) if familias else "—",
                help="Famílias ainda abrigadas que você pode ver")

    abas = st.tabs(["📦 Estoque", "👪 Entregar a família", "🛶 Comunidade ou abrigo", "📊 Entregas e cobertura"])
    with abas[0]:
        linhas_estoque = _bloco_estoque(cliente, municipio_id, saldos, movimenta)
    with abas[1]:
        _bloco_familias(cliente, municipio_id, familias, abrigos, movimentos, saldos)
    with abas[2]:
        if movimenta:
            _bloco_comunidades(cliente, municipio_id, comunidades, abrigos, saldos)
        else:
            st.info("Entregas a comunidades e abrigos são registradas pela logística ou pela coordenação.")
    nomes_familias = {f["id"]: f["responsavel_nome"] for f in familias}
    linhas_entregas = [
        {"Data": _br(m["registrado_em"]), "Item": ITENS[m["item"]][0].split(" ", 1)[1],
         "Quantidade": -m["quantidade"], "Unidade": ITENS[m["item"]][1], "Tipo": MOTIVOS[m["motivo"]],
         "Destino": (nomes_familias.get(m.get("familia_id"), "família (nome restrito)") if m.get("familia_id")
                     else comunidades.get(m.get("comunidade_id")) or abrigos.get(m.get("abrigo_id")) or ""),
         "Abrigo": abrigos.get(m.get("abrigo_id"), ""), "Pessoas": m.get("pessoas_atendidas"),
         "Repetição justificada": m.get("justificativa_repeticao") or ""}
        for m in saidas
    ]
    linhas_entradas = [
        {"Data": _br(m["registrado_em"]), "Item": ITENS[m["item"]][0].split(" ", 1)[1], "Quantidade": m["quantidade"],
         "Unidade": ITENS[m["item"]][1], "Motivo": MOTIVOS[m["motivo"]], "Origem/destino": m.get("origem_destino") or "",
         "Observação": m.get("observacao") or ""}
        for m in movimentos if not m["motivo"].startswith("entrega")
    ]
    linhas_cobertura = [
        {"Família (responsável)": nomes_familias.get(c["familia_id"], ""), "Abrigo": abrigos.get(c.get("abrigo_id"), ""),
         "No abrigo desde": str(c.get("data_entrada") or "")[:10], "Última cesta": _br(c.get("ultima_cesta")) or "nunca",
         "Último kit higiene": _br(c.get("ultimo_kit_higiene")) or "nunca", "Entregas": c.get("entregas") or 0}
        for c in sorted(sem_cesta, key=lambda c: str(c.get("ultima_cesta") or ""))
    ]
    with abas[3]:
        if linhas_cobertura:
            st.warning(f"⚠️ {len(linhas_cobertura)} família(s) abrigada(s) sem cesta básica há mais de {JANELA_DIAS} dias "
                       "(ou nunca receberam).")
            st.dataframe(linhas_cobertura, hide_index=True, width="stretch")
        elif familias:
            st.success(f"Todas as famílias abrigadas visíveis receberam cesta nos últimos {JANELA_DIAS} dias.")
        st.markdown("**Entregas dos últimos 30 dias**")
        if linhas_entregas:
            st.dataframe(linhas_entregas, hide_index=True, width="stretch")
        else:
            st.caption("Nenhuma entrega registrada.")
        if linhas_entradas:
            st.markdown("**Entradas, perdas e ajustes (30 dias)**")
            st.dataframe(linhas_entradas, hide_index=True, width="stretch")

    painel_relatorio(
        "Ajuda humanitária",
        [("Estoque atual", linhas_estoque), ("Entregas (30 dias)", linhas_entregas),
         ("Entradas e ajustes (30 dias)", linhas_entradas), (f"Famílias sem cesta há {JANELA_DIAS}+ dias", linhas_cobertura)],
        subtitulo=f"{municipio['nome']}/{municipio['uf']}" if municipio else municipio_id,
        resumo={"Entregas (30 dias)": len({m.get("entrega_id") for m in saidas}),
                "Itens com saldo": len(saldos), f"Famílias sem cesta há {JANELA_DIAS}+ dias": len(sem_cesta)},
    )
