"""Coletor configurável dos boletins de alerta hidrológico do SGB/SACE."""

from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    return coletar_configurado(
        "sgb", configuracao or carregar_configuracao("sgb"), sessao=sessao
    )
