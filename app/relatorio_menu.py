"""Gerador de relatório de cada menu: PDF com todas as seções e CSV por tabela."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Sequence

import streamlit as st

from core.relatorios import gerar_csv, gerar_pdf_secoes


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def painel_relatorio(
    titulo: str,
    secoes: Sequence[tuple[str, Sequence[dict[str, Any]]]],
    *,
    subtitulo: str | None = None,
    resumo: dict[str, Any] | None = None,
) -> None:
    """Expander com o PDF do menu e um CSV por seção (abre no Excel, separador ;)."""
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    base = _slug(f"{titulo} {subtitulo or ''}")[:60]
    with st.expander("📄 Gerar relatório deste menu", expanded=False):
        total = sum(len(linhas) for _, linhas in secoes)
        st.caption(f"{len(secoes)} seção(ões), {total} registro(s), com os dados exibidos nesta tela.")
        try:
            st.download_button(
                "Baixar PDF completo",
                gerar_pdf_secoes(titulo, secoes, subtitulo=subtitulo, resumo=resumo),
                file_name=f"{base}_{carimbo}.pdf",
                mime="application/pdf",
                key=f"pdf-{base}",
                type="primary",
            )
        except Exception as erro:
            st.warning(f"PDF indisponível: {erro}")
        colunas = st.columns(min(max(len(secoes), 1), 4))
        for posicao, (nome, linhas) in enumerate(secoes):
            if not linhas:
                continue
            colunas[posicao % len(colunas)].download_button(
                f"CSV — {nome}",
                gerar_csv(linhas, list(linhas[0].keys())),
                file_name=f"{base}_{_slug(nome)}_{carimbo}.csv",
                mime="text/csv",
                key=f"csv-{base}-{_slug(nome)}",
            )
