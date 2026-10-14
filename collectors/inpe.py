"""INPE Queimadas: focos de calor do Amazonas (CSV diário oficial, sem chave).

``python -m collectors.inpe`` (GitHub Actions, a cada 3 h) baixa os arquivos diários de
ontem e de hoje (https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/),
guarda os focos do AM com risco de fogo, dias sem chuva e intensidade (FRP) e mantém só
os últimos DIAS_RETIDOS dias. Cada satélite detecta o mesmo fogo várias vezes: as contagens
são de detecções, não de incêndios distintos.
"""

from __future__ import annotations

import csv
import io
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from collectors.comum import cliente_servico, coletar_configurado, carregar_configuracao, registrar_saude

LOGGER = logging.getLogger(__name__)
URL_DIARIO = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_{data}.csv"
NOME_FONTE = "INPE Queimadas"
DIAS_RETIDOS = 30
UF_AM = "13"


def coletar(configuracao: dict[str, Any] | None = None, *, sessao: Any = requests) -> list[dict[str, Any]]:
    """Adaptador genérico configurável (mantido por compatibilidade com config/fontes.yaml)."""
    return coletar_configurado("inpe", configuracao or carregar_configuracao("inpe"), sessao=sessao)


def _numero(valor: Any) -> float | None:
    try:
        numero = float(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return None if numero in (-999, -999.0) else numero


def focos_do_csv(texto: str) -> list[dict[str, Any]]:
    linhas = []
    for r in csv.DictReader(io.StringIO(texto)):
        municipio_id = str(r.get("municipio_id") or "").strip()
        if str(r.get("estado_id") or "").strip() != UF_AM and not municipio_id.startswith(UF_AM):
            continue
        lat, lon = _numero(r.get("lat")), _numero(r.get("lon"))
        if lat is None or lon is None or not r.get("id"):
            continue
        dias = _numero(r.get("numero_dias_sem_chuva"))
        linhas.append({
            "id_inpe": r["id"].strip(),
            "data_hora": r["data_hora_gmt"].strip().replace(" ", "T") + "+00:00",
            "lat": lat, "lon": lon,
            "municipio_id": municipio_id if len(municipio_id) == 7 else None,
            "satelite": (r.get("satelite") or "").strip() or None,
            "risco_fogo": _numero(r.get("risco_fogo")),
            "dias_sem_chuva": int(dias) if dias is not None else None,
            "precipitacao": _numero(r.get("precipitacao")),
            "frp": _numero(r.get("frp")),
            "geom": f"SRID=4326;POINT({lon} {lat})",
        })
    return linhas


def coletar_e_gravar(cliente: Any, *, sessao: Any = requests, agora: datetime | None = None) -> int:
    agora = agora or datetime.now(timezone.utc)
    municipios = {str(m["id_ibge"]).strip() for m in cliente.table("municipios").select("id_ibge").execute().data or []}
    focos: list[dict[str, Any]] = []
    for dia in (agora - timedelta(days=1), agora):
        resposta = sessao.get(URL_DIARIO.format(data=dia.strftime("%Y%m%d")), timeout=180)
        if resposta.status_code == 404:  # arquivo do dia ainda não publicado
            continue
        resposta.raise_for_status()
        resposta.encoding = "utf-8"
        focos.extend(focos_do_csv(resposta.text))
    for foco in focos:
        if foco["municipio_id"] not in municipios:
            foco["municipio_id"] = None
    unicos = list({f["id_inpe"]: f for f in focos}.values())
    for inicio in range(0, len(unicos), 500):
        cliente.table("focos_calor").upsert(unicos[inicio:inicio + 500], on_conflict="id_inpe").execute()
    corte = (agora - timedelta(days=DIAS_RETIDOS)).isoformat()
    cliente.table("focos_calor").delete().lt("data_hora", corte).execute()
    return len(unicos)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cliente = cliente_servico()
    try:
        total = coletar_e_gravar(cliente)
        LOGGER.info("INPE: %s focos no AM (ontem e hoje)", total)
        registrar_saude(cliente, NOME_FONTE, registros=total)
    except Exception as erro:
        LOGGER.exception("Coleta do INPE falhou")
        registrar_saude(cliente, NOME_FONTE, registros=0, erro=f"{type(erro).__name__}: {erro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
