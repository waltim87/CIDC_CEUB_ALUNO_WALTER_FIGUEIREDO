"""SGB/SACE: situação oficial dos pontos de alerta hidrológico da bacia do Amazonas.

``python -m collectors.sgb`` (GitHub Actions, a cada 3 h) lê o mapa de estações do SACE
(https://sace.sgb.gov.br/estacoes_mapa.php?bacia=amazonas): coordenadas e nome de cada
ponto; depois abre o relatório de cada ponto para obter cota atual, horário da medição e
a SITUAÇÃO oficial (Normal, Atenção, Alerta, Inundação...). Associa o ponto à sede de
município mais próxima (até RAIO_KM). O SACE não publica os valores numéricos das cotas
de alerta em formato aberto; a situação oficial é usada diretamente.
"""

from __future__ import annotations

import logging
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from collectors.comum import cliente_servico, coletar_configurado, carregar_configuracao, registrar_saude

LOGGER = logging.getLogger(__name__)
BASE = "https://sace.sgb.gov.br/"
NOME_FONTE = "SGB SACE"
RAIO_KM = 60
CABECALHO = {"User-Agent": "CIDC-prototipo/1.0"}
FUSO_SACE = timezone(timedelta(hours=-4))  # horário de Manaus nos relatórios (inferido)

_MARCADOR = re.compile(
    r"relatorio\.php\?apenas_grafico=sim&(bacia=amazonas&pm=(\d+)&s=\d*&sr=\d*)\"[^`]*?`;.*?"
    r"L\.circleMarker\(\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\],\s*\{[^}]*?fillColor:\s*\"(#[0-9A-Fa-f]{6})\"[^}]*\}\)"
    r".*?bindTooltip\(\"([^\"]+)\"",
    re.S,
)
_COTA = re.compile(r"<h2[^>]*>\s*([\d.,]+)\s*Cota \(cm\)\s*</h2>", re.S)
_MEDICAO = re.compile(r"Última medição:\s*<b>\s*([\d/]+\s+[\d:]+)\s*</b>", re.S)
_SITUACAO = re.compile(r"Situação:\s*<span[^>]*></span>\s*([^<]+?)\s*<br", re.S)


def coletar(configuracao: dict[str, Any] | None = None, *, sessao: Any = requests) -> list[dict[str, Any]]:
    """Adaptador genérico configurável (mantido por compatibilidade com config/fontes.yaml)."""
    return coletar_configurado("sgb", configuracao or carregar_configuracao("sgb"), sessao=sessao)


def pontos_do_mapa(html: str) -> list[dict[str, Any]]:
    pontos: dict[int, dict[str, Any]] = {}
    for consulta, pm, lat, lon, cor, nome in _MARCADOR.findall(html):
        pontos[int(pm)] = {"pm": int(pm), "latitude": float(lat), "longitude": float(lon), "cor": cor,
                           "nome": nome.split(" - ", 1)[-1].strip(), "link": f"{BASE}relatorio.php?{consulta}"}
    return list(pontos.values())


def dados_do_relatorio(html: str) -> dict[str, Any]:
    cota = _COTA.search(html)
    medicao = _MEDICAO.search(html)
    situacao = _SITUACAO.search(html)
    medido_em = None
    if medicao:
        try:
            medido_em = datetime.strptime(medicao.group(1).strip(), "%d/%m/%Y %H:%M").replace(tzinfo=FUSO_SACE).isoformat()
        except ValueError:
            medido_em = None
    return {
        "cota_cm": float(cota.group(1).replace(".", "").replace(",", ".")) if cota else None,
        "medido_em": medido_em,
        "situacao": situacao.group(1).strip() if situacao else None,
    }


def _distancia_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def municipio_mais_proximo(ponto: dict[str, Any], municipios: list[dict[str, Any]]) -> str | None:
    candidatos = [
        (_distancia_km((ponto["latitude"], ponto["longitude"]), (m["latitude"], m["longitude"])), str(m["id_ibge"]).strip())
        for m in municipios if m.get("latitude") is not None
    ]
    if not candidatos:
        return None
    distancia, codigo = min(candidatos)
    return codigo if distancia <= RAIO_KM else None


def coletar_e_gravar(cliente: Any, *, sessao: Any = requests, pausa: float = 0.5) -> int:
    municipios = cliente.table("municipios").select("id_ibge,latitude,longitude").execute().data or []
    mapa = sessao.get(BASE + "estacoes_mapa.php?bacia=amazonas", timeout=60, headers=CABECALHO)
    mapa.raise_for_status()
    mapa.encoding = "utf-8"
    pontos = pontos_do_mapa(mapa.text)
    if not pontos:
        raise RuntimeError("Nenhum ponto encontrado no mapa do SACE (o layout da página mudou?)")
    linhas = []
    for ponto in pontos:
        link = ponto["link"]
        try:
            relatorio = sessao.get(link, timeout=60, headers=CABECALHO)
            relatorio.raise_for_status()
            relatorio.encoding = "utf-8"
            ponto.update(dados_do_relatorio(relatorio.text))
        except Exception as erro:
            LOGGER.warning("Relatório SACE do ponto %s indisponível (%s)", ponto["pm"], type(erro).__name__)
        ponto.update(link=link, municipio_id=municipio_mais_proximo(ponto, municipios),
                     atualizado_em=datetime.now(timezone.utc).isoformat())
        linhas.append(ponto)
        if pausa:
            time.sleep(pausa)
    cliente.table("sace_pontos").upsert(linhas, on_conflict="pm").execute()
    return len(linhas)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cliente = cliente_servico()
    try:
        total = coletar_e_gravar(cliente)
        LOGGER.info("SACE: %s pontos da bacia do Amazonas", total)
        registrar_saude(cliente, NOME_FONTE, registros=total)
    except Exception as erro:
        LOGGER.exception("Coleta do SACE falhou")
        registrar_saude(cliente, NOME_FONTE, registros=0, erro=f"{type(erro).__name__}: {erro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
