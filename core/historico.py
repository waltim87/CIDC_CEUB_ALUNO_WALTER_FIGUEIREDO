"""Compara o nível atual com os marcadores históricos de cheia e seca da estação."""

from __future__ import annotations

from typing import Any, Mapping


def _numero(valor: Any) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def comparar_com_historico(
    nivel_cm: Any, cheia_cm: Any, seca_cm: Any
) -> dict[str, Any]:
    """Posição do nível entre a seca (0%) e a cheia (100%) históricas.

    Marcadores ausentes resultam em campos None; nunca são presumidos.
    """
    nivel, cheia, seca = _numero(nivel_cm), _numero(cheia_cm), _numero(seca_cm)
    resultado: dict[str, Any] = {
        "dif_cheia_cm": None,
        "dif_seca_cm": None,
        "posicao_pct": None,
        "situacao": "sem_marcadores",
    }
    if nivel is None:
        resultado["situacao"] = "sem_leitura"
        return resultado
    if cheia is not None:
        resultado["dif_cheia_cm"] = nivel - cheia
    if seca is not None:
        resultado["dif_seca_cm"] = nivel - seca
    if cheia is not None and seca is not None and cheia > seca:
        resultado["posicao_pct"] = (nivel - seca) / (cheia - seca) * 100
    if cheia is not None and nivel >= cheia:
        resultado["situacao"] = "acima_da_cheia_historica"
    elif seca is not None and nivel <= seca:
        resultado["situacao"] = "abaixo_da_seca_historica"
    elif cheia is not None or seca is not None:
        resultado["situacao"] = "dentro_da_faixa_historica"
    return resultado


def extremos_observados(niveis: list[Any]) -> tuple[float | None, float | None]:
    """Maior e menor nível da série informada (apoio quando não há marcador oficial)."""
    valores = [v for v in (_numero(n) for n in niveis) if v is not None]
    return (max(valores), min(valores)) if valores else (None, None)
