"""Execução automática do índice: usa só leituras reais já coletadas.

Só o componente de hidrologia é derivado de dados (nível x cotas da estação).
Os demais ficam nulos e o índice normaliza os pesos restantes. Gera apenas
rascunhos de alerta; o envio continua exigindo aprovação humana.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from core.motor import calcular_e_gerar_rascunhos

LOGGER = logging.getLogger(__name__)
IDADE_MAXIMA_HORAS = 24
# Hipótese inicial, sem validação oficial: fração da cota de alerta em que o score começa a subir.
INICIO_FRACAO_ALERTA = 0.7


def score_hidrologia_estacao(
    nivel_cm: float, cota_alerta: float, cota_emergencia: float
) -> float:
    """0-100: <=70% da cota de alerta = 0; alerta = 50; emergência = 80; acima, até 100."""
    if cota_alerta <= 0:
        raise ValueError("cota_alerta deve ser positiva")
    inicio = cota_alerta * INICIO_FRACAO_ALERTA
    if nivel_cm <= inicio:
        return 0.0
    if nivel_cm < cota_alerta:
        return 50.0 * (nivel_cm - inicio) / (cota_alerta - inicio)
    if cota_emergencia <= cota_alerta:
        return 80.0 if nivel_cm < cota_emergencia else 100.0
    if nivel_cm < cota_emergencia:
        return 50.0 + 30.0 * (nivel_cm - cota_alerta) / (cota_emergencia - cota_alerta)
    excesso = (nivel_cm - cota_emergencia) / cota_emergencia
    return min(100.0, 80.0 + 20.0 * excesso / 0.1)


def _instante(valor: str) -> datetime:
    instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)


def coletar_hidrologia_por_municipio(
    cliente: Any, *, agora: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """Maior score de hidrologia por município, com a proveniência das leituras."""
    agora = agora or datetime.now(timezone.utc)
    limite = agora - timedelta(hours=IDADE_MAXIMA_HORAS)
    estacoes = (
        cliente.table("estacoes")
        .select("id,nome,municipio_id,cota_alerta,cota_emergencia")
        .execute()
        .data
        or []
    )
    por_municipio: dict[str, dict[str, Any]] = {}
    for estacao in estacoes:
        try:
            if not estacao.get("municipio_id") or estacao.get("cota_alerta") is None:
                continue
            leitura = (
                cliente.table("leituras")
                .select("nivel_cm,data_hora_leitura")
                .eq("estacao_id", estacao["id"])
                .order("data_hora_leitura", desc=True)
                .limit(1)
                .execute()
                .data
            )
            if not leitura or leitura[0].get("nivel_cm") is None:
                continue
            if _instante(leitura[0]["data_hora_leitura"]) < limite:
                continue
            cota_emergencia = estacao.get("cota_emergencia")
            score = score_hidrologia_estacao(
                float(leitura[0]["nivel_cm"]),
                float(estacao["cota_alerta"]),
                float(cota_emergencia if cota_emergencia is not None else estacao["cota_alerta"]),
            )
        except Exception:
            LOGGER.exception("Falha ao avaliar a estação %s", estacao.get("id"))
            continue
        atual = por_municipio.setdefault(
            str(estacao["municipio_id"]), {"score": -1.0, "fontes": []}
        )
        atual["score"] = max(atual["score"], score)
        atual["fontes"].append(
            {
                "nome": f"estacao:{estacao.get('nome') or estacao['id']}",
                "data_hora_leitura": leitura[0]["data_hora_leitura"],
            }
        )
    return por_municipio


def executar_motor(cliente: Any, *, agora: datetime | None = None) -> dict[str, Any]:
    """Calcula índice e rascunhos por município; falha de um não afeta os demais."""
    resumo: dict[str, Any] = {"municipios": 0, "alertas": 0, "erros": 0}
    for municipio_id, dados in coletar_hidrologia_por_municipio(cliente, agora=agora).items():
        try:
            resultado = calcular_e_gerar_rascunhos(
                cliente,
                municipio_id,
                {"hidrologia": dados["score"]},
                fontes=dados["fontes"],
            )
            resumo["municipios"] += 1
            resumo["alertas"] += len(resultado["alertas"])
        except Exception:
            LOGGER.exception("Falha no motor para o município %s", municipio_id)
            resumo["erros"] += 1
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    resumo = executar_motor(create_client(url, chave))
    LOGGER.info("Motor: %s", resumo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
