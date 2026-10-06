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


COLUNAS_SITUACAO = [
    "Município",
    "UF",
    "Código IBGE",
    "Classe",
    "Índice",
    "Hora leitura (UTC)",
    "Último alerta",
    "Fontes",
]
SEM_INDICE = "Sem índice"


def montar_situacao_municipal(
    municipios: Mapping[str, Mapping[str, Any]],
    indices: Sequence[Mapping[str, Any]],
    alertas: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Uma linha por município: índice mais recente e último alerta.

    `indices` e `alertas` devem vir ordenados do mais recente para o mais antigo.
    Municípios sem índice aparecem como "Sem índice", sem valor inventado.
    """
    ultimo_indice: dict[str, Mapping[str, Any]] = {}
    for indice in indices:
        ultimo_indice.setdefault(str(indice["municipio_id"]).strip(), indice)
    ultimo_alerta: dict[str, Mapping[str, Any]] = {}
    for alerta in alertas:
        ultimo_alerta.setdefault(str(alerta["municipio_id"]).strip(), alerta)

    linhas = []
    for codigo, municipio in municipios.items():
        indice = ultimo_indice.get(codigo)
        alerta = ultimo_alerta.get(codigo)
        fontes = ""
        if indice:
            nomes = [
                str(f.get("nome", f.get("fonte")))
                for f in (indice.get("fontes_json") or [])
                if isinstance(f, Mapping) and (f.get("nome") or f.get("fonte"))
            ]
            fontes = ", ".join(dict.fromkeys(nomes))
        linhas.append(
            {
                "Município": municipio.get("nome", codigo),
                "UF": municipio.get("uf", ""),
                "Código IBGE": codigo,
                "Classe": indice["classe"] if indice else SEM_INDICE,
                "Índice": indice["score_total"] if indice else None,
                "Hora leitura (UTC)": (
                    indice.get("data_hora_leitura_referencia") if indice else None
                ),
                "Último alerta": (
                    f"{alerta['classe']} ({alerta['status']})" if alerta else "Nenhum"
                ),
                "Fontes": fontes,
            }
        )
    linhas.sort(
        key=lambda linha: (
            linha["Índice"] is None,
            -(linha["Índice"] or 0),
            linha["Município"],
        )
    )
    return linhas


def resumo_por_classe(linhas: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Contagem de municípios por classe, incluindo os sem índice."""
    contagem: dict[str, int] = {"Total de municípios": len(linhas)}
    for linha in linhas:
        chave = f"Municípios — {linha['Classe']}"
        contagem[chave] = contagem.get(chave, 0) + 1
    return contagem
