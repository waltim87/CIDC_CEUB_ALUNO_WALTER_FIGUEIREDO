"""Execução isolada e registro do estado das fontes configuradas."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from collectors.ana import coletar as coletar_ana
from collectors.cemaden import coletar as coletar_cemaden
from collectors.cnes import coletar as coletar_cnes
from collectors.ibge import coletar as coletar_ibge
from collectors.inep import coletar as coletar_inep
from collectors.inmet import coletar as coletar_inmet
from collectors.inpe import coletar as coletar_inpe
from collectors.sgb import coletar as coletar_sgb
from collectors.comum import ConfiguracaoPendenteError, carregar_configuracao

LOGGER = logging.getLogger(__name__)

COLETORES: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "ana": coletar_ana,
    "inpe": coletar_inpe,
    "inmet": coletar_inmet,
    "sgb": coletar_sgb,
    "cemaden": coletar_cemaden,
    "ibge": coletar_ibge,
    "cnes": coletar_cnes,
    "inep": coletar_inep,
}


def verificar_fontes(
    *,
    configuracoes: dict[str, dict[str, Any]] | None = None,
    coletores: dict[str, Callable[..., list[dict[str, Any]]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Executa cada fonte isoladamente e retorna status, horário, contagem e erro."""
    configuracoes = configuracoes or {
        chave: carregar_configuracao(chave) for chave in COLETORES
    }
    coletores = coletores or COLETORES
    resultados: dict[str, dict[str, Any]] = {}

    for chave, coletor in coletores.items():
        nome = configuracoes.get(chave, {}).get("nome", chave)
        verificacao = datetime.now(timezone.utc).isoformat()
        try:
            registros = coletor(configuracoes.get(chave))
            resultados[chave] = {
                "nome": nome,
                "status": "operacional",
                "verificado_em": verificacao,
                "registros": len(registros),
                "erro": None,
            }
        except ConfiguracaoPendenteError as erro:
            LOGGER.warning("Fonte %s pendente de confirmação: %s", nome, erro)
            resultados[chave] = {
                "nome": nome,
                "status": "pendente_confirmacao",
                "verificado_em": verificacao,
                "registros": 0,
                "erro": str(erro),
            }
        except Exception as erro:
            LOGGER.exception("Falha isolada na fonte %s; seguindo para as demais", nome)
            resultados[chave] = {
                "nome": nome,
                "status": "erro",
                "verificado_em": verificacao,
                "registros": 0,
                "erro": str(erro),
            }
    return resultados


def persistir_saude(
    resultados: dict[str, dict[str, Any]],
    *,
    url: str | None = None,
    chave: str | None = None,
) -> int:
    """Atualiza o registro das fontes no Supabase; os segredos vêm do ambiente."""
    import os

    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url = url or os.environ.get("SUPABASE_URL")
    chave = chave or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente")

    cliente = create_client(url, chave)
    atualizadas = 0
    for resultado in resultados.values():
        campos_atualizar: dict[str, Any] = {
            "status": resultado["status"],
            "ultima_verificacao": resultado["verificado_em"],
            "ultimo_erro": resultado["erro"],
        }
        if resultado["status"] == "operacional":
            campos_atualizar["ultima_coleta"] = resultado["verificado_em"]
        consulta = (
            cliente.table("fontes")
            .update(campos_atualizar)
            .eq("nome", resultado["nome"])
            .execute()
        )
        quantidade = len(consulta.data or [])
        if quantidade == 0:
            raise RuntimeError(
                f"Fonte '{resultado['nome']}' não existe na tabela public.fontes"
            )
        atualizadas += quantidade
    return atualizadas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for fonte, estado in verificar_fontes().items():
        LOGGER.info("%s: %s (%s registro(s))", fonte, estado["status"], estado["registros"])
