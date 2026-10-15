"""Ocorrências com atendimento: fila por prioridade, equipe responsável e linha do tempo.

Toda mudança passa pelas funções do banco (migration 202610140014), que conferem quem pode
fazer o quê e registram o evento. O app só mostra os botões que fazem sentido para o perfil.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

TIPOS = {
    "resgate": ("🛟 Resgate de pessoas", [200, 30, 30]),
    "cheia_alagamento": ("🌊 Cheia / alagamento", [21, 101, 192]),
    "isolamento_comunidade": ("🚫 Comunidade isolada", [120, 60, 160]),
    "incendio_fumaca": ("🔥 Incêndio / fumaça", [230, 81, 0]),
    "saude": ("🏥 Atendimento de saúde", [0, 137, 123]),
    "abastecimento": ("📦 Água / alimento / combustível", [121, 85, 72]),
    "desabamento_erosao": ("🏚️ Desabamento / terras caídas", [93, 64, 55]),
    "outro": ("❓ Outro", [120, 120, 120]),
}
DO_RELATO = {"cheia_alagamento": "cheia_alagamento", "rio_subindo": "cheia_alagamento", "chuva_forte": "cheia_alagamento",
             "isolamento_comunidade": "isolamento_comunidade", "rio_baixando": "isolamento_comunidade",
             "incendio_fumaca": "incendio_fumaca", "outro": "outro"}
PRIORIDADES = {"critica": ("🔴 CRÍTICA", [198, 40, 40]), "alta": ("🟠 Alta", [239, 108, 0]),
               "media": ("🟡 Média", [251, 192, 45]), "baixa": ("🟢 Baixa", [67, 160, 71])}
STATUS = {"aberta": "📥 Aberta (sem equipe)", "atribuida": "👥 Equipe designada", "em_deslocamento": "🚤 A caminho",
          "em_atendimento": "🛠️ Em atendimento", "resolvida": "✅ Resolvida", "cancelada": "🚫 Cancelada"}
PROXIMO = {"atribuida": ("em_deslocamento", "🚤 Saímos / a caminho"),
           "em_deslocamento": ("em_atendimento", "🛠️ Chegamos / atendendo")}
ENCERRADAS = {"resolvida", "cancelada"}
EQUIPES = {"agente_campo": "Agentes de campo", "saude_assistencia": "Saúde e assistência",
           "logistica_abastecimento": "Logística / barcos", "operador_monitoramento": "Monitoramento",
           "coordenador_municipal": "Coordenação", "voluntario": "Voluntários"}
PERFIS_ABRIR = {"coordenador_municipal", "operador_monitoramento", "agente_campo", "saude_assistencia",
                "logistica_abastecimento", "administrador"}
PERFIS_TELA = PERFIS_ABRIR | {"voluntario", "gestor_estadual", "gestor_nacional"}
FUSO = timezone(timedelta(hours=-4))


def _instante(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        quando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def duracao(inicio: Any, fim: Any = None, agora: datetime | None = None) -> str:
    comeco = _instante(inicio)
    if not comeco:
        return ""
    return formatar_minutos(((_instante(fim) or agora or datetime.now(timezone.utc)) - comeco).total_seconds() / 60)


def formatar_minutos(total: float) -> str:
    minutos = int(total)
    if minutos < 60:
        return f"{max(minutos, 0)} min"
    if minutos < 48 * 60:
        return f"{minutos // 60} h {minutos % 60:02d} min"
    return f"{minutos // 1440} dias"


def ordenar_fila(ocorrencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mais grave primeiro; na mesma prioridade, a mais antiga primeiro."""
    peso = {p: i for i, p in enumerate(PRIORIDADES)}
    return sorted(ocorrencias, key=lambda o: (peso.get(o["prioridade"], 9), str(o["aberta_em"])))


def indicadores(ocorrencias: list[dict[str, Any]]) -> dict[str, Any]:
    abertas = [o for o in ocorrencias if o["status"] not in ENCERRADAS]
    resolvidas = [o for o in ocorrencias if o["status"] == "resolvida" and o.get("resolvida_em")]
    minutos = [(_instante(o["resolvida_em"]) - _instante(o["aberta_em"])).total_seconds() / 60 for o in resolvidas]
    return {
        "abertas": len(abertas),
        "graves": sum(1 for o in abertas if o["prioridade"] in {"critica", "alta"}),
        "sem_equipe": sum(1 for o in abertas if not o.get("equipe_funcao") and not o.get("responsavel_id")),
        "pessoas": sum(o.get("pessoas_envolvidas") or 0 for o in abertas),
        "tempo_medio": formatar_minutos(sum(minutos) / len(minutos)) if minutos else "—",
    }


def linhas_relatorio(ocorrencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"Nº": o["numero"], "Prioridade": PRIORIDADES[o["prioridade"]][0].split(" ", 1)[1].capitalize(),
         "Tipo": TIPOS[o["tipo"]][0].split(" ", 1)[1], "Título": o["titulo"],
         "Situação": STATUS[o["status"]].split(" ", 1)[1], "Equipe": EQUIPES.get(o.get("equipe_funcao"), "—"),
         "Responsável": o.get("responsavel_nome") or "—", "Pessoas": o.get("pessoas_envolvidas"),
         "Local": o.get("local_descricao") or "",
         "Aberta em": (_instante(o["aberta_em"]).astimezone(FUSO).strftime("%d/%m %H:%M")),
         "Tempo": duracao(o["aberta_em"], o.get("resolvida_em")), "Resultado": o.get("resultado") or ""}
        for o in ordenar_fila(ocorrencias)
    ]


def _rpc(cliente: Any, funcao: str, parametros: dict[str, Any], sucesso: str) -> None:
    try:
        cliente.rpc(funcao, parametros).execute()
    except Exception as erro:
        mensagem = getattr(erro, "message", None) or str(erro)
        st.error(f"Não foi possível: {mensagem}")
        return
    st.session_state["_aviso_ocorrencia"] = sucesso
    st.rerun()


def _form_abrir(cliente: Any, municipio_id: str, relatos: list[dict], ja_viraram: set[str]) -> None:
    from app.voluntarios import TIPOS_RELATO

    candidatos = {r["id"]: r for r in relatos if r["id"] not in ja_viraram and r["status"] != "descartado"}
    origem = None
    if candidatos:
        origem = st.selectbox(
            "A partir de um relato de campo (opcional)", [None] + list(candidatos),
            format_func=lambda i: "— nova ocorrência, sem relato —" if i is None else
            f"{TIPOS_RELATO.get(candidatos[i]['tipo'], ('Outro',))[0]} · {candidatos[i]['status']} · "
            f"{(candidatos[i].get('descricao') or '')[:60]}", key=f"origem-{municipio_id}")
    relato = candidatos.get(origem) if origem else None
    with st.form(f"abrir-{municipio_id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tipos = list(TIPOS)
        tipo = c1.selectbox("Tipo", tipos, format_func=lambda t: TIPOS[t][0],
                            index=tipos.index(DO_RELATO.get(relato["tipo"], "outro")) if relato else 0)
        prioridade = c2.selectbox("Prioridade", list(PRIORIDADES), format_func=lambda p: PRIORIDADES[p][0], index=1)
        titulo = st.text_input("Resumo (o que está acontecendo)", max_chars=120,
                               placeholder="Ex.: Família ilhada no telhado na comunidade São Raimundo")
        descricao = st.text_area("Detalhes", value=(relato.get("descricao") or "") if relato else "", max_chars=1000)
        c1, c2 = st.columns([3, 1])
        local = c1.text_input("Local / referência", max_chars=300, placeholder="Ex.: margem esquerda, depois do porto")
        pessoas = c2.number_input("Pessoas envolvidas", min_value=0, max_value=100000, step=1, value=0)
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude (opcional)", value=float(relato["latitude"]) if relato else None,
                              format="%.5f", min_value=-90.0, max_value=90.0)
        lon = c2.number_input("Longitude (opcional)", value=float(relato["longitude"]) if relato else None,
                              format="%.5f", min_value=-180.0, max_value=180.0)
        if st.form_submit_button("Abrir ocorrência", type="primary"):
            if len(titulo.strip()) < 5:
                st.error("Escreva um resumo com pelo menos 5 letras.")
                return
            _rpc(cliente, "cidc_ocorrencia_abrir", {
                "p_municipio_id": municipio_id, "p_tipo": tipo, "p_prioridade": prioridade, "p_titulo": titulo,
                "p_descricao": descricao, "p_local": local, "p_latitude": lat, "p_longitude": lon,
                "p_pessoas": int(pessoas) or None, "p_relato_id": origem,
            }, "Ocorrência aberta.")


def _cartao(cliente: Any, o: dict[str, Any], perfil: dict[str, Any], eventos: list[dict],
            pessoas: dict[str, str], coordena: bool) -> None:
    eu = perfil["id"]
    do_municipio = perfil.get("municipio_id") == str(o["municipio_id"]).strip()
    da_equipe = o.get("responsavel_id") == eu or (o.get("equipe_funcao") == perfil["perfil"] and do_municipio)
    pode_assumir = not o.get("responsavel_id") and do_municipio and perfil["perfil"] in (
        PERFIS_ABRIR - {"coordenador_municipal", "administrador"}) | {"voluntario"}
    with st.container(border=True):
        st.markdown(f"**#{o['numero']} · {PRIORIDADES[o['prioridade']][0]} · {TIPOS[o['tipo']][0]}** — "
                    f"{_texto(o['titulo'])}")
        st.caption(f"{STATUS[o['status']]} · equipe: {EQUIPES.get(o.get('equipe_funcao'), 'nenhuma')} · "
                   f"responsável: {o.get('responsavel_nome') or 'ninguém'} · aberta há {duracao(o['aberta_em'])}"
                   + (f" · {o['pessoas_envolvidas']} pessoa(s)" if o.get("pessoas_envolvidas") else "")
                   + (f" · 📍 {_texto(o['local_descricao'])}" if o.get("local_descricao") else ""))
        if o.get("descricao"):
            st.markdown(_texto(o["descricao"]))
        botoes = st.columns(3)
        if pode_assumir and botoes[0].button("🙋 Assumir", key=f"assumir-{o['id']}"):
            _rpc(cliente, "cidc_ocorrencia_atualizar", {"p_ocorrencia": o["id"], "p_assumir": True}, "Você assumiu.")
        if (da_equipe or coordena) and o["status"] in PROXIMO:
            proximo, rotulo = PROXIMO[o["status"]]
            if botoes[1].button(rotulo, key=f"avancar-{o['id']}", type="primary"):
                _rpc(cliente, "cidc_ocorrencia_atualizar", {"p_ocorrencia": o["id"], "p_status": proximo},
                     "Situação atualizada.")
        with st.expander(f"Linha do tempo ({len(eventos)}) e ações"):
            for e in eventos:
                quando = _instante(e["criado_em"]).astimezone(FUSO).strftime("%d/%m %H:%M")
                st.markdown(f"`{quando}` **{_texto(e['autor_nome'])}** — {_texto(e['texto'])}")
            if not (da_equipe or coordena):
                return
            with st.form(f"acao-{o['id']}", clear_on_submit=True):
                texto = st.text_input("Anotação / resultado", max_chars=500,
                                      placeholder="Ex.: 4 pessoas levadas ao abrigo Escola Rio Purus")
                opcoes = ["anotar"]
                if da_equipe or coordena:
                    opcoes += ["resolvida"]
                if coordena:
                    opcoes += ["cancelada"]
                acao = st.radio("O que fazer", opcoes, horizontal=True, format_func=lambda a: {
                    "anotar": "📝 Só anotar", "resolvida": "✅ Resolver", "cancelada": "🚫 Cancelar"}[a])
                equipe = responsavel = prioridade = None
                if coordena:
                    c1, c2, c3 = st.columns(3)
                    equipe = c1.selectbox("Designar equipe", [None] + list(EQUIPES),
                                          format_func=lambda e: "— manter —" if e is None else EQUIPES[e])
                    responsavel = c2.selectbox("Responsável", [None] + list(pessoas),
                                               format_func=lambda i: "— manter —" if i is None else pessoas[i])
                    prioridade = c3.selectbox("Prioridade", [None] + list(PRIORIDADES),
                                              format_func=lambda p: "— manter —" if p is None else PRIORIDADES[p][0])
                if st.form_submit_button("Salvar"):
                    if acao == "resolvida" and not texto.strip():
                        st.error("Para resolver, escreva o resultado do atendimento.")
                        return
                    if acao == "anotar" and not texto.strip() and not (equipe or responsavel or prioridade):
                        st.error("Escreva uma anotação ou escolha uma mudança.")
                        return
                    _rpc(cliente, "cidc_ocorrencia_atualizar", {
                        "p_ocorrencia": o["id"], "p_status": None if acao == "anotar" else acao,
                        "p_texto": texto.strip() or None, "p_equipe": equipe, "p_responsavel": responsavel,
                        "p_prioridade": prioridade,
                    }, "Ocorrência atualizada.")


def _texto(valor: str) -> str:
    from app.chat import texto_seguro

    return texto_seguro(valor)


def _mapa(abertas: list[dict[str, Any]]) -> None:
    import pydeck as pdk

    pontos = [{"lat": o["latitude"], "lon": o["longitude"], "cor": PRIORIDADES[o["prioridade"]][1] + [220],
               "titulo": f"#{o['numero']} {TIPOS[o['tipo']][0]}", "detalhe": f"{STATUS[o['status']]} · {o['titulo']}"}
              for o in abertas if o.get("latitude") is not None and o.get("longitude") is not None]
    if not pontos:
        return
    st.pydeck_chart(pdk.Deck(
        layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]", get_fill_color="cor",
                          get_radius=1500, radius_min_pixels=7, stroked=True, get_line_color=[255, 255, 255],
                          line_width_min_pixels=2, pickable=True)],
        initial_view_state=pdk.ViewState(latitude=sum(p["lat"] for p in pontos) / len(pontos),
                                         longitude=sum(p["lon"] for p in pontos) / len(pontos), zoom=8),
        map_provider="carto", map_style="light", tooltip={"html": "<b>{titulo}</b><br/>{detalhe}"},
    ), height=320)
    st.caption("Ocorrências abertas com localização. Cor = prioridade. Mapa © OpenStreetMap / CARTO.")


def renderizar_ocorrencias() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("🚑 Ocorrências")
    st.caption("Cada chamado vira um caso com equipe responsável e linha do tempo até ser resolvido. "
               "Emergência com risco de vida: ligue 193 (Bombeiros) ou 199 (Defesa Civil).")
    mostrar_aviso()
    if st.session_state.get("_aviso_ocorrencia"):
        st.success(st.session_state.pop("_aviso_ocorrencia"))
    try:
        cliente, perfil = exigir_perfil(PERFIS_TELA)
        municipio_id = _municipio_da_tela(cliente, perfil, "ocorrencias")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        desde = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        todas = (cliente.table("ocorrencias").select("*").eq("municipio_id", municipio_id)
                 .order("aberta_em", desc=True).limit(500).execute().data or [])
        ocorrencias = [o for o in todas if o["status"] not in ENCERRADAS or str(o.get("resolvida_em") or "") >= desde]
        ids = [o["id"] for o in ocorrencias]
        eventos = (cliente.table("ocorrencia_eventos").select("*").in_("ocorrencia_id", ids)
                   .order("criado_em").limit(5000).execute().data or []) if ids else []
    except Exception as erro:
        st.error(f"Não foi possível carregar as ocorrências (aplique a migration 202610140014): {erro}")
        return
    municipio = carregar_municipios(cliente).get(municipio_id)
    nome_municipio = f"{municipio['nome']}/{municipio['uf']}" if municipio else municipio_id
    por_ocorrencia: dict[str, list] = {}
    for e in eventos:
        por_ocorrencia.setdefault(e["ocorrencia_id"], []).append(e)
    coordena = perfil["perfil"] == "administrador" or (
        perfil["perfil"] == "coordenador_municipal" and perfil.get("municipio_id") == municipio_id)
    pode_abrir = perfil["perfil"] == "administrador" or (
        perfil["perfil"] in PERFIS_ABRIR and perfil.get("municipio_id") == municipio_id)

    k = indicadores(ocorrencias)
    c = st.columns(5)
    c[0].metric("Abertas", k["abertas"])
    c[1].metric("Críticas ou altas", k["graves"])
    c[2].metric("Sem equipe", k["sem_equipe"])
    c[3].metric("Pessoas envolvidas", k["pessoas"])
    c[4].metric("Tempo médio até resolver", k["tempo_medio"], help="Resolvidas nos últimos 30 dias")

    if pode_abrir:
        with st.expander("➕ Abrir ocorrência", expanded=not ocorrencias):
            try:
                relatos = (cliente.table("relatos").select("id,tipo,status,descricao,latitude,longitude")
                           .eq("municipio_id", municipio_id).gte("criado_em", (datetime.now(timezone.utc)
                           - timedelta(hours=72)).isoformat()).order("criado_em", desc=True).limit(50).execute().data or [])
            except Exception:
                relatos = []
            _form_abrir(cliente, municipio_id, relatos, {o["relato_id"] for o in todas if o.get("relato_id")})
    elif perfil["perfil"] == "voluntario":
        st.info("Viu algo? Registre em **Relatos de campo**: a equipe transforma o relato em ocorrência. "
                "Você também pode **assumir** uma ocorrência do seu município (ex.: se tem barco).")

    abertas = ordenar_fila([o for o in ocorrencias if o["status"] not in ENCERRADAS])
    pessoas: dict[str, str] = {}
    if coordena:
        try:
            pessoas = {p["id"]: f"{p['nome']} ({EQUIPES.get(p['perfil'], p['perfil'])})"
                       for p in cliente.rpc("cidc_chat_pessoas", {}).execute().data or []
                       if str(p.get("municipio_id") or "").strip() == municipio_id}
            pessoas[perfil["id"]] = f"{perfil['nome']} (você)"
        except Exception:
            pessoas = {}
    _mapa(abertas)
    st.subheader(f"Fila de atendimento ({len(abertas)})")
    if not abertas:
        st.success("Nenhuma ocorrência aberta neste município.")
    filtro = st.radio("Mostrar", ["todas", "minhas", "sem_equipe"], horizontal=True, key=f"filtro-{municipio_id}",
                      format_func={"todas": "Todas", "minhas": "Minhas / da minha equipe",
                                   "sem_equipe": "Sem equipe"}.get) if abertas else "todas"
    for o in abertas:
        minha = o.get("responsavel_id") == perfil["id"] or o.get("equipe_funcao") == perfil["perfil"]
        if (filtro == "minhas" and not minha) or (filtro == "sem_equipe" and (o.get("equipe_funcao") or o.get("responsavel_id"))):
            continue
        _cartao(cliente, o, perfil, por_ocorrencia.get(o["id"], []), pessoas, coordena)

    encerradas = [o for o in ocorrencias if o["status"] in ENCERRADAS]
    if encerradas:
        with st.expander(f"Encerradas nos últimos 30 dias ({len(encerradas)})"):
            st.dataframe(linhas_relatorio(encerradas), hide_index=True, width="stretch")
            if coordena:
                reabrir = st.selectbox("Reabrir", [None] + [o["id"] for o in encerradas], key=f"reabrir-{municipio_id}",
                                       format_func=lambda i: "—" if i is None else
                                       next(f"#{o['numero']} {o['titulo']}" for o in encerradas if o["id"] == i))
                if reabrir and st.button("Reabrir ocorrência", key=f"btn-reabrir-{municipio_id}"):
                    _rpc(cliente, "cidc_ocorrencia_atualizar", {"p_ocorrencia": reabrir, "p_status": "aberta",
                                                                "p_texto": "Reaberta pela coordenação"}, "Reaberta.")

    linha_tempo = [
        {"Ocorrência": next((f"#{o['numero']}" for o in ocorrencias if o["id"] == e["ocorrencia_id"]), ""),
         "Quando": _instante(e["criado_em"]).astimezone(FUSO).strftime("%d/%m %H:%M"),
         "Quem": e["autor_nome"], "O quê": e["texto"]}
        for e in eventos
    ]
    painel_relatorio(
        "Ocorrências e atendimento",
        [("Fila aberta", linhas_relatorio(abertas)), ("Encerradas (30 dias)", linhas_relatorio(encerradas)),
         ("Linha do tempo", linha_tempo)],
        subtitulo=nome_municipio,
        resumo={"Abertas": k["abertas"], "Críticas ou altas": k["graves"], "Sem equipe": k["sem_equipe"],
                "Pessoas envolvidas (abertas)": k["pessoas"], "Tempo médio até resolver (30 dias)": k["tempo_medio"]},
    )
