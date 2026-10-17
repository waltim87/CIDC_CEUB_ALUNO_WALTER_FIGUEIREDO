"""Áreas de risco por comunidade (prevenção).

Cadastra pontos críticos com tipo, casas/pessoas expostas, nível, foto e coordenadas.
Somente a coordenação municipal ou a administração podem cadastrar/editar/excluir.
A leitura segue o município do usuário (RLS no banco).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

TIPOS = {
    "inundacao": ("🌊 Inundação / cheia"),
    "terras_caidas": ("🏚️ Terras caídas / desabamento"),
    "erosao": ("🌊 Erosão de margem"),
    "deslizamento": ("⛰️ Deslizamento de terra"),
    "incendio": ("🔥 Incêndio / queimada"),
    "outro": ("❓ Outro"),
}
NIVEIS = {
    "baixo": ("🟢 Baixo", [46, 160, 67]),
    "medio": ("🟡 Médio", [251, 192, 45]),
    "alto": ("🟠 Alto", [239, 108, 0]),
    "critico": ("🔴 Crítico", [198, 40, 40]),
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
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(FUSO_MANHAS).strftime("%d/%m %H:%M") + " (Manaus)"


def renderizar_areas_risco(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("⚠️ Áreas de risco por comunidade")
    st.caption("Cadastro de pontos críticos para prevenção: inundação, terras caídas, erosão, "
               "deslizamento, incêndio e outro. Cada área tem nível, número de casas/pessoas e localização.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "areas_risco")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    try:
        linhas = (cliente.table("areas_risco_comunidade")
                  .select("id,municipio_id,comunidade_id,nome,tipo,nivel,casas,pessoas,descricao,"
                          "latitude,longitude,caminho_foto,registrado_por,registrado_em,atualizado_em")
                  .eq("municipio_id", municipio_id)
                  .order("registrado_em", desc=True)
                  .limit(2000)
                  .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar as áreas de risco (aplique a migration 202610140017): {erro}")
        return

    pode_gerenciar = perfil["perfil"] in {"coordenador_municipal", "administrador"} and perfil.get("municipio_id") == municipio_id

    # ---------- KPIs ----------
    total_casas = 0
    total_pessoas = 0
    com_coordenadas = 0
    for a in linhas:
        total_casas += a.get("casas") or 0
        total_pessoas += a.get("pessoas") or 0
        if a.get("latitude") is not None and a.get("longitude") is not None:
            com_coordenadas += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Áreas cadastradas", len(linhas))
    c2.metric("Com coordenadas", com_coordenadas)
    c3.metric("Casas expostas", _numero(total_casas))
    c4.metric("Pessoas expostas", _numero(total_pessoas))

    # ---------- Mapa ----------
    import pydeck as pdk

    pontos = []
    for a in linhas:
        if a.get("latitude") is None or a.get("longitude") is None:
            continue
        nivel = a.get("nivel", "baixo")
        cor = NIVEIS[nivel][1] + [200]
        pontos.append({
            "lat": a["latitude"], "lon": a["longitude"],
            "nome": a["nome"],
            "tipo": TIPOS[a["tipo"]][0].split(" ", 1)[1] if " " in TIPOS[a["tipo"]][0] else TIPOS[a["tipo"]][0],
            "nivel": NIVEIS[nivel][0],
            "casas": a.get("casas") or 0,
            "pessoas": a.get("pessoas") or 0,
            "cor": cor,
            "detalhe": f"{a['nome']} · {TIPOS[a['tipo']][0]} · {NIVEIS[nivel][0]} · "
                       f"{a.get('casas') or 0} casa(s), {a.get('pessoas') or 0} pessoa(s)",
        })

    if pontos:
        st.pydeck_chart(
            pdk.Deck(
                layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]",
                                  get_fill_color="cor", get_radius=3000, radius_min_pixels=5,
                                  stroked=True, get_line_color=[255, 255, 255],
                                  line_width_min_pixels=1, pickable=True)],
                initial_view_state=pdk.ViewState(
                    latitude=float(pontos[0]["lat"]), longitude=float(pontos[0]["lon"]), zoom=11),
                map_provider="carto", map_style="light",
                tooltip={"html": "<b>{nome}</b><br/>{tipo} · {nivel}<br/>{casas} casa(s), {pessoas} pessoa(s)"},
            ),
            height=420,
        )
        st.caption("Cor = nível de risco (verde = baixo, amarelo = médio, laranja = alto, vermelho = crítico). "
                   "Mapa © OpenStreetMap / CARTO.")
    else:
        st.info("Nenhuma área com coordenadas cadastrada ainda.")

    # ---------- Cadastro / edição ----------
    st.subheader("Cadastrar ou editar área de risco")

    if pode_gerenciar:
        with st.form("form_area_risco", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome / local da área", max_chars=200,
                                 placeholder="Ex.: beira do rio, comunidade São Raimundo")
            tipo = c2.selectbox("Tipo de risco", list(TIPOS),
                                format_func=lambda t: TIPOS[t][0])
            c1, c2 = st.columns(2)
            nivel = c1.selectbox("Nível de risco", list(NIVEIS),
                                 format_func=lambda n: NIVEIS[n][0])
            casas = c2.number_input("Número de casas", min_value=0, step=1, value=0)
            c1, c2 = st.columns(2)
            pessoas = c1.number_input("Número de pessoas", min_value=0, step=1, value=0)
            descricao = st.text_area("Descrição (referência local, histórico)", max_chars=1000,
                                     placeholder="Ex.: alaga em cheias acima de 15 m; atinge 12 famílias")
            c1, c2 = st.columns(2)
            latitude = c1.number_input("Latitude", value=None, format="%.6f",
                                       min_value=-90.0, max_value=90.0, step=0.000001)
            longitude = c2.number_input("Longitude", value=None, format="%.6f",
                                        min_value=-180.0, max_value=180.0, step=0.000001)
            caminho_foto = st.text_input("Caminho da foto (opcional)", max_chars=500,
                                         placeholder="Ex.: fotos-risco/labrea/comunidade_sao_raimundo.jpg")
            if st.form_submit_button("Salvar área de risco", type="primary"):
                if len(nome.strip()) < 3:
                    st.error("Informe o nome da área (mínimo 3 caracteres).")
                elif latitude is None or longitude is None:
                    st.error("Informe a latitude e a longitude.")
                else:
                    try:
                        cliente.rpc("cidc_area_risco_cadastrar", {
                            "p_municipio_id": municipio_id,
                            "p_nome": nome.strip(),
                            "p_tipo": tipo,
                            "p_nivel": nivel,
                            "p_casas": int(casas) or None,
                            "p_pessoas": int(pessoas) or None,
                            "p_descricao": descricao.strip() or None,
                            "p_latitude": latitude,
                            "p_longitude": longitude,
                            "p_caminho_foto": caminho_foto.strip() or None,
                        }).execute()
                        st.success("Área de risco salva com sucesso.")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Não foi possível salvar: {erro}")
    else:
        st.info("Cadastro e edição de áreas de risco estão disponíveis para a coordenação municipal e a administração.")

    # ---------- Lista ----------
    st.subheader("Áreas de risco cadastradas")
    if not linhas:
        st.success("Nenhuma área de risco cadastrada neste município ainda.")
    else:
        linhas_tabela = [
            {
                "Área": a["nome"],
                "Tipo": TIPOS[a["tipo"]][0],
                "Nível": NIVEIS[a["nivel"]][0],
                "Casas": _numero(a.get("casas")),
                "Pessoas": _numero(a.get("pessoas")),
                "Local": (f"{a['latitude']:.5f}, {a['longitude']:.5f}"
                          if a.get("latitude") is not None and a.get("longitude") is not None else "sem coordenadas"),
                "Cadastrado em": _hora_local(a.get("registrado_em")),
            }
            for a in linhas
        ]
        st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Relatório ----------
    painel_relatorio(
        "Áreas de risco por comunidade",
        [("Áreas cadastradas", [
            {"Área": a["nome"], "Tipo": TIPOS[a["tipo"]][0], "Nível": NIVEIS[a["nivel"]][0],
             "Casas": a.get("casas"), "Pessoas": a.get("pessoas"),
             "Latitude": a.get("latitude"), "Longitude": a.get("longitude"),
             "Descrição": a.get("descricao") or "",
             "Cadastrado em": _hora_local(a.get("registrado_em"))}
            for a in linhas
        ])],
        subtitulo=nome_municipio,
        resumo={"Áreas cadastradas": len(linhas), "Com coordenadas": com_coordenadas,
                "Casas expostas": total_casas, "Pessoas expostas": total_pessoas},
    )
