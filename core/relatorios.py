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
    limite = max(int(largura / 1.7), 6)
    pdf.set_font("Helvetica", "B", 8)
    for coluna in colunas:
        pdf.cell(largura, 6, _latin1(coluna)[:limite], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for linha in linhas:
        for coluna in colunas:
            valor = linha.get(coluna)
            pdf.cell(largura, 6, _latin1(valor)[:limite], border=1)
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


COLUNAS_DETALHADAS = [
    "Município", "UF", "Código IBGE", "Calha", "População",
    "Classe", "Índice", "Maior componente", "Hidrologia", "População exposta",
    "Infraestrutura", "Logística", "Vulnerabilidade", "Hora leitura (UTC)", "Fontes",
    "Situação oficial", "Data situação oficial",
    "Último alerta", "Alertas (total)", "Alertas enviados",
    "Comunidades", "Pop. em comunidades",
    "Famílias afetadas", "Pessoas afetadas",
    "Estações", "Última leitura (UTC)", "Nível último (cm)", "Chuva última (mm)",
    "Focos de calor",
    "Unidades de saúde", "Escolas", "Outra infraestrutura",
    "Abrigos", "Capacidade abrigos", "Ocupação abrigos", "Ocupação (%)",
    "Água", "Alimento", "Medicamento", "Oxigênio", "Combustível", "Purificador",
    "Tarefas (total)", "Tarefas pendentes", "Tarefas concluídas",
]
COLUNAS_PDF_DETALHADO = [
    "Município", "UF", "População", "Classe", "Índice", "Situação oficial",
    "Comunidades", "Pessoas afetadas", "Focos de calor", "Ocupação (%)",
    "Tarefas pendentes",
]
_COMPONENTES = {
    "Hidrologia": "score_hidrologia",
    "População exposta": "score_populacao",
    "Infraestrutura": "score_infra",
    "Logística": "score_logistica",
    "Vulnerabilidade": "score_vulnerabilidade",
}
_RECURSOS = {
    "agua": "Água", "alimento": "Alimento", "medicamento": "Medicamento",
    "oxigenio": "Oxigênio", "combustivel": "Combustível", "purificador": "Purificador",
}
_CONSULTAS = {
    "municipios": ("municipios", "id_ibge,calha,populacao", None),
    "comunidades": ("comunidades", "id,municipio_id,populacao_estimada", None),
    "estacoes": ("estacoes", "id,municipio_id", None),
    "leituras": ("leituras", "estacao_id,data_hora_leitura,nivel_cm,chuva_mm", "data_hora_leitura"),
    "focos": ("focos_calor", "municipio_id", None),
    "infra": ("infraestrutura", "tipo,municipio_id", None),
    "situacao": ("situacao_municipal", "municipio_id,data,situacao", "data"),
    "recursos": ("recursos", "municipio_id,tipo,quantidade", None),
    "abrigos": ("abrigos", "municipio_id,capacidade,ocupacao", None),
    "afetados": ("pessoas_afetadas", "comunidade_id,familias,pessoas,data", "data"),
    "acoes": ("acoes", "alerta_id,status", None),
    "alertas": ("alertas", "id,municipio_id,status", "criado_em"),
}


def carregar_dados_relatorio(cliente: Any) -> tuple[dict[str, list], list[str]]:
    """Lê as tabelas de apoio; cada uma falha de forma isolada (lista vazia + aviso)."""
    dados: dict[str, list] = {}
    avisos: list[str] = []
    for chave, (tabela, colunas, ordem) in _CONSULTAS.items():
        try:
            consulta = cliente.table(tabela).select(colunas)
            if ordem:
                consulta = consulta.order(ordem, desc=True)
            dados[chave] = consulta.limit(5000).execute().data or []
        except Exception as erro:  # noqa: BLE001 - uma tabela não derruba o relatório
            dados[chave] = []
            avisos.append(f"{tabela}: {erro}")
    return dados, avisos


def _por_municipio(linhas: Sequence[Mapping[str, Any]]) -> dict[str, list]:
    agrupado: dict[str, list] = {}
    for linha in linhas:
        if linha.get("municipio_id"):
            agrupado.setdefault(str(linha["municipio_id"]).strip(), []).append(linha)
    return agrupado


def _numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def detalhar_situacao(
    linhas: Sequence[Mapping[str, Any]],
    indices: Sequence[Mapping[str, Any]],
    alertas: Sequence[Mapping[str, Any]],
    dados: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Acrescenta a cada linha dados de população, campo, infraestrutura e tarefas.

    Valores ausentes ficam vazios (None); contagens sem registro valem 0.
    """
    ultimo_indice: dict[str, Mapping[str, Any]] = {}
    for indice in indices:
        ultimo_indice.setdefault(str(indice["municipio_id"]).strip(), indice)
    info_municipio = {str(m["id_ibge"]).strip(): m for m in dados.get("municipios", [])}
    comunidades = _por_municipio(dados.get("comunidades", []))
    estacoes = _por_municipio(dados.get("estacoes", []))
    focos = _por_municipio(dados.get("focos", []))
    infra = _por_municipio(dados.get("infra", []))
    abrigos = _por_municipio(dados.get("abrigos", []))
    recursos = _por_municipio(dados.get("recursos", []))
    alertas_mun = _por_municipio(alertas)
    situacao: dict[str, Mapping[str, Any]] = {}
    for registro in dados.get("situacao", []):  # mais recente primeiro
        situacao.setdefault(str(registro["municipio_id"]).strip(), registro)

    estacao_para_municipio = {
        str(e["id"]): cod for cod, lista in estacoes.items() for e in lista
    }
    ultima_leitura: dict[str, Mapping[str, Any]] = {}
    for leitura in dados.get("leituras", []):  # mais recente primeiro
        cod = estacao_para_municipio.get(str(leitura.get("estacao_id")))
        if cod:
            ultima_leitura.setdefault(cod, leitura)

    comunidade_para_municipio = {
        str(c["id"]): cod for cod, lista in comunidades.items() for c in lista
    }
    familias: dict[str, int] = {}
    pessoas: dict[str, int] = {}
    for registro in dados.get("afetados", []):
        cod = comunidade_para_municipio.get(str(registro.get("comunidade_id")))
        if cod:
            familias[cod] = familias.get(cod, 0) + int(_numero(registro.get("familias")))
            pessoas[cod] = pessoas.get(cod, 0) + int(_numero(registro.get("pessoas")))

    alerta_para_municipio = {
        str(a["id"]): str(a["municipio_id"]).strip() for a in alertas if a.get("id")
    }
    tarefas: dict[str, list[str]] = {}
    for acao in dados.get("acoes", []):
        cod = alerta_para_municipio.get(str(acao.get("alerta_id")))
        if cod:
            tarefas.setdefault(cod, []).append(str(acao.get("status")))

    resultado = []
    for linha in linhas:
        cod = str(linha["Código IBGE"])
        novo = dict(linha)
        info = info_municipio.get(cod, {})
        indice = ultimo_indice.get(cod)
        novo["Calha"] = info.get("calha")
        novo["População"] = info.get("populacao")
        maior = None
        for rotulo, campo in _COMPONENTES.items():
            valor = indice.get(campo) if indice else None
            novo[rotulo] = valor
            if valor is not None and (maior is None or valor > maior[1]):
                maior = (rotulo, valor)
        novo["Maior componente"] = maior[0] if maior else None
        sit = situacao.get(cod)
        novo["Situação oficial"] = sit["situacao"] if sit else "Não informada"
        novo["Data situação oficial"] = sit["data"] if sit else None
        lista_alertas = alertas_mun.get(cod, [])
        novo["Alertas (total)"] = len(lista_alertas)
        novo["Alertas enviados"] = sum(a.get("status") == "enviado" for a in lista_alertas)
        lista_com = comunidades.get(cod, [])
        novo["Comunidades"] = len(lista_com)
        novo["Pop. em comunidades"] = int(
            sum(_numero(c.get("populacao_estimada")) for c in lista_com)
        )
        novo["Famílias afetadas"] = familias.get(cod, 0)
        novo["Pessoas afetadas"] = pessoas.get(cod, 0)
        novo["Estações"] = len(estacoes.get(cod, []))
        leitura = ultima_leitura.get(cod)
        novo["Última leitura (UTC)"] = leitura["data_hora_leitura"] if leitura else None
        novo["Nível último (cm)"] = leitura.get("nivel_cm") if leitura else None
        novo["Chuva última (mm)"] = leitura.get("chuva_mm") if leitura else None
        novo["Focos de calor"] = len(focos.get(cod, []))
        tipos = [i.get("tipo") for i in infra.get(cod, [])]
        novo["Unidades de saúde"] = tipos.count("ubs")
        novo["Escolas"] = tipos.count("escola")
        novo["Outra infraestrutura"] = len(tipos) - tipos.count("ubs") - tipos.count("escola")
        lista_abrigos = abrigos.get(cod, [])
        capacidade = int(sum(_numero(a.get("capacidade")) for a in lista_abrigos))
        ocupacao = int(sum(_numero(a.get("ocupacao")) for a in lista_abrigos))
        novo["Abrigos"] = len(lista_abrigos)
        novo["Capacidade abrigos"] = capacidade
        novo["Ocupação abrigos"] = ocupacao
        novo["Ocupação (%)"] = round(100 * ocupacao / capacidade, 1) if capacidade else None
        for tipo, rotulo in _RECURSOS.items():
            novo[rotulo] = sum(
                _numero(r.get("quantidade")) for r in recursos.get(cod, []) if r.get("tipo") == tipo
            )
        status = tarefas.get(cod, [])
        novo["Tarefas (total)"] = len(status)
        novo["Tarefas pendentes"] = sum(s in ("pendente", "em_andamento") for s in status)
        novo["Tarefas concluídas"] = sum(s == "concluida" for s in status)
        resultado.append(novo)
    return resultado


def totais_detalhados(linhas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Totais para o resumo do relatório (somas simples das linhas)."""
    def soma(coluna: str) -> int:
        return int(sum(_numero(linha.get(coluna)) for linha in linhas))

    capacidade = soma("Capacidade abrigos")
    return {
        "População total dos municípios": soma("População"),
        "Comunidades cadastradas": soma("Comunidades"),
        "Pessoas afetadas registradas": soma("Pessoas afetadas"),
        "Famílias afetadas registradas": soma("Famílias afetadas"),
        "Estações monitoradas": soma("Estações"),
        "Focos de calor registrados": soma("Focos de calor"),
        "Unidades de saúde cadastradas": soma("Unidades de saúde"),
        "Escolas cadastradas": soma("Escolas"),
        "Abrigos": soma("Abrigos"),
        "Ocupação dos abrigos (%)": (
            round(100 * soma("Ocupação abrigos") / capacidade, 1) if capacidade else None
        ),
        "Alertas emitidos": soma("Alertas enviados"),
        "Tarefas pendentes": soma("Tarefas pendentes"),
        "Municípios com situação oficial informada": sum(
            linha.get("Situação oficial") != "Não informada" for linha in linhas
        ),
    }