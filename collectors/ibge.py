"""Coletor confirmado de municípios do IBGE API de Localidades."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from collectors.comum import (
    ConfiguracaoPendenteError,
    carregar_configuracao,
    coletar_configurado,
)


def coletar(
    configuracao: dict[str, Any] | None = None, *, sessao: Any = requests
) -> list[dict[str, Any]]:
    configuracao = configuracao or carregar_configuracao("ibge")
    municipios = coletar_configurado("ibge", configuracao, sessao=sessao)
    uf = configuracao.get("uf")
    if not isinstance(uf, str) or len(uf) != 2:
        raise ConfiguracaoPendenteError("Confirme a sigla UF para o endpoint IBGE")

    saida = []
    for municipio in municipios:
        codigo = municipio.get("id_ibge")
        nome = municipio.get("nome")
        if not isinstance(codigo, (int, str)) or not str(codigo).isdigit():
            raise ValueError(f"Código IBGE inválido: {codigo!r}")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError(f"Nome inválido para município IBGE {codigo}")
        saida.append(
            {
                "id_ibge": str(codigo).zfill(7),
                "nome": nome.strip(),
                "uf": uf,
                "fonte": municipio["fonte"],
                "coletado_em": municipio["coletado_em"],
            }
        )
    return saida


def persistir(
    municipios: list[dict[str, Any]],
    *,
    configuracao: dict[str, Any] | None = None,
) -> int:
    if not municipios:
        return 0
    configuracao = configuracao or carregar_configuracao("ibge")

    from dotenv import load_dotenv
    from supabase import create_client

    import os

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente")
    cliente = create_client(url, chave)

    fonte = (
        cliente.table("fontes")
        .select("id")
        .eq("nome", configuracao["nome"])
        .single()
        .execute()
    )
    fonte_id = fonte.data["id"]
    linhas = [
        {
            "id_ibge": municipio["id_ibge"],
            "nome": municipio["nome"],
            "uf": municipio["uf"],
        }
        for municipio in municipios
    ]
    cliente.table("municipios").upsert(linhas, on_conflict="id_ibge").execute()
    agora = datetime.now(timezone.utc).isoformat()
    cliente.table("fontes").update(
        {
            "ultima_coleta": agora,
            "ultima_verificacao": agora,
            "ultimo_erro": None,
            "status": "operacional",
        }
    ).eq("id", fonte_id).execute()
    return len(linhas)
