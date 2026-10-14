"""Relatório PDF das análises do robô: gráficos, alertas, marcadores históricos e tabela.

Gerado a cada execução do GitHub Actions (artefato baixável na página da
execução) e pelo botão do painel. Usa somente dados já gravados.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.relatorios import gerar_pdf
from core.robo import ORDEM_SINAIS, ROTULOS_DIRECAO, ROTULOS_SINAL, _data_br

LOGGER = logging.getLogger(__name__)
COLUNAS_ESTACOES = [
    "Município", "Estação", "Sinal", "Nível (cm)", "Variação 24 h (cm)",
    "Posição na faixa (%)", "Seca recorde (cm)", "Cheia recorde (cm)", "Leitura (UTC)",
]


def linhas_estacoes(
    analises: Mapping[str, Mapping[str, Any]], nomes: Mapping[str, str]
) -> list[dict[str, Any]]:
    linhas = []
    for codigo, analise in analises.items():
        for e in analise.get("estacoes_json") or []:
            linhas.append(
                {
                    "Município": nomes.get(codigo, codigo),
                    "Estação": f"{e.get('estacao')} ({e.get('codigo')})",
                    "Sinal": ROTULOS_SINAL.get(e.get("sinal"), e.get("sinal")),
                    "Nível (cm)": e.get("nivel_cm"),
                    "Variação 24 h (cm)": e.get("variacao_24h_cm"),
                    "Posição na faixa (%)": e.get("posicao_pct"),
                    "Seca recorde (cm)": (
                        f"{e['seca_historica_cm']:g} ({_data_br(e.get('seca_historica_data'))})"
                        if e.get("seca_historica_cm") is not None else None
                    ),
                    "Cheia recorde (cm)": (
                        f"{e['cheia_historica_cm']:g} ({_data_br(e.get('cheia_historica_data'))})"
                        if e.get("cheia_historica_cm") is not None else None
                    ),
                    "Leitura (UTC)": (e.get("data_hora_leitura") or "")[:16].replace("T", " "),
                }
            )
    ordem = {ROTULOS_SINAL[s]: i for i, s in enumerate(reversed(ORDEM_SINAIS))}
    return sorted(linhas, key=lambda l: ordem.get(l["Sinal"], 9))


def gerar_relatorio_robo(
    analises: Mapping[str, Mapping[str, Any]],
    nomes: Mapping[str, str],
    *,
    alertas_gerados: int | None = None,
) -> bytes:
    contagem = {ROTULOS_SINAL[s]: 0 for s in ORDEM_SINAIS}
    for analise in analises.values():
        contagem[ROTULOS_SINAL.get(analise.get("sinal"), "Sem dados")] += 1
    linhas = linhas_estacoes(analises, nomes)
    posicoes = {
        l["Estação"]: l["Posição na faixa (%)"]
        for l in linhas
        if l["Posição na faixa (%)"] is not None
    }
    resumo: dict[str, Any] = {
        "Municípios analisados": len(analises),
        "Em Atenção ou acima": sum(
            1 for a in analises.values() if a.get("sinal") in {"atencao", "alerta", "alto"}
        ),
        "Última análise (UTC)": max(
            (str(a.get("gerado_em") or "")[:16].replace("T", " ") for a in analises.values()),
            default="n/d",
        ),
        "Faixa histórica": "0% = seca recorde, 100% = cheia recorde (ANA 1990+)",
    }
    if alertas_gerados is not None:
        resumo["Rascunhos de alerta criados nesta execução"] = alertas_gerados
    graficos = [("Municípios por sinal do robô", contagem)]
    if posicoes:
        graficos.append(("Posição do nível entre seca (0%) e cheia (100%) recordes", posicoes))
    return gerar_pdf(
        "Relatório de risco hidrológico — robô CIDC",
        linhas,
        COLUNAS_ESTACOES,
        resumo=resumo,
        graficos=graficos,
        analises=[
            {
                "Município": nomes.get(codigo, codigo),
                "sinal": ROTULOS_SINAL.get(a.get("sinal"), a.get("sinal"))
                + (f" ({ROTULOS_DIRECAO[a['direcao']]})" if a.get("direcao") else ""),
                "texto": a.get("texto"),
                "gerado_em": str(a.get("gerado_em") or "")[:16].replace("T", " ") + " UTC",
            }
            for codigo, a in sorted(
                analises.items(),
                key=lambda item: -ORDEM_SINAIS.index(item[1].get("sinal", "sem_dados")),
            )
        ],
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    cliente = create_client(url, chave)
    linhas = (
        cliente.table("analises_risco").select("*").order("gerado_em", desc=True).limit(500).execute().data
        or []
    )
    analises: dict[str, dict[str, Any]] = {}
    for linha in linhas:
        analises.setdefault(str(linha["municipio_id"]).strip(), linha)
    nomes = {
        str(m["id_ibge"]).strip(): f"{m['nome']}/{m['uf']}"
        for m in cliente.table("municipios").select("id_ibge,nome,uf").execute().data or []
    }
    pasta = Path("relatorios")
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"relatorio_risco_{datetime.now(timezone.utc):%Y%m%d_%H%M}UTC.pdf"
    arquivo.write_bytes(gerar_relatorio_robo(analises, nomes))
    LOGGER.info("Relatório gerado: %s (%s municípios)", arquivo, len(analises))
    return 0


if __name__ == "__main__":
    sys.exit(main())
