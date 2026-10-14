"""Componentes visuais: mapa de risco por município, cartões e gráficos.

Tudo gratuito: pydeck e Altair já vêm com o Streamlit; o mapa base é o
CARTO (OpenStreetMap), sem token. Cada número mostra fonte e horário.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from core.robo import ORDEM_SINAIS, ROTULOS_DIRECAO, ROTULOS_SINAL

CORES_SINAL = {
    "sem_dados": [150, 150, 150],
    "normal": [46, 160, 67],
    "atencao": [230, 190, 30],
    "alerta": [240, 130, 20],
    "alto": [215, 60, 40],
}
COR_SEM_ESTACAO = [205, 210, 218]
HEX_SINAL = {k: "#%02x%02x%02x" % tuple(v) for k, v in CORES_SINAL.items()}
AVISO_ROBO = (
    "Sinais do robô: triagem indicativa com limiares hipotéticos (config/robo.yaml), "
    "sem validação oficial. Texto por IA gratuita (Gemini) ou modelo fixo; exige revisão humana."
)

CSS = """
<style>
.cidc-cartao {border-left: 6px solid var(--cor); padding: .6rem .9rem; margin: .4rem 0;
  border-radius: 6px; background: rgba(127,127,127,.07);}
.cidc-cartao h4 {margin: 0 0 .25rem 0; font-size: 1rem;}
.cidc-cartao p {margin: 0 0 .25rem 0; font-size: .92rem;}
.cidc-cartao small {opacity: .75;}
.cidc-selo {display:inline-block; padding: 0 .5rem; border-radius: 99px; color: #fff;
  font-size: .78rem; font-weight: 600; background: var(--cor);}
.cidc-legenda span {display:inline-block; margin-right: .9rem; font-size: .85rem;}
.cidc-legenda i {display:inline-block; width:.8rem; height:.8rem; border-radius:50%;
  margin-right:.3rem; vertical-align:-1px;}
</style>
"""


def aplicar_estilo() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _hora_local(valor: str | None) -> str:
    """UTC ISO -> 'dd/mm HH:MM (Manaus)'; Manaus = UTC-4."""
    if not valor:
        return "n/d"
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m %H:%M") + " (Manaus)"


# ---------------------------------------------------------------- dados
def carregar_analises(cliente: Any, limite: int = 1000) -> dict[str, dict[str, Any]]:
    """Análise mais recente do robô por município (respeita o RLS do usuário)."""
    try:
        linhas = (
            cliente.table("analises_risco")
            .select(
                "municipio_id,gerado_em,sinal,direcao,texto,metodo,modelo,"
                "fatores_json,estacoes_json,fontes_json,data_hora_leitura_referencia"
            )
            .order("gerado_em", desc=True)
            .limit(limite)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    ultimas: dict[str, dict[str, Any]] = {}
    for linha in linhas:
        ultimas.setdefault(str(linha["municipio_id"]).strip(), linha)
    return ultimas


def carregar_municipios_mapa(cliente: Any) -> list[dict[str, Any]]:
    try:
        return (
            cliente.table("municipios")
            .select("id_ibge,nome,uf,populacao,latitude,longitude")
            .limit(1000)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def carregar_series(cliente: Any, horas: int = 72) -> list[dict[str, Any]]:
    """Leituras de nível das últimas ``horas`` com o nome da estação."""
    limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    estacoes = {
        e["id"]: e
        for e in (
            cliente.table("estacoes")
            .select("id,codigo_oficial,nome,rio,municipio_id,latitude,longitude")
            .limit(1000)
            .execute()
            .data
            or []
        )
    }
    leituras = (
        cliente.table("leituras")
        .select("estacao_id,data_hora_leitura,nivel_cm,vazao,chuva_mm")
        .gte("data_hora_leitura", limite)
        .order("data_hora_leitura")
        .limit(5000)
        .execute()
        .data
        or []
    )
    saida = []
    for leitura in leituras:
        estacao = estacoes.get(leitura["estacao_id"])
        if estacao and leitura.get("nivel_cm") is not None:
            saida.append(
                {
                    "Estação": f"{estacao['nome']} ({estacao.get('codigo_oficial')})",
                    "Data/hora": leitura["data_hora_leitura"],
                    "Nível (cm)": float(leitura["nivel_cm"]),
                }
            )
    return saida


# ---------------------------------------------------------------- cartões
def legenda() -> None:
    itens = "".join(
        f'<span><i style="background:{HEX_SINAL[s]}"></i>{ROTULOS_SINAL[s]}</span>'
        for s in ORDEM_SINAIS
    )
    itens += f'<span><i style="background:#cdd2da"></i>Sem estação</span>'
    st.markdown(f'<div class="cidc-legenda">{itens}</div>', unsafe_allow_html=True)


def _escapar(texto: Any) -> str:
    return (
        str("" if texto is None else texto)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def cartao_analise(nome: str, analise: dict[str, Any]) -> None:
    sinal = analise.get("sinal", "sem_dados")
    direcao = ROTULOS_DIRECAO.get(analise.get("direcao") or "", "")
    origem = "IA (Gemini)" if analise.get("metodo") == "ia" else "modelo fixo"
    fontes = ", ".join(
        f"{f.get('nome')} @ {_hora_local(f.get('data_hora_leitura'))}"
        for f in analise.get("fontes_json") or []
    ) or "sem leitura recente"
    st.markdown(
        f"""<div class="cidc-cartao" style="--cor:{HEX_SINAL.get(sinal, '#999')}">
<h4>{_escapar(nome)} <span class="cidc-selo" style="--cor:{HEX_SINAL.get(sinal, '#999')}">
{ROTULOS_SINAL.get(sinal, sinal)}</span> {_escapar(direcao)}</h4>
<p>{_escapar(analise.get('texto'))}</p>
<small>Análise de {_hora_local(analise.get('gerado_em'))} · texto: {origem} · fontes: {_escapar(fontes)}</small>
</div>""",
        unsafe_allow_html=True,
    )


def kpis_robo(
    analises: dict[str, dict[str, Any]], municipios: list[dict[str, Any]]
) -> None:
    contagem = {s: 0 for s in ORDEM_SINAIS}
    for analise in analises.values():
        contagem[analise.get("sinal", "sem_dados")] += 1
    em_risco = contagem["atencao"] + contagem["alerta"] + contagem["alto"]
    populacao = {str(m["id_ibge"]).strip(): m.get("populacao") or 0 for m in municipios}
    pop_risco = sum(
        populacao.get(c, 0)
        for c, a in analises.items()
        if a.get("sinal") in {"atencao", "alerta", "alto"}
    )
    ultima = max((a.get("gerado_em") or "" for a in analises.values()), default=None)
    colunas = st.columns(4)
    with colunas[0].container(border=True):
        st.metric("Municípios monitorados", len(analises))
    with colunas[1].container(border=True):
        st.metric("Em Atenção ou acima", em_risco)
    with colunas[2].container(border=True):
        st.metric("População nesses municípios", f"{pop_risco:,}".replace(",", "."))
        st.caption("IBGE Censo 2022")
    with colunas[3].container(border=True):
        st.metric("Última análise do robô", _hora_local(ultima).replace(" (Manaus)", "") if ultima else "n/d")
        st.caption("Horário de Manaus")


# ---------------------------------------------------------------- mapa
def mapa_risco(
    municipios: list[dict[str, Any]],
    analises: dict[str, dict[str, Any]],
    *,
    classes_indice: dict[str, str] | None = None,
    altura: int = 520,
) -> None:
    """Pontos por cidade (cor = sinal do robô, tamanho = população) e estações ANA."""
    import pydeck as pdk

    classes_indice = classes_indice or {}
    pontos, estacoes = [], []
    for municipio in municipios:
        if municipio.get("latitude") is None or municipio.get("longitude") is None:
            continue
        codigo = str(municipio["id_ibge"]).strip()
        analise = analises.get(codigo)
        sinal = analise.get("sinal") if analise else None
        populacao = municipio.get("populacao") or 0
        pontos.append(
            {
                "nome": f"{municipio['nome']}/{municipio.get('uf', '')}",
                "lon": municipio["longitude"],
                "lat": municipio["latitude"],
                "cor": CORES_SINAL.get(sinal, COR_SEM_ESTACAO) + [215],
                # Monitorados ganham destaque; tamanho cresce com a população.
                "raio": (9000 if analise else 4000) + math.sqrt(populacao) * 45,
                "titulo": ROTULOS_SINAL.get(sinal, "Sem estação monitorada"),
                "detalhe": (
                    f"População {populacao:,} (IBGE 2022)".replace(",", ".")
                    + (f" · Índice: {classes_indice[codigo]}" if codigo in classes_indice else "")
                    + (f"<br/>{_escapar(analise['texto'])[:280]}" if analise else "")
                    + (f"<br/><i>Análise {_hora_local(analise['gerado_em'])}</i>" if analise else "")
                ),
            }
        )
        for estacao in (analise or {}).get("estacoes_json") or []:
            if estacao.get("latitude") is None:
                continue
            estacoes.append(
                {
                    "nome": f"Estação ANA {estacao.get('estacao')} ({estacao.get('codigo')})",
                    "lon": estacao["longitude"],
                    "lat": estacao["latitude"],
                    "cor": CORES_SINAL.get(estacao.get("sinal"), [150, 150, 150]) + [255],
                    "titulo": f"Rio {estacao.get('rio') or ''} — {ROTULOS_SINAL.get(estacao.get('sinal'), '')}",
                    "detalhe": (
                        f"Nível {estacao.get('nivel_cm')} cm · variação 24 h: "
                        f"{estacao.get('variacao_24h_cm')} cm · leitura "
                        f"{_hora_local(estacao.get('data_hora_leitura'))}"
                    ),
                }
            )
    if not pontos:
        st.info("Sem coordenadas de municípios: aplique a migration 202610140002.")
        return
    camadas = [
        pdk.Layer(
            "ScatterplotLayer",
            data=pontos,
            get_position="[lon, lat]",
            get_fill_color="cor",
            get_radius="raio",
            radius_min_pixels=4,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=estacoes,
            get_position="[lon, lat]",
            get_fill_color="cor",
            get_radius=1800,
            radius_min_pixels=5,
            stroked=True,
            get_line_color=[20, 40, 90],
            line_width_min_pixels=2,
            pickable=True,
        ),
    ]
    st.pydeck_chart(
        pdk.Deck(
            layers=camadas,
            initial_view_state=pdk.ViewState(latitude=-4.6, longitude=-63.5, zoom=4.7),
            map_provider="carto",
            map_style="light",
            tooltip={"html": "<b>{nome}</b><br/>{titulo}<br/>{detalhe}"},
        ),
        height=altura,
    )
    legenda()
    st.caption(
        "Círculos grandes: sede do município (tamanho = população). Círculos com borda azul: "
        "estações ANA. Mapa base © OpenStreetMap / CARTO. " + AVISO_ROBO
    )


# ---------------------------------------------------------------- gráficos
def grafico_barras(dados: dict[str, int], titulo: str, cores: dict[str, str] | None = None) -> None:
    import altair as alt
    import pandas as pd

    if not dados:
        return
    tabela = pd.DataFrame({"Categoria": list(dados), "Quantidade": list(dados.values())})
    cores = cores or {}
    escala = alt.Scale(
        domain=list(dados), range=[cores.get(c, "#2f6db5") for c in dados]
    )
    st.altair_chart(
        alt.Chart(tabela, title=titulo)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Quantidade:Q", title=None, axis=alt.Axis(format="d", tickMinStep=1)),
            y=alt.Y(
                "Categoria:N", sort=list(dados), title=None,
                axis=alt.Axis(labelOverlap=False, labelLimit=220),
            ),
            color=alt.Color("Categoria:N", scale=escala, legend=None),
            tooltip=["Categoria", "Quantidade"],
        )
        .properties(height=max(140, 42 * len(dados))),
        width="stretch",
    )


def grafico_sinais(analises: dict[str, dict[str, Any]]) -> None:
    contagem = {ROTULOS_SINAL[s]: 0 for s in ORDEM_SINAIS}
    for analise in analises.values():
        contagem[ROTULOS_SINAL.get(analise.get("sinal"), "Sem dados")] += 1
    grafico_barras(
        contagem,
        "Municípios por sinal do robô",
        {ROTULOS_SINAL[s]: HEX_SINAL[s] for s in ORDEM_SINAIS},
    )


def grafico_series(series: list[dict[str, Any]], titulo: str = "Nível dos rios (últimas 72 h)") -> None:
    import altair as alt
    import pandas as pd

    if not series:
        st.info("Sem leituras de nível nas últimas 72 h.")
        return
    tabela = pd.DataFrame(series)
    tabela["Data/hora"] = pd.to_datetime(tabela["Data/hora"], utc=True).dt.tz_convert(
        "America/Manaus"
    )
    st.altair_chart(
        alt.Chart(tabela, title=titulo)
        .mark_line(point=alt.OverlayMarkDef(size=12))
        .encode(
            x=alt.X("Data/hora:T", title="Horário de Manaus"),
            y=alt.Y("Nível (cm):Q", scale=alt.Scale(zero=False)),
            color=alt.Color("Estação:N", legend=alt.Legend(orient="bottom", columns=2)),
            tooltip=["Estação", alt.Tooltip("Data/hora:T", format="%d/%m %H:%M"), "Nível (cm)"],
        )
        .properties(height=360)
        .interactive(),
        width="stretch",
    )
    st.caption("Fonte: ANA — telemetria (ServiceANA). Horário da fonte convertido de UTC−03:00 (inferido).")


def grafico_variacao(analises: dict[str, dict[str, Any]], nomes: dict[str, str]) -> None:
    """Variação projetada em 24 h por estação (barras divergentes)."""
    import altair as alt
    import pandas as pd

    linhas = []
    for codigo, analise in analises.items():
        for estacao in analise.get("estacoes_json") or []:
            if estacao.get("variacao_24h_cm") is None:
                continue
            linhas.append(
                {
                    "Estação": f"{estacao.get('estacao')} — {nomes.get(codigo, codigo)}",
                    "Variação 24 h (cm)": estacao["variacao_24h_cm"],
                    "Sinal": ROTULOS_SINAL.get(estacao.get("sinal"), ""),
                }
            )
    if not linhas:
        return
    tabela = pd.DataFrame(linhas)
    escala = alt.Scale(
        domain=[ROTULOS_SINAL[s] for s in ORDEM_SINAIS],
        range=[HEX_SINAL[s] for s in ORDEM_SINAIS],
    )
    st.altair_chart(
        alt.Chart(tabela, title="Variação do nível projetada em 24 h (− descendo / + subindo)")
        .mark_bar(cornerRadius=3)
        .encode(
            x=alt.X("Variação 24 h (cm):Q"),
            y=alt.Y(
                "Estação:N", sort="x", title=None,
                axis=alt.Axis(labelOverlap=False, labelLimit=260),
            ),
            color=alt.Color("Sinal:N", scale=escala),
            tooltip=["Estação", "Variação 24 h (cm)", "Sinal"],
        )
        .properties(height=max(160, 46 * len(linhas))),
        width="stretch",
    )
