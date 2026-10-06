"""Ciclo único de coleta para o agendador (GitHub Actions) ou uso manual.

Cada fonte roda isolada; o resultado de cada uma é gravado em public.fontes.
Fontes ainda marcadas como CONFIRMAR ficam como "pendente_confirmacao" e não
derrubam a execução.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from collectors import saude
from collectors.ana import persistir_no_supabase as persistir_ana

LOGGER = logging.getLogger(__name__)


def _coletor_ana_com_gravacao(
    coletor: Callable[..., list[dict[str, Any]]],
    gravador: Callable[..., int],
) -> Callable[..., list[dict[str, Any]]]:
    def executar(configuracao: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        leituras = coletor(configuracao)
        gravador(leituras)
        return leituras

    return executar


def executar_ciclo(
    *,
    coletores: dict[str, Callable[..., list[dict[str, Any]]]] | None = None,
    configuracoes: dict[str, dict[str, Any]] | None = None,
    gravar_saude: Callable[[dict[str, dict[str, Any]]], int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Coleta todas as fontes e registra a saúde de cada uma, sem interromper no meio."""
    if coletores is None:
        coletores = dict(saude.COLETORES)
        coletores["ana"] = _coletor_ana_com_gravacao(coletores["ana"], persistir_ana)
    gravar_saude = gravar_saude or saude.persistir_saude

    resultados = saude.verificar_fontes(configuracoes=configuracoes, coletores=coletores)
    for chave, resultado in resultados.items():
        try:
            gravar_saude({chave: resultado})
        except Exception:
            LOGGER.exception("Não foi possível registrar a saúde da fonte %s", chave)
            resultado["erro_registro"] = True
    return resultados


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    resultados = executar_ciclo()
    for chave, estado in resultados.items():
        LOGGER.info("%s: %s (%s registro(s))", chave, estado["status"], estado["registros"])
    # Falha o job só se nada pôde ser registrado (ex.: segredos ausentes).
    if resultados and all(r.get("erro_registro") for r in resultados.values()):
        LOGGER.error("Nenhuma fonte pôde ser registrada no Supabase; confira os Secrets.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
