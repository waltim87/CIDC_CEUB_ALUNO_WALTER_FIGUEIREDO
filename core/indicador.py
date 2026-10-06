"""Indicador de resultado: tempo entre a leitura da fonte e a emissão do alerta.

Meta do projeto: reduzir a média de (emitido_em - data_hora_leitura) de 30 para
10 minutos. A meta é uma hipótese de projeto, sem validação oficial.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median
from typing import Any, Iterable, Mapping

META_MINUTOS = 10.0
LINHA_BASE_MINUTOS = 30.0


def _como_datetime(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, str) and valor.strip():
        try:
            resultado = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if resultado.tzinfo is None:
        resultado = resultado.replace(tzinfo=timezone.utc)
    return resultado.astimezone(timezone.utc)


def minutos_leitura_emissao(alerta: Mapping[str, Any]) -> float | None:
    """Minutos entre a leitura de referência e a emissão; None se não verificável."""
    indice = alerta.get("indices")
    if isinstance(indice, list):
        indice = indice[0] if indice else None
    leitura = _como_datetime(
        (indice or {}).get("data_hora_leitura_referencia")
        if isinstance(indice, Mapping)
        else alerta.get("data_hora_leitura_referencia")
    )
    emissao = _como_datetime(alerta.get("emitido_em"))
    if leitura is None or emissao is None:
        return None
    minutos = (emissao - leitura).total_seconds() / 60
    # Emissão anterior à leitura indica dado inconsistente, não latência negativa.
    return minutos if minutos >= 0 else None


def calcular_indicador(alertas: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Resume a latência leitura→emissão apenas com alertas verificáveis."""
    lista = list(alertas)
    medidas = [
        minutos
        for minutos in (minutos_leitura_emissao(alerta) for alerta in lista)
        if minutos is not None
    ]
    resumo: dict[str, Any] = {
        "alertas_considerados": len(lista),
        "alertas_medidos": len(medidas),
        "alertas_sem_dados": len(lista) - len(medidas),
        "media_minutos": None,
        "mediana_minutos": None,
        "maximo_minutos": None,
        "meta_minutos": META_MINUTOS,
        "linha_base_minutos": LINHA_BASE_MINUTOS,
        "meta_atingida": None,
    }
    if medidas:
        resumo["media_minutos"] = round(mean(medidas), 1)
        resumo["mediana_minutos"] = round(median(medidas), 1)
        resumo["maximo_minutos"] = round(max(medidas), 1)
        resumo["meta_atingida"] = resumo["media_minutos"] <= META_MINUTOS
    return resumo


def ler_alertas_emitidos(cliente: Any, *, limite: int = 1000) -> list[dict[str, Any]]:
    """Alertas com emissão registrada e a leitura de referência do índice."""
    resultado = (
        cliente.table("alertas")
        .select("id,municipio_id,classe,emitido_em,indices(data_hora_leitura_referencia)")
        .not_.is_("emitido_em", "null")
        .order("emitido_em", desc=True)
        .limit(limite)
        .execute()
    )
    return resultado.data or []
