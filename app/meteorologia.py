"""Tela de meteorologia: avisos e previsão oficiais do INMET, chuva prevista (Open-Meteo)
e chuva observada pelos pluviômetros das estações da ANA."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import streamlit as st

ORDEM_SEVERIDADE = {"Grande Perigo": 3, "Perigo": 2, "Perigo Potencial": 1}
CORES_SEVERIDADE = {"Grande Perigo": [192, 0, 0], "Perigo": [255, 140, 0], "Perigo Potencial": [240, 210, 0]}
PERIODOS = {"manha": "Manhã", "tarde": "Tarde", "noite": "Noite", "dia": "Dia"}


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}" if len(texto) >= 10 else texto


def _hora_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]} {texto[11:16]}" if len(texto) >= 16 else texto


def carregar_avisos(cliente: Any) -> list[dict[str, Any]]:
    agora = datetime.now(timezone.utc).isoformat()
    return cliente.table("avisos_meteorologicos").select("*").gte("fim", agora).order("inicio").limit(5000).execute().data or []


def carregar_previsao(cliente: Any, municipio_id: str | None = None) -> list[dict[str, Any]]:
    consulta = cliente.table("previsao_tempo").select("*").gte("data", date.today().isoformat())
    if municipio_id:
        consulta = consulta.eq("municipio_id", municipio_id)
    return consulta.order("data").limit(5000).execute().data or []


def _agrupar_avisos(avisos: list[dict[str, Any]], nomes: dict[str, str]) -> list[dict[str, Any]]:
    grupos: dict[tuple, dict[str, Any]] = {}
    for a in avisos:
        chave = (a["codigo"],)
        grupo = grupos.setdefault(chave, {**a, "municipios": []})
        grupo["municipios"].append(nomes.get(str(a["municipio_id"]).strip(), a["municipio_id"]))
    return sorted(grupos.values(), key=lambda g: (-ORDEM_SEVERIDADE.get(g["severidade"], 0), g.get("inicio") or ""))


def cartoes_avisos(avisos: list[dict[str, Any]], nomes: dict[str, str], limite_municipios: int = 25) -> list[dict]:
    linhas = []
    for grupo in _agrupar_avisos(avisos, nomes):
        municipios = sorted(set(grupo["municipios"]))
        cor = grupo.get("cor") or "#f0d200"
        lista = ", ".join(municipios[:limite_municipios]) + (f" e mais {len(municipios) - limite_municipios}" if len(municipios) > limite_municipios else "")
        st.markdown(
            f"""<div style="border-left:8px solid {cor};padding:.6rem .9rem;margin:.4rem 0;border-radius:6px;background:rgba(127,127,127,.07)">
<b>{grupo['descricao']}</b> — <i>{grupo['severidade']}</i> · de {_hora_br(grupo.get('inicio'))} até {_hora_br(grupo.get('fim'))}<br/>
<small><b>Riscos:</b> {grupo.get('riscos') or 'n/d'}</small><br/>
<small><b>Instruções:</b> {grupo.get('instrucoes') or 'n/d'}</small><br/>
<small><b>Municípios do AM ({len(municipios)}):</b> {lista}</small></div>""",
            unsafe_allow_html=True,
        )
        linhas.append({"Aviso": grupo["descricao"], "Severidade": grupo["severidade"],
                       "Início": _hora_br(grupo.get("inicio")), "Fim": _hora_br(grupo.get("fim")),
                       "Municípios": ", ".join(municipios), "Riscos": grupo.get("riscos"),
                       "Instruções": grupo.get("instrucoes")})
    st.caption("Fonte: INMET — avisos meteorológicos oficiais (apiprevmet3). Horários de Brasília.")
    return linhas


def tabela_previsao(previsao: list[dict[str, Any]]) -> list[dict]:
    linhas = [
        {"Data": _data_br(p["data"]), "Período": PERIODOS.get(p["periodo"], p["periodo"]),
         "Tempo": p.get("resumo"), "Máx (°C)": p.get("temp_max"), "Mín (°C)": p.get("temp_min"),
         "Umidade (%)": f"{p.get('umidade_min') or ''}–{p.get('umidade_max') or ''}".strip("–"),
         "Vento": p.get("vento"), "Chuva prevista (mm)": p.get("chuva_prevista_mm"), "Fonte": p.get("fonte")}
        for p in sorted(previsao, key=lambda p: (p["data"], list(PERIODOS).index(p["periodo"]) if p["periodo"] in PERIODOS else 9))
    ]
    st.dataframe(linhas, hide_index=True, width="stretch")
    return linhas


def _mapa_avisos(avisos: list[dict], previsao: list[dict], municipios: list[dict]) -> None:
    import pydeck as pdk

    pior: dict[str, str] = {}
    for a in avisos:
        codigo = str(a["municipio_id"]).strip()
        if ORDEM_SEVERIDADE.get(a["severidade"], 0) > ORDEM_SEVERIDADE.get(pior.get(codigo, ""), 0):
            pior[codigo] = a["severidade"]
    chuva: dict[str, float] = {}
    for p in previsao:
        if p["periodo"] == "dia" and p.get("chuva_prevista_mm") is not None:
            codigo = str(p["municipio_id"]).strip()
            chuva[codigo] = max(chuva.get(codigo, 0), float(p["chuva_prevista_mm"]))
    pontos = [
        {"lat": m["latitude"], "lon": m["longitude"], "nome": m["nome"],
         "cor": CORES_SEVERIDADE.get(pior.get(str(m["id_ibge"]).strip()), [170, 190, 210]) + [210],
         "raio": 4000 + chuva.get(str(m["id_ibge"]).strip(), 0) * 600,
         "detalhe": f"{pior.get(str(m['id_ibge']).strip(), 'sem aviso INMET')} · chuva prevista máx. "
                    f"{chuva.get(str(m['id_ibge']).strip(), 0):g} mm/dia"}
        for m in municipios if m.get("latitude") is not None
    ]
    if not pontos:
        return
    st.pydeck_chart(
        pdk.Deck(
            layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]", get_fill_color="cor",
                              get_radius="raio", radius_min_pixels=5, stroked=True, get_line_color=[255, 255, 255],
                              line_width_min_pixels=1, pickable=True)],
            initial_view_state=pdk.ViewState(latitude=-4.6, longitude=-63.5, zoom=4.7),
            map_provider="carto", map_style="light", tooltip={"html": "<b>{nome}</b><br/>{detalhe}"},
        ),
        height=440,
    )
    st.caption("Cor: pior aviso INMET vigente (amarelo = perigo potencial, laranja = perigo, vermelho = grande "
               "perigo; cinza = sem aviso). Tamanho: chuva prevista máxima em um dia (Open-Meteo). "
               "Mapa © OpenStreetMap / CARTO.")


def _chuva_observada(cliente: Any, nomes: dict[str, str]) -> list[dict]:
    """Soma das últimas 24 h dos pluviômetros das estações ANA."""
    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    estacoes = {e["id"]: e for e in cliente.table("estacoes").select("id,nome,municipio_id").execute().data or []}
    soma: dict[str, float] = {}
    for leitura in (
        cliente.table("leituras").select("estacao_id,chuva_mm").gte("data_hora_leitura", desde)
        .not_.is_("chuva_mm", "null").limit(10000).execute().data or []
    ):
        soma[leitura["estacao_id"]] = soma.get(leitura["estacao_id"], 0) + float(leitura["chuva_mm"] or 0)
    linhas = sorted(
        [{"Estação": estacoes[i]["nome"], "Município": nomes.get(str(estacoes[i].get("municipio_id") or "").strip()),
          "Chuva 24 h (mm)": round(v, 1)} for i, v in soma.items() if i in estacoes],
        key=lambda l: -l["Chuva 24 h (mm)"],
    )
    return linhas


def _queimadas(cliente: Any, nomes: dict[str, str]) -> list[dict]:
    """Focos de calor do INPE nas últimas 24 h: totais, ranking e mapa."""
    import pydeck as pdk
    from app.visual import grafico_barras

    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    focos = (cliente.table("focos_calor").select("lat,lon,municipio_id,satelite,risco_fogo,dias_sem_chuva,frp,data_hora")
             .gte("data_hora", desde).limit(20000).execute().data or [])
    if not focos:
        st.info("Nenhum foco de calor do INPE nas últimas 24 h (ou coleta ainda não executada).")
        return []
    por_municipio: dict[str, list] = {}
    for f in focos:
        por_municipio.setdefault(str(f.get("municipio_id") or "").strip(), []).append(f)
    c1, c2, c3 = st.columns(3)
    c1.metric("Focos (24 h)", len(focos))
    c2.metric("Municípios com focos", len([k for k in por_municipio if k]))
    c3.metric("Risco de fogo máximo", f"{max((f.get('risco_fogo') or 0) for f in focos):.2f}")
    linhas = sorted(
        [{"Município": nomes.get(k, k or "não identificado"), "Focos (24 h)": len(v),
          "Risco de fogo máx.": round(max((f.get("risco_fogo") or 0) for f in v), 2),
          "Dias sem chuva (máx.)": max((f.get("dias_sem_chuva") or 0) for f in v)}
         for k, v in por_municipio.items()],
        key=lambda l: -l["Focos (24 h)"],
    )
    grafico_barras({l["Município"]: l["Focos (24 h)"] for l in linhas[:15]}, "Municípios com mais focos (24 h)")
    pontos = [{"lat": f["lat"], "lon": f["lon"], "risco": f.get("risco_fogo") or 0,
               "detalhe": f"{nomes.get(str(f.get('municipio_id') or '').strip(), '')} · risco {f.get('risco_fogo')} · "
                          f"{f.get('satelite')} · {str(f.get('data_hora'))[:16]} UTC"} for f in focos]
    st.pydeck_chart(pdk.Deck(
        layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]",
                          get_fill_color="[230, 80 + 120 * (1 - risco), 20, 200]", get_radius=1500,
                          radius_min_pixels=2, pickable=True)],
        initial_view_state=pdk.ViewState(latitude=-4.6, longitude=-63.5, zoom=4.7),
        map_provider="carto", map_style="light", tooltip={"html": "{detalhe}"},
    ), height=420)
    st.dataframe(linhas, hide_index=True, width="stretch")
    st.caption("Fonte: INPE — Programa Queimadas (CSV diário). Detecções de todos os satélites: o mesmo fogo pode "
               "aparecer mais de uma vez. Mapa © OpenStreetMap / CARTO.")
    return linhas


def _pluviometros(cliente: Any, nomes: dict[str, str]) -> list[dict]:
    dados = cliente.table("chuva_cemaden").select("*").execute().data or []
    linhas = sorted(
        [{"Pluviômetro": d["nome"], "Município": nomes.get(str(d.get("municipio_id") or "").strip(), ""),
          "1 h (mm)": d.get("acc1h_mm"), "24 h (mm)": d.get("acc24h_mm"), "72 h (mm)": d.get("acc72h_mm"),
          "96 h (mm)": d.get("acc96h_mm"), "Última leitura (UTC)": str(d.get("medido_em") or "")[:16].replace("T", " ")}
         for d in dados],
        key=lambda l: -(l["24 h (mm)"] or 0),
    )
    if not linhas:
        st.info("Sem dados do Cemaden (coleta ainda não executada).")
    st.dataframe(linhas, hide_index=True, width="stretch")
    st.caption("Fonte: Cemaden — pluviômetros automáticos (mapa interativo). '—' = sem dado no período.")
    return linhas


def renderizar_meteorologia() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.relatorio_menu import painel_relatorio
    from app.visual import grafico_barras

    st.title("Meteorologia")
    st.caption("Avisos e previsão oficiais do INMET, chuva prevista (Open-Meteo) e chuva observada (ANA).")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil({
            "voluntario", "gestor_nacional", "gestor_estadual", "coordenador_municipal", "operador_monitoramento",
            "agente_campo", "saude_assistencia", "logistica_abastecimento", "pesquisador", "administrador",
        })
        municipios_dict = carregar_municipios(cliente)
        nomes = {c: m["nome"] for c, m in municipios_dict.items()}
        municipios = cliente.table("municipios").select("id_ibge,nome,latitude,longitude").execute().data or []
        avisos = carregar_avisos(cliente)
        previsao = carregar_previsao(cliente)
    except Exception as erro:
        st.error(f"Não foi possível carregar a meteorologia (aplique a migration 202610140008): {erro}")
        return

    com_aviso = {str(a["municipio_id"]).strip() for a in avisos}
    pior = max((a["severidade"] for a in avisos), key=lambda s: ORDEM_SEVERIDADE.get(s, 0), default="nenhum")
    chuva_dia = [p for p in previsao if p["periodo"] == "dia" and p.get("chuva_prevista_mm") is not None]
    maior = max(chuva_dia, key=lambda p: float(p["chuva_prevista_mm"]), default=None)
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.metric("Municípios do AM com aviso INMET", len(com_aviso))
    with c2.container(border=True):
        st.metric("Pior severidade vigente", pior)
    with c3.container(border=True):
        st.metric("Maior chuva prevista (1 dia)", f"{float(maior['chuva_prevista_mm']):g} mm" if maior else "n/d")
        if maior:
            st.caption(f"{nomes.get(str(maior['municipio_id']).strip())} em {_data_br(maior['data'])} (Open-Meteo)")

    aba_avisos, aba_mapa, aba_previsao, aba_chuva, aba_fogo, aba_cemaden = st.tabs(
        ["⚠️ Avisos INMET", "🗺️ Mapa", "📅 Previsão por município", "🌧️ Chuva prevista e observada",
         "🔥 Queimadas (INPE)", "📡 Pluviômetros Cemaden"]
    )
    with aba_fogo:
        try:
            linhas_fogo = _queimadas(cliente, nomes)
        except Exception as erro:
            linhas_fogo = []
            st.warning(f"Queimadas indisponíveis (aplique a migration 202610140010): {erro}")
    with aba_cemaden:
        try:
            linhas_cemaden = _pluviometros(cliente, nomes)
        except Exception as erro:
            linhas_cemaden = []
            st.warning(f"Cemaden indisponível (aplique a migration 202610140010): {erro}")
    with aba_avisos:
        linhas_avisos = cartoes_avisos(avisos, nomes) if avisos else []
        if not avisos:
            st.success("Nenhum aviso meteorológico do INMET vigente para o Amazonas.")
    with aba_mapa:
        _mapa_avisos(avisos, previsao, municipios)
    with aba_previsao:
        codigos = sorted(nomes, key=lambda c: nomes[c])
        padrao = perfil.get("municipio_id")
        escolhido = st.selectbox("Município", codigos, format_func=lambda c: nomes[c],
                                 index=codigos.index(padrao) if padrao in codigos else 0, key="met-municipio")
        linhas_previsao = tabela_previsao([p for p in previsao if str(p["municipio_id"]).strip() == escolhido])
        st.caption("Resumo, temperaturas, umidade e vento: INMET (previsão oficial). Chuva em mm: Open-Meteo (modelo).")
    with aba_chuva:
        totais: dict[str, float] = {}
        for p in chuva_dia:
            codigo = str(p["municipio_id"]).strip()
            totais[codigo] = totais.get(codigo, 0) + float(p["chuva_prevista_mm"])
        top = dict(sorted(((nomes.get(c, c), round(v, 1)) for c, v in totais.items()), key=lambda i: -i[1])[:15])
        if top:
            grafico_barras(top, "Chuva prevista acumulada nos próximos dias (mm) — 15 maiores")
        try:
            linhas_chuva = _chuva_observada(cliente, nomes)
        except Exception:
            linhas_chuva = []
        st.subheader("Chuva observada nas últimas 24 h (pluviômetros ANA)")
        if linhas_chuva:
            st.dataframe(linhas_chuva, hide_index=True, width="stretch")
        else:
            st.info("Sem registros de chuva nas estações ANA nas últimas 24 h.")
    painel_relatorio(
        "Relatório meteorológico",
        [("Avisos INMET vigentes", linhas_avisos), (f"Previsão — {nomes.get(escolhido)}", linhas_previsao),
         ("Chuva prevista acumulada (mm)", [{"Município": k, "Chuva prevista (mm)": v} for k, v in top.items()]),
         ("Chuva observada 24 h (ANA)", linhas_chuva), ("Focos de calor 24 h (INPE)", linhas_fogo),
         ("Pluviômetros Cemaden", linhas_cemaden)],
        resumo={"Municípios com aviso INMET": len(com_aviso), "Pior severidade": pior,
                "Fontes": "INMET (avisos e previsão), Open-Meteo (chuva prevista), ANA e Cemaden (chuva observada), "
                          "INPE (focos de calor)"},
    )


def secao_publica(cliente: Any, municipio_id: str) -> None:
    """Aviso INMET vigente e previsão do município na página pública (dados oficiais)."""
    try:
        avisos = [a for a in carregar_avisos(cliente) if str(a["municipio_id"]).strip() == municipio_id]
        previsao = carregar_previsao(cliente, municipio_id)
    except Exception:
        return
    st.subheader("🌦️ Tempo e avisos meteorológicos")
    if avisos:
        cartoes_avisos(avisos, {municipio_id: ""}, limite_municipios=0)
    else:
        st.success("Sem aviso meteorológico do INMET vigente para este município.")
    if previsao:
        tabela_previsao(previsao)
        st.caption("Previsão: INMET. Chuva em mm: Open-Meteo (modelo numérico).")
