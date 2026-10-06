"""Coletor configurável de arquivos CSV do INPE Queimadas."""

from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    return coletar_configurado(
        "inpe", configuracao or carregar_configuracao("inpe"), sessao=sessao
    )
