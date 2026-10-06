"""Coletor configurável da Plataforma de Entrega de Dados do Cemaden."""

from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    return coletar_configurado(
        "cemaden", configuracao or carregar_configuracao("cemaden"), sessao=sessao
    )
