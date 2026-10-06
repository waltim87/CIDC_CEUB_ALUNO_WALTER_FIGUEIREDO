"""Coletor configurável de arquivos de estabelecimentos do CNES."""

from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    return coletar_configurado(
        "cnes", configuracao or carregar_configuracao("cnes"), sessao=sessao
    )
