"""Robô de análise de risco por município (executado a cada 3 horas).

Para cada estação com leituras reais calcula nível atual, variação projetada em
24 h e direção (subindo/descendo/estável), compara com cotas e extremos
históricos quando cadastrados e consolida um sinal por município. Um texto
curto é redigido pela IA (core/llm.py) ou pelo modelo fixo. Limiares em
config/robo.yaml são hipóteses sem validação oficial; o resultado é triagem
indicativa e não substitui alertas aprovados por humano.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from core import llm

LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "robo.yaml"
ORDEM_SINAIS = ["sem_dados", "normal", "atencao", "alerta", "alto"]
ROTULOS_SINAL = {
    "sem_dados": "Sem dados",
    "normal": "Normal",
    "atencao": "Atenção",
    "alerta": "Alerta",
    "alto": "Alto",
}
ROTULOS_DIRECAO = {"subindo": "subindo", "descendo": "descendo", "estavel": "estável"}


def carregar_config(caminho: Path = CONFIG_PATH) -> dict[str, Any]:
    with caminho.open(encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


def _instante(valor: str) -> datetime:
    instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)


def _maior(*sinais: str) -> str:
    return max(sinais, key=ORDEM_SINAIS.index)


def classificar_variacao(variacao_24h_cm: float | None, cfg: dict[str, Any]) -> str:
    if variacao_24h_cm is None:
        return "normal"
    limites = cfg["variacao_24h_cm"]
    absoluta = abs(variacao_24h_cm)
    if absoluta >= limites["alto"]:
        return "alto"
    if absoluta >= limites["alerta"]:
        return "alerta"
    if absoluta >= limites["atencao"]:
        return "atencao"
    return "normal"


def analisar_estacao(
    estacao: dict[str, Any],
    leituras: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    agora: datetime,
) -> dict[str, Any]:
    """Sinal de uma estação a partir das leituras de nível (qualquer ordem)."""
    serie = sorted(
        (
            (_instante(l["data_hora_leitura"]), float(l["nivel_cm"]))
            for l in leituras
            if l.get("nivel_cm") is not None
        ),
        key=lambda item: item[0],
    )
    base = {
        "estacao": estacao.get("nome"),
        "codigo": estacao.get("codigo_oficial"),
        "rio": estacao.get("rio"),
        "latitude": estacao.get("latitude"),
        "longitude": estacao.get("longitude"),
        "nivel_cm": None,
        "data_hora_leitura": None,
        "idade_horas": None,
        "variacao_24h_cm": None,
        "direcao": None,
        "sinal": "sem_dados",
        "motivos": [],
    }
    if not serie:
        base["motivos"].append("sem leitura de nível na janela analisada")
        return base

    ultimo_instante, nivel = serie[-1]
    idade = (agora - ultimo_instante).total_seconds() / 3600
    base.update(
        nivel_cm=round(nivel, 1),
        data_hora_leitura=ultimo_instante.astimezone(timezone.utc).isoformat(),
        idade_horas=round(idade, 1),
    )
    if idade > cfg["idade_maxima_leitura_horas"]:
        base["motivos"].append(f"última leitura com {round(idade, 1)} h de atraso")
        return base

    sinal = "normal"
    primeiro_instante, nivel_inicial = serie[0]
    horas = (ultimo_instante - primeiro_instante).total_seconds() / 3600
    if horas >= cfg["horas_minimas_para_tendencia"]:
        variacao = round((nivel - nivel_inicial) / horas * 24, 1)
        base["variacao_24h_cm"] = variacao
        if abs(variacao) <= cfg["variacao_24h_cm"]["estavel"]:
            base["direcao"] = "estavel"
        else:
            base["direcao"] = "subindo" if variacao > 0 else "descendo"
        sinal_variacao = classificar_variacao(variacao, cfg)
        if sinal_variacao != "normal":
            base["motivos"].append(
                f"nível {ROTULOS_DIRECAO[base['direcao']]} {abs(variacao)} cm em 24 h"
            )
        sinal = _maior(sinal, sinal_variacao)
    else:
        base["motivos"].append("série curta demais para estimar tendência")

    cota_alerta = estacao.get("cota_alerta")
    cota_emergencia = estacao.get("cota_emergencia")
    if cota_emergencia is not None and nivel >= float(cota_emergencia):
        sinal = _maior(sinal, "alto")
        base["motivos"].append(f"nível acima da cota de emergência ({cota_emergencia} cm)")
    elif cota_alerta is not None and nivel >= float(cota_alerta):
        sinal = _maior(sinal, "alerta")
        base["motivos"].append(f"nível acima da cota de alerta ({cota_alerta} cm)")
    elif cota_alerta is not None and nivel >= float(cota_alerta) * cfg["fracao_cota_atencao"]:
        sinal = _maior(sinal, "atencao")
        base["motivos"].append(f"nível próximo da cota de alerta ({cota_alerta} cm)")

    margem = cfg["margem_extremo_historico"]
    seca = estacao.get("seca_historica_cm")
    cheia = estacao.get("cheia_historica_cm")
    if seca is not None and nivel <= float(seca) * (1 + margem):
        sinal = _maior(sinal, "alerta")
        base["motivos"].append(f"nível perto da seca histórica ({seca} cm)")
    if cheia is not None and nivel >= float(cheia) * (1 - margem):
        sinal = _maior(sinal, "alerta")
        base["motivos"].append(f"nível perto da cheia histórica ({cheia} cm)")

    base["sinal"] = sinal
    return base


def consolidar_municipio(
    municipio: dict[str, Any], analises_estacoes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Sinal do município = pior sinal entre as estações (com dados) dele."""
    sinal = "sem_dados"
    pior: dict[str, Any] | None = None
    for analise in analises_estacoes:
        if pior is None or ORDEM_SINAIS.index(analise["sinal"]) > ORDEM_SINAIS.index(sinal):
            sinal, pior = analise["sinal"], analise
    leituras = [a["data_hora_leitura"] for a in analises_estacoes if a["data_hora_leitura"]]
    fatores = []
    for analise in analises_estacoes:
        fatores.extend(f"{analise['estacao']}: {motivo}" for motivo in analise["motivos"])
    return {
        "municipio_id": municipio["id_ibge"],
        "municipio": municipio.get("nome"),
        "populacao": municipio.get("populacao"),
        "sinal": sinal,
        "direcao": (pior or {}).get("direcao"),
        "fatores": fatores,
        "estacoes": analises_estacoes,
        "data_hora_leitura_referencia": max(leituras) if leituras else None,
    }


def texto_modelo_fixo(resultado: dict[str, Any]) -> str:
    """Texto determinístico, usado sem IA ou quando a IA falha."""
    partes = [
        f"{resultado['municipio']}: sinal {ROTULOS_SINAL[resultado['sinal']]} "
        "(triagem indicativa, sem validação oficial)."
    ]
    for estacao in resultado["estacoes"]:
        if estacao["nivel_cm"] is None:
            partes.append(f"Estação {estacao['estacao']} sem leitura de nível recente.")
            continue
        trecho = f"Estação {estacao['estacao']}: nível {estacao['nivel_cm']} cm"
        if estacao["sinal"] == "sem_dados":
            partes.append(
                f"{trecho} na última leitura, há {estacao['idade_horas']} h (desatualizada)."
            )
            continue
        if estacao["variacao_24h_cm"] is not None:
            trecho += (
                f", {ROTULOS_DIRECAO[estacao['direcao']]} "
                f"({estacao['variacao_24h_cm']:+} cm projetados em 24 h)"
            )
        partes.append(trecho + ".")
    if resultado.get("populacao"):
        partes.append(f"População do município: {resultado['populacao']} pessoas (IBGE 2022).")
    partes.append("Confirme nos órgãos oficiais antes de qualquer decisão.")
    return " ".join(partes)


def fatos_para_ia(resultado: dict[str, Any]) -> dict[str, Any]:
    return {
        "municipio": resultado["municipio"],
        "populacao_ibge_2022": resultado.get("populacao"),
        "sinal": ROTULOS_SINAL[resultado["sinal"]],
        "motivos": resultado["fatores"],
        "estacoes": [
            {
                "nome": e["estacao"],
                "rio": e["rio"],
                "nivel_cm": e["nivel_cm"],
                "variacao_24h_cm": e["variacao_24h_cm"],
                "direcao": ROTULOS_DIRECAO.get(e["direcao"] or "", None),
            }
            for e in resultado["estacoes"]
        ],
    }


def _buscar_dados(cliente: Any, agora: datetime, cfg: dict[str, Any]) -> tuple[list, dict, dict]:
    estacoes = (
        cliente.table("estacoes")
        .select(
            "id,codigo_oficial,nome,rio,municipio_id,latitude,longitude,cota_alerta,cota_emergencia,"
            "cheia_historica_cm,seca_historica_cm"
        )
        .not_.is_("codigo_oficial", "null")
        .execute()
        .data
        or []
    )
    municipios = {
        m["id_ibge"].strip(): m
        for m in (
            cliente.table("municipios")
            .select("id_ibge,nome,uf,populacao,latitude,longitude")
            .execute()
            .data
            or []
        )
    }
    limite = (agora - timedelta(hours=cfg["janela_horas"])).isoformat()
    leituras: dict[str, list] = {}
    for estacao in estacoes:
        try:
            leituras[estacao["id"]] = (
                cliente.table("leituras")
                .select("data_hora_leitura,nivel_cm")
                .eq("estacao_id", estacao["id"])
                .gte("data_hora_leitura", limite)
                .order("data_hora_leitura")
                .limit(1000)
                .execute()
                .data
                or []
            )
        except Exception:
            LOGGER.exception("Falha ao ler leituras da estação %s", estacao.get("codigo_oficial"))
            leituras[estacao["id"]] = []
    return estacoes, municipios, leituras


def executar_robo(
    cliente: Any,
    *,
    agora: datetime | None = None,
    cfg: dict[str, Any] | None = None,
    gerar_texto: Callable[..., tuple[str, str, str | None]] = llm.gerar_texto,
) -> dict[str, Any]:
    agora = agora or datetime.now(timezone.utc)
    cfg = cfg or carregar_config()
    estacoes, municipios, leituras = _buscar_dados(cliente, agora, cfg)

    por_municipio: dict[str, list] = {}
    for estacao in estacoes:
        municipio_id = (estacao.get("municipio_id") or "").strip()
        if municipio_id:
            por_municipio.setdefault(municipio_id, []).append(
                analisar_estacao(estacao, leituras.get(estacao["id"], []), cfg, agora=agora)
            )

    resumo = {"municipios": 0, "ia": 0, "modelo_fixo": 0, "erros": 0}
    chamadas_ia = 0
    for municipio_id, analises in sorted(por_municipio.items()):
        try:
            municipio = municipios.get(municipio_id, {"id_ibge": municipio_id, "nome": municipio_id})
            resultado = consolidar_municipio(municipio, analises)
            texto_fixo = texto_modelo_fixo(resultado)
            if chamadas_ia < cfg["ia"]["max_chamadas_por_execucao"]:
                chamadas_ia += 1
                texto, metodo, modelo = gerar_texto(
                    fatos_para_ia(resultado),
                    texto_fixo,
                    modelo=cfg["ia"]["modelo"],
                    variavel_chave=cfg["ia"]["variavel_chave"],
                    timeout=cfg["ia"]["timeout_segundos"],
                )
            else:
                texto, metodo, modelo = texto_fixo, "modelo_fixo", None
            cliente.table("analises_risco").insert(
                {
                    "municipio_id": municipio_id,
                    "gerado_em": agora.isoformat(),
                    "sinal": resultado["sinal"],
                    "direcao": resultado["direcao"],
                    "texto": texto,
                    "metodo": metodo,
                    "modelo": modelo,
                    "fatores_json": resultado["fatores"],
                    "estacoes_json": resultado["estacoes"],
                    "fontes_json": [
                        {"nome": f"ANA estação {e['codigo']}", "data_hora_leitura": e["data_hora_leitura"]}
                        for e in analises
                        if e["data_hora_leitura"]
                    ],
                    "data_hora_leitura_referencia": resultado["data_hora_leitura_referencia"],
                }
            ).execute()
            resumo["municipios"] += 1
            resumo[metodo] += 1
        except Exception:
            LOGGER.exception("Falha na análise do município %s", municipio_id)
            resumo["erros"] += 1
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    resumo = executar_robo(create_client(url, chave))
    LOGGER.info("Robô: %s", resumo)
    return 1 if resumo["erros"] and not resumo["municipios"] else 0


if __name__ == "__main__":
    sys.exit(main())
