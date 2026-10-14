"""Cemaden: pluviômetros do Amazonas (JSON aberto do mapa interativo, sem chave).

``python -m collectors.cemaden`` (GitHub Actions, a cada 3 h) grava a última leitura e
os acumulados de 1 h a 96 h de cada pluviômetro do AM
(https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=AM).
Horário informado pelo Cemaden tratado como UTC (inferido; confirmar com o Cemaden).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from collectors.comum import cliente_servico, coletar_configurado, carregar_configuracao, registrar_saude

LOGGER = logging.getLogger(__name__)
URL = "https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=AM"
NOME_FONTE = "Cemaden PED"
ACUMULADOS = {"acc1hr": "acc1h_mm", "acc3hr": "acc3h_mm", "acc6hr": "acc6h_mm", "acc12hr": "acc12h_mm",
              "acc24hr": "acc24h_mm", "acc48hr": "acc48h_mm", "acc72hr": "acc72h_mm", "acc96hr": "acc96h_mm"}


def coletar(configuracao: dict[str, Any] | None = None, *, sessao: Any = requests) -> list[dict[str, Any]]:
    """Adaptador genérico configurável (mantido por compatibilidade com config/fontes.yaml)."""
    return coletar_configurado("cemaden", configuracao or carregar_configuracao("cemaden"), sessao=sessao)


def _mm(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None  # o Cemaden usa "-" quando não há dado


def _instante(texto: Any) -> str | None:
    try:
        return datetime.strptime(str(texto).strip(), "%d/%m/%y %H:%M").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def estacoes_do_json(dados: list[dict[str, Any]], municipios: set[str]) -> list[dict[str, Any]]:
    linhas = []
    for e in dados:
        if str(e.get("uf")).upper() != "AM" or e.get("idestacao") is None:
            continue
        municipio_id = str(e.get("codibge") or "").strip()
        linha = {
            "id_estacao": int(e["idestacao"]),
            "municipio_id": municipio_id if municipio_id in municipios else None,
            "nome": str(e.get("nomeestacao") or "Sem nome").strip(),
            "ultimo_valor_mm": _mm(e.get("ultimovalor")),
            "medido_em": _instante(e.get("datahoraUltimovalor")),
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        }
        linha.update({destino: _mm(e.get(origem)) for origem, destino in ACUMULADOS.items()})
        linhas.append(linha)
    return linhas


def coletar_e_gravar(cliente: Any, *, sessao: Any = requests) -> int:
    municipios = {str(m["id_ibge"]).strip() for m in cliente.table("municipios").select("id_ibge").execute().data or []}
    resposta = sessao.get(URL, timeout=60, headers={"User-Agent": "CIDC-prototipo/1.0"})
    resposta.raise_for_status()
    linhas = estacoes_do_json(resposta.json(), municipios)
    if linhas:
        cliente.table("chuva_cemaden").upsert(linhas, on_conflict="id_estacao").execute()
    return len(linhas)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cliente = cliente_servico()
    try:
        total = coletar_e_gravar(cliente)
        LOGGER.info("Cemaden: %s pluviômetros do AM", total)
        registrar_saude(cliente, NOME_FONTE, registros=total)
    except Exception as erro:
        LOGGER.exception("Coleta do Cemaden falhou")
        registrar_saude(cliente, NOME_FONTE, registros=0, erro=f"{type(erro).__name__}: {erro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
