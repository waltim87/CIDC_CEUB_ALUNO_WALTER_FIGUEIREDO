"""Painel principal de situação e tendência municipal."""

from __future__ import annotations

import streamlit as st

from app.comum import (
    carregar_municipios,
    carregar_pesos,
    cliente_supabase,
    mostrar_aviso,
)
from core.alertas import formatar_fontes
from core.indice import ler_indices

st.set_page_config(page_title="Painel principal | CIDC", page_icon="🌧️", layout="wide")
st.title("Centro de Inteligência da Defesa Civil")
st.caption("Painel principal — situação municipal e tendências")
mostrar_aviso()
st.info(
    "Fase 3: índice e rascunhos de alerta. Os alertas não são enviados automaticamente; "
    "a aprovação humana é obrigatória."
)

try:
    cliente = cliente_supabase()
    pesos, validacao_oficial = carregar_pesos(cliente)
    municipios = carregar_municipios(cliente)
    indices = ler_indices(cliente)
except Exception as erro:
    st.error(f"Não foi possível carregar o painel: {erro}")
    st.stop()

st.subheader("Hipótese de pesos do índice")
st.caption(
    "Pesos configuráveis persistidos no Supabase. "
    + ("Validação oficial registrada." if validacao_oficial else "Pesos ainda sem validação oficial.")
)
st.dataframe(
    [
        {"Componente": nome.replace("_", " ").title(), "Peso (%)": peso}
        for nome, peso in pesos.items()
    ],
    hide_index=True,
    use_container_width=True,
)

if not indices:
    st.info(
        "Ainda não há índices calculados com evidências. O painel não cria valores "
        "de demonstração nem interpreta ausência de leituras como risco zero."
    )
    st.stop()

linhas = []
for indice in indices:
    municipio = municipios.get(indice["municipio_id"].strip(), {})
    linhas.append(
        {
            "Município": municipio.get("nome", indice["municipio_id"]),
            "UF": municipio.get("uf", ""),
            "Classe": indice["classe"],
            "Índice": indice["score_total"],
            "Data/hora do índice (UTC)": indice["data_hora"],
            "Data/hora da leitura de referência (UTC)": indice.get(
                "data_hora_leitura_referencia"
            ),
            "Fontes e leituras": formatar_fontes(indice.get("fontes_json")),
        }
    )

st.subheader("Índices mais recentes")
st.dataframe(linhas, hide_index=True, use_container_width=True)

selecionado = st.selectbox(
    "Ver explicação do índice",
    range(len(indices)),
    format_func=lambda pos: (
        f"{municipios.get(indices[pos]['municipio_id'].strip(), {}).get('nome', indices[pos]['municipio_id'])} — "
        f"{indices[pos]['classe']} ({indices[pos]['score_total']})"
    ),
)
indice = indices[selecionado]
municipio = municipios.get(indice["municipio_id"].strip(), {})
st.subheader(
    f"Explicação: {municipio.get('nome', indice['municipio_id'])}/"
    f"{municipio.get('uf', '')}"
)
st.caption(
    f"Fontes e leituras: {formatar_fontes(indice.get('fontes_json'))} · "
    f"Leitura de referência: {indice.get('data_hora_leitura_referencia') or 'não informada'} · "
    f"Índice calculado: {indice['data_hora']}"
)
st.dataframe(
    indice.get("explicacao_json", []),
    hide_index=True,
    use_container_width=True,
)
