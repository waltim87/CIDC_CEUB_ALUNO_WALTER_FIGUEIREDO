"""Coletor configurável de arquivos de escolas do INEP."""

from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    return coletar_configurado(
        "inep", configuracao or carregar_configuracao("inep"), sessao=sessao
    )
