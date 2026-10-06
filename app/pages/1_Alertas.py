"""Compatibilidade da página antiga com a revisão autenticada de alertas."""

from __future__ import annotations

import streamlit as st

from app.paineis import renderizar_alertas

st.set_page_config(page_title="Revisão de alertas | CIDC", page_icon="🚨", layout="wide")
renderizar_alertas()
