"""Compatibilidade da página antiga com a revisão autenticada de alertas."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.paineis import renderizar_alertas

st.set_page_config(page_title="Revisão de alertas | CIDC", page_icon="🚨", layout="wide")
renderizar_alertas()
