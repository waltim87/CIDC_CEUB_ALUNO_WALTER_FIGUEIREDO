"""Relatórios exportáveis (CSV e PDF) a partir de dados já consultados."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

AVISO = (
    "Protótipo sem validação oficial; confirme nos órgãos oficiais. "
    "Pesos e regras são hipóteses iniciais."
)


def _celula_segura(valor: Any) -> str:
    """Evita injeção de fórmulas ao abrir o CSV em planilhas."""
    texto = "" if valor is None else str(valor)
    if texto[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + texto
    return texto


def gerar_csv(linhas: Sequence[Mapping[str, Any]], colunas: Sequence[str]) -> bytes:
    """CSV UTF-8 com BOM (abre com acentos no Excel) e separador ponto e vírgula."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([_celula_segura(linha.get(coluna)) for coluna in colunas])
    return ("\ufeff" + saida.getvalue()).encode("utf-8")


def _latin1(texto: Any) -> str:
    # A fonte padrão do PDF cobre Latin-1, suficiente para o português.
    return str("" if texto is None else texto).encode("latin-1", "replace").decode("latin-1")


def gerar_pdf(
    titulo: str,
    linhas: Sequence[Mapping[str, Any]],
    colunas: Sequence[str],
    *,
    resumo: Mapping[str, Any] | None = None,
) -> bytes:
    """PDF simples em paisagem: aviso, resumo opcional e tabela."""
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    gerado = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    pdf.cell(0, 5, _latin1(f"Gerado em {gerado}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 4, _latin1(AVISO), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    if resumo:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Resumo", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for chave, valor in resumo.items():
            pdf.cell(
                0, 5, _latin1(f"{chave}: {valor if valor is not None else 'n/d'}"),
                new_x="LMARGIN", new_y="NEXT",
            )
        pdf.ln(2)
    largura = (pdf.w - pdf.l_margin - pdf.r_margin) / max(len(colunas), 1)
    pdf.set_font("Helvetica", "B", 8)
    for coluna in colunas:
        pdf.cell(largura, 6, _latin1(coluna)[:28], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for linha in linhas:
        for coluna in colunas:
            valor = linha.get(coluna)
            pdf.cell(largura, 6, _latin1(valor)[:28], border=1)
        pdf.ln()
    return bytes(pdf.output())
