"""Chat interno: canal geral por município, canais entre comunidades e conversas privadas.

As regras de acesso ficam no banco (migration 202610140012): o app só mostra o que o
Supabase devolve para a conta logada. CPF digitado em mensagem é mascarado no banco.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

PERFIS_CHAT = {
    "voluntario", "gestor_nacional", "gestor_estadual", "coordenador_municipal", "operador_monitoramento",
    "agente_campo", "saude_assistencia", "logistica_abastecimento", "administrador",
}
ICONES_CANAL = {"municipio": "🏘️", "comunidades": "🛶", "privado": "🔒"}
TIPOS_CANAL = {"municipio": "geral do município", "comunidades": "entre comunidades", "privado": "privado"}
ROTULOS_PERFIL = {
    "voluntario": "voluntário(a)", "coordenador_municipal": "coordenação municipal",
    "operador_monitoramento": "monitoramento", "agente_campo": "agente de campo",
    "saude_assistencia": "saúde/assistência", "logistica_abastecimento": "logística",
    "gestor_estadual": "gestão estadual", "gestor_nacional": "gestão nacional", "administrador": "administração",
}
AVATARES = {"voluntario": "🙋", "coordenador_municipal": "🏛️", "saude_assistencia": "🏥", "agente_campo": "📍",
            "logistica_abastecimento": "🚤", "operador_monitoramento": "📡"}
LIMITE_MENSAGENS = 150
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")
try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Manaus")
except Exception:  # Windows sem tzdata
    FUSO = timezone(timedelta(hours=-4))


def texto_seguro(texto: str) -> str:
    """Mostra o texto como foi digitado: sem links, imagens ou formatação vindos de mensagem."""
    return _MARKDOWN.sub(r"\\\1", texto or "").replace("\n", "  \n")


def hora_local(valor: str | None, agora: datetime | None = None) -> str:
    if not valor:
        return ""
    try:
        quando = datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(FUSO)
    except ValueError:
        return str(valor)[:16]
    hoje = (agora or datetime.now(timezone.utc)).astimezone(FUSO).date()
    return quando.strftime("%H:%M") if quando.date() == hoje else quando.strftime("%d/%m %H:%M")


def rotulo_canal(canal: dict[str, Any]) -> str:
    return f"{ICONES_CANAL.get(canal['tipo'], '💬')} {canal['nome']}"


def _carregar_canais(cliente: Any) -> list[dict[str, Any]]:
    canais = cliente.table("chat_canais").select("*").eq("arquivado", False).limit(300).execute().data or []
    ordem = {"municipio": 0, "comunidades": 1, "privado": 2}
    return sorted(canais, key=lambda c: (ordem.get(c["tipo"], 9), c["nome"].lower()))


def _novo_canal(cliente: Any, perfil: dict[str, Any], municipios: dict[str, dict[str, str]]) -> None:
    nomes_municipios = {c: f"{m['nome']}/{m.get('uf', '')}" for c, m in municipios.items()}
    tipo = st.radio("Tipo de canal", ["municipio", "comunidades", "privado"], horizontal=True,
                    format_func=lambda t: f"{ICONES_CANAL[t]} {TIPOS_CANAL[t].capitalize()}", key="chat-tipo")
    if tipo == "municipio":
        codigos = sorted(municipios, key=lambda c: nomes_municipios[c])
        padrao = perfil.get("municipio_id")
        municipio_id = st.selectbox("Município", codigos, format_func=nomes_municipios.get,
                                    index=codigos.index(padrao) if padrao in codigos else 0, key="chat-municipio")
        st.caption("Todo mundo com acesso ao município participa. Se o canal já existir, ele é aberto.")
        if st.button("Abrir canal do município", type="primary"):
            _criar(cliente, {"p_nome": "geral", "p_tipo": "municipio", "p_municipio_id": municipio_id})
        return

    if tipo == "comunidades":
        comunidades = cliente.table("comunidades").select("id,nome,municipio_id").order("nome").limit(2000).execute().data or []
        if not comunidades:
            st.info("Nenhuma comunidade cadastrada ainda. A coordenação municipal cadastra em "
                    "**Gestão municipal → Comunidades**.")
            return
        rotulos = {c["id"]: f"{c['nome']} — {nomes_municipios.get(str(c['municipio_id']).strip(), '')}" for c in comunidades}
        with st.form("chat-novo-comunidades", clear_on_submit=True):
            escolhidas = st.multiselect("Comunidades (pode juntar comunidades de municípios diferentes)",
                                        list(rotulos), format_func=rotulos.get)
            nome = st.text_input("Nome do canal", placeholder="Ex.: Comunidades do Médio Purus")
            descricao = st.text_input("Para que serve (opcional)")
            if st.form_submit_button("Criar canal", type="primary"):
                if not escolhidas or len(nome.strip()) < 3:
                    st.error("Escolha ao menos uma comunidade e dê um nome ao canal.")
                else:
                    _criar(cliente, {"p_nome": nome, "p_tipo": "comunidades", "p_comunidades": escolhidas,
                                     "p_descricao": descricao})
        st.caption("Participam todas as pessoas com acesso aos municípios dessas comunidades.")
        return

    pessoas = cliente.rpc("cidc_chat_pessoas", {}).execute().data or []
    if not pessoas:
        st.info("Ainda não há outras pessoas cadastradas que você possa chamar.")
        return
    filtro = st.selectbox("Filtrar pessoas por município", ["todos"] + sorted({str(p.get("municipio_id") or "").strip()
                          for p in pessoas if p.get("municipio_id")}, key=lambda c: nomes_municipios.get(c, c)),
                          format_func=lambda c: "Todos" if c == "todos" else nomes_municipios.get(c, c), key="chat-filtro")
    visiveis = [p for p in pessoas if filtro == "todos" or str(p.get("municipio_id") or "").strip() == filtro]
    rotulos = {p["id"]: (f"{p['nome']} · {ROTULOS_PERFIL.get(p['perfil'], p['perfil'])}"
                         f" · {nomes_municipios.get(str(p.get('municipio_id') or '').strip(), 'sem município')}")
               for p in visiveis}
    with st.form("chat-novo-privado", clear_on_submit=True):
        escolhidas = st.multiselect("Pessoas", list(rotulos), format_func=rotulos.get)
        nome = st.text_input("Nome da conversa", placeholder="Ex.: Equipe do abrigo / Barcos de resgate")
        if st.form_submit_button("Criar conversa", type="primary"):
            if not escolhidas or len(nome.strip()) < 3:
                st.error("Escolha ao menos uma pessoa e dê um nome à conversa.")
            else:
                _criar(cliente, {"p_nome": nome, "p_tipo": "privado", "p_membros": escolhidas})
    st.caption("Só as pessoas escolhidas veem a conversa. Você pode incluir mais gente depois.")


def _criar(cliente: Any, parametros: dict[str, Any]) -> None:
    try:
        canal_id = cliente.rpc("cidc_chat_criar_canal", parametros).execute().data
    except Exception as erro:
        st.error(f"Não foi possível criar o canal: {erro}")
        return
    st.session_state["chat_canal"] = canal_id
    st.rerun()


def _membros(cliente: Any, canal: dict[str, Any], perfil: dict[str, Any]) -> None:
    membros = cliente.table("chat_membros").select("usuario_id").eq("canal_id", canal["id"]).execute().data or []
    pessoas = {p["id"]: p for p in cliente.rpc("cidc_chat_pessoas", {}).execute().data or []}
    nomes = [perfil["nome"] + " (você)" if m["usuario_id"] == perfil["id"] else
             pessoas.get(m["usuario_id"], {}).get("nome", "pessoa sem acesso a você") for m in membros]
    st.write(f"**{len(membros)} participantes:** " + ", ".join(sorted(nomes)))
    if canal.get("criado_por") == perfil["id"] or perfil["perfil"] == "administrador":
        fora = {i: p["nome"] for i, p in pessoas.items() if i not in {m["usuario_id"] for m in membros}}
        with st.form(f"chat-incluir-{canal['id']}", clear_on_submit=True):
            novos = st.multiselect("Incluir pessoas", list(fora), format_func=fora.get)
            if st.form_submit_button("Incluir") and novos:
                try:
                    cliente.rpc("cidc_chat_adicionar_membros", {"p_canal_id": canal["id"], "p_membros": novos}).execute()
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível incluir: {erro}")
    if st.button("Sair desta conversa", key=f"chat-sair-{canal['id']}"):
        cliente.table("chat_membros").delete().eq("canal_id", canal["id"]).eq("usuario_id", perfil["id"]).execute()
        st.session_state.pop("chat_canal", None)
        st.rerun()


def _mensagens(cliente: Any, canal_id: str, perfil: dict[str, Any]) -> None:
    @st.fragment(run_every=10)
    def atualizar() -> None:
        dados = (
            cliente.table("chat_mensagens").select("id,usuario_id,autor_nome,autor_perfil,texto,criado_em")
            .eq("canal_id", canal_id).order("criado_em", desc=True).limit(LIMITE_MENSAGENS).execute().data or []
        )
        caixa = st.container(height=480)
        if not dados:
            caixa.info("Nenhuma mensagem ainda. Escreva a primeira lá embaixo.")
        for m in reversed(dados):
            proprio = m["usuario_id"] == perfil["id"]
            with caixa.chat_message("user" if proprio else m["autor_nome"] or "?",
                                    avatar=AVATARES.get(m["autor_perfil"], "💬")):
                st.markdown(f"**{texto_seguro(m['autor_nome'])}** · "
                            f"{ROTULOS_PERFIL.get(m['autor_perfil'], m['autor_perfil'])} · "
                            f"{hora_local(m['criado_em'])}")
                st.markdown(texto_seguro(m["texto"]))
        st.caption("Atualiza sozinho a cada 10 segundos. Horário de Manaus.")

    atualizar()


def renderizar_chat() -> None:
    from app.comum import carregar_municipios, exigir_perfil

    st.title("💬 Chat interno")
    st.caption("Conversa entre voluntários, comunidades e equipes. Não é canal oficial de alerta: em "
               "emergência, ligue 199 (Defesa Civil) ou 193 (Bombeiros). Não envie CPF, documentos ou "
               "dados de saúde de terceiros (LGPD). CPF digitado é mascarado automaticamente.")
    try:
        cliente, perfil = exigir_perfil(PERFIS_CHAT)
        municipios = carregar_municipios(cliente)
        canais = _carregar_canais(cliente)
    except Exception as erro:
        st.error(f"Chat indisponível: {erro}")
        return

    por_id = {c["id"]: c for c in canais}
    atual = st.session_state.get("chat_canal")
    if atual not in por_id and canais:
        meu = [c for c in canais if c["tipo"] == "municipio" and str(c.get("municipio_id") or "").strip()
               == perfil.get("municipio_id")]
        atual = (meu or canais)[0]["id"]

    lateral, principal = st.columns([1, 3])
    with lateral:
        if canais:
            atual = st.radio("Canais", list(por_id), index=list(por_id).index(atual),
                             format_func=lambda i: rotulo_canal(por_id[i]), key="chat-lista")
            st.session_state["chat_canal"] = atual
        with st.expander("➕ Novo canal ou conversa", expanded=not canais):
            _novo_canal(cliente, perfil, municipios)

    with principal:
        if not canais:
            st.info("Você ainda não participa de nenhum canal. Abra o canal do seu município ao lado.")
            return
        canal = por_id[atual]
        st.subheader(rotulo_canal(canal))
        detalhe = TIPOS_CANAL.get(canal["tipo"], "")
        if canal["tipo"] == "comunidades":
            nomes = cliente.table("comunidades").select("nome").in_("id", canal["comunidades"]).execute().data or []
            detalhe += ": " + ", ".join(n["nome"] for n in nomes)
        st.caption(detalhe + (f" — {canal['descricao']}" if canal.get("descricao") else ""))
        if canal["tipo"] == "privado":
            with st.expander("👥 Participantes"):
                _membros(cliente, canal, perfil)
        _mensagens(cliente, canal["id"], perfil)

    texto = st.chat_input("Escreva uma mensagem", max_chars=1000)
    if texto and texto.strip():
        try:
            cliente.table("chat_mensagens").insert(
                {"canal_id": atual, "usuario_id": perfil["id"], "texto": texto.strip()}
            ).execute()
            st.rerun()
        except Exception as erro:
            st.error(f"Mensagem não enviada: {erro}")
