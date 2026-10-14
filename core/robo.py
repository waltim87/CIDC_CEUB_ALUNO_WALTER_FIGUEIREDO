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
import time
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
        "posicao_pct": None,
        "seca_historica_cm": estacao.get("seca_historica_cm"),
        "seca_historica_data": estacao.get("seca_historica_data"),
        "cheia_historica_cm": estacao.get("cheia_historica_cm"),
        "cheia_historica_data": estacao.get("cheia_historica_data"),
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

    sinal = _maior(sinal, _avaliar_faixa_historica(base, estacao, nivel, cfg))
    base["sinal"] = sinal
    return base


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _avaliar_faixa_historica(
    base: dict[str, Any], estacao: dict[str, Any], nivel: float, cfg: dict[str, Any]
) -> str:
    """Posição entre seca (0%) e cheia (100%) recordes; perto de qualquer extremo eleva o sinal."""
    seca, cheia = estacao.get("seca_historica_cm"), estacao.get("cheia_historica_cm")
    base.update(
        seca_historica_cm=float(seca) if seca is not None else None,
        seca_historica_data=estacao.get("seca_historica_data"),
        cheia_historica_cm=float(cheia) if cheia is not None else None,
        cheia_historica_data=estacao.get("cheia_historica_data"),
        posicao_pct=None,
    )
    if seca is None or cheia is None or float(cheia) <= float(seca):
        return "normal"
    seca, cheia = float(seca), float(cheia)
    posicao = round((nivel - seca) / (cheia - seca) * 100, 1)
    base["posicao_pct"] = posicao
    faixa = cfg["faixa_historica_pct"]
    if posicao <= 50:
        extremo, valor, data, distancia = "seca", seca, estacao.get("seca_historica_data"), posicao
    else:
        extremo, valor, data, distancia = "cheia", cheia, estacao.get("cheia_historica_data"), 100 - posicao
    referencia = f"{extremo} recorde de {valor:g} cm em {_data_br(data)}"
    if distancia <= 0:
        base["motivos"].append(
            f"nível {'abaixo' if extremo == 'seca' else 'acima'} da {referencia}"
        )
        return "alto"
    if distancia <= faixa["alerta"]:
        base["motivos"].append(f"nível a {distancia:g}% da faixa histórica da {referencia}")
        return "alerta"
    if distancia <= faixa["atencao"]:
        base["motivos"].append(f"nível a {distancia:g}% da faixa histórica da {referencia}")
        return "atencao"
    return "normal"


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


def aplicar_meteorologia(
    resultado: dict[str, Any], avisos: list[dict[str, Any]], chuva: list[dict[str, Any]], cfg: dict[str, Any]
) -> dict[str, Any]:
    """Avisos oficiais do INMET e chuva prevista elevam o sinal e entram nos fatores."""
    regras = cfg.get("meteorologia") or {}
    severidades = regras.get("severidade_inmet") or {}
    resultado["avisos"] = [
        {"descricao": a["descricao"], "severidade": a["severidade"], "fim": a.get("fim"),
         "riscos": a.get("riscos")}
        for a in avisos
    ]
    resultado["chuva_prevista"] = [
        {"data": c["data"], "mm": float(c["chuva_prevista_mm"])}
        for c in chuva if c.get("chuva_prevista_mm") is not None
    ]
    sinal = resultado["sinal"]
    vistos = set()
    for aviso in avisos:
        efeito = severidades.get(aviso["severidade"])
        if efeito:
            sinal = _maior(sinal, efeito)
        chave = (aviso["descricao"], aviso["severidade"])
        if chave not in vistos:
            vistos.add(chave)
            resultado["fatores"].append(
                f"INMET: aviso de {aviso['descricao']} ({aviso['severidade']}) até {_data_br(aviso.get('fim'))}"
            )
    limites = regras.get("chuva_prevista_dia_mm") or {}
    maior_chuva = max((c["mm"] for c in resultado["chuva_prevista"]), default=None)
    if maior_chuva is not None and limites:
        if maior_chuva >= limites.get("alerta", float("inf")):
            sinal = _maior(sinal, "alerta")
        elif maior_chuva >= limites.get("atencao", float("inf")):
            sinal = _maior(sinal, "atencao")
        if maior_chuva >= limites.get("atencao", float("inf")):
            resultado["fatores"].append(f"chuva prevista de até {maior_chuva:g} mm em um dia (Open-Meteo)")
    resultado["sinal"] = sinal
    return resultado


def _nivel_por_limite(valor: float | None, limites: dict[str, float]) -> str | None:
    if valor is None:
        return None
    if valor >= limites.get("alerta", float("inf")):
        return "alerta"
    if valor >= limites.get("atencao", float("inf")):
        return "atencao"
    return None


def aplicar_fontes_oficiais(
    resultado: dict[str, Any], dados: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    """SGB/SACE (situação oficial), Cemaden (chuva observada) e INPE (focos) elevam o sinal."""
    regras = cfg.get("fontes_oficiais") or {}
    sinal = resultado["sinal"]
    sace = dados.get("sace") or []
    resultado["sace"] = [{"ponto": p["nome"], "situacao": p.get("situacao"), "cota_cm": p.get("cota_cm"),
                          "medido_em": p.get("medido_em")} for p in sace]
    for ponto in sace:
        efeito = (regras.get("situacao_sace") or {}).get(str(ponto.get("situacao") or ""))
        if efeito:
            sinal = _maior(sinal, efeito)
            resultado["fatores"].append(f"SGB/SACE: ponto {ponto['nome']} em situação {ponto['situacao']}")
    chuva = dados.get("chuva_24h")
    resultado["chuva_observada_24h_mm"] = chuva
    nivel = _nivel_por_limite(chuva, regras.get("chuva_observada_24h_mm") or {})
    if nivel:
        sinal = _maior(sinal, nivel)
        resultado["fatores"].append(f"Cemaden: chuva observada de {chuva:g} mm em 24 h")
    focos = dados.get("focos_24h")
    resultado["focos_24h"] = focos
    nivel = _nivel_por_limite(focos, regras.get("focos_24h") or {})
    if nivel:
        sinal = _maior(sinal, nivel)
        resultado["fatores"].append(f"INPE: {focos} focos de calor detectados em 24 h")
    resultado["sinal"] = sinal
    return resultado


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
        if estacao.get("posicao_pct") is not None:
            trecho += (
                f"; posição {estacao['posicao_pct']}% entre a seca recorde "
                f"({estacao['seca_historica_cm']:g} cm, {_data_br(estacao['seca_historica_data'])}) "
                f"e a cheia recorde ({estacao['cheia_historica_cm']:g} cm, "
                f"{_data_br(estacao['cheia_historica_data'])})"
            )
        partes.append(trecho + ".")
    vistos = set()
    for aviso in resultado.get("avisos") or []:
        chave = (aviso["descricao"], aviso["severidade"])
        if chave in vistos:
            continue
        vistos.add(chave)
        partes.append(
            f"INMET: aviso de {aviso['descricao']} ({aviso['severidade']}) até {_data_br(aviso.get('fim'))}."
        )
    chuva = [c for c in resultado.get("chuva_prevista") or [] if c["mm"] is not None]
    if chuva:
        partes.append(
            "Chuva prevista (Open-Meteo): "
            + ", ".join(f"{_data_br(c['data'])[:5]} {c['mm']:g} mm" for c in chuva) + "."
        )
    for ponto in resultado.get("sace") or []:
        if ponto.get("situacao"):
            partes.append(f"SGB/SACE: ponto {ponto['ponto']} em situação {ponto['situacao']}"
                          + (f", cota {ponto['cota_cm']:g} cm." if ponto.get("cota_cm") is not None else "."))
    if resultado.get("chuva_observada_24h_mm"):
        partes.append(f"Chuva observada em 24 h (Cemaden): {resultado['chuva_observada_24h_mm']:g} mm.")
    if resultado.get("focos_24h"):
        partes.append(f"Focos de calor em 24 h (INPE): {resultado['focos_24h']}.")
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
        "avisos_inmet": [
            {"tipo": a["descricao"], "severidade": a["severidade"], "ate": _data_br(a.get("fim"))}
            for a in resultado.get("avisos") or []
        ],
        "sace_situacao_oficial": resultado.get("sace") or [],
        "chuva_observada_24h_mm_cemaden": resultado.get("chuva_observada_24h_mm"),
        "focos_calor_24h_inpe": resultado.get("focos_24h"),
        "chuva_prevista_mm_por_dia": {
            _data_br(c["data"])[:5]: c["mm"] for c in resultado.get("chuva_prevista") or []
        },
        "estacoes": [
            {
                "nome": e["estacao"],
                "rio": e["rio"],
                "nivel_cm": e["nivel_cm"],
                "variacao_24h_cm": e["variacao_24h_cm"],
                "direcao": ROTULOS_DIRECAO.get(e["direcao"] or "", None),
                "posicao_pct_entre_seca_e_cheia_recordes": e.get("posicao_pct"),
                "seca_recorde_cm": e.get("seca_historica_cm"),
                "seca_recorde_data": _data_br(e.get("seca_historica_data")),
                "cheia_recorde_cm": e.get("cheia_historica_cm"),
                "cheia_recorde_data": _data_br(e.get("cheia_historica_data")),
            }
            for e in resultado["estacoes"]
        ],
    }


COLUNAS_ESTACAO = "id,codigo_oficial,nome,rio,municipio_id,latitude,longitude,cota_alerta,cota_emergencia"
COLUNAS_HISTORICO = (
    "cheia_historica_cm,cheia_historica_data,seca_historica_cm,seca_historica_data,historico_fonte"
)


def _ler_estacoes(cliente: Any) -> list[dict[str, Any]]:
    """Estações com código oficial; sem as colunas de marcadores, segue sem eles."""
    try:
        consulta = cliente.table("estacoes").select(f"{COLUNAS_ESTACAO},{COLUNAS_HISTORICO}")
        return consulta.not_.is_("codigo_oficial", "null").execute().data or []
    except Exception:
        LOGGER.warning(
            "Marcadores históricos indisponíveis (aplique a migration 202610140004); "
            "seguindo sem eles", exc_info=True,
        )
        consulta = cliente.table("estacoes").select(COLUNAS_ESTACAO)
        return consulta.not_.is_("codigo_oficial", "null").execute().data or []


def _criar_alerta_rascunho(
    cliente: Any,
    *,
    municipio_id: str,
    sinal: str,
    texto: str,
    analise_id: str | None,
    agora: datetime,
    cfg: dict[str, Any],
) -> bool:
    """Rascunho de alerta para revisão humana; não repete dentro da janela configurada."""
    regra = cfg["alerta_automatico"]
    if sinal not in regra["sinais"]:
        return False
    classe = ROTULOS_SINAL[sinal]
    desde = (agora - timedelta(hours=regra["janela_horas"])).isoformat()
    existentes = (
        cliente.table("alertas")
        .select("id")
        .eq("municipio_id", municipio_id)
        .eq("classe", classe)
        .in_("status", ["rascunho", "aprovado", "enviado"])
        .gte("criado_em", desde)
        .limit(1)
        .execute()
        .data
    )
    if existentes:
        return False
    cliente.table("alertas").insert(
        {
            "municipio_id": municipio_id,
            "classe": classe,
            "texto": texto,
            "canal": None,
            "status": "rascunho",
            "analise_id": analise_id,
        }
    ).execute()
    return True


def _buscar_meteorologia(cliente: Any, agora: datetime, cfg: dict[str, Any]) -> tuple[dict, dict]:
    """Avisos INMET vigentes e chuva prevista por município; vazio se as tabelas não existirem."""
    avisos: dict[str, list] = {}
    chuva: dict[str, list] = {}
    try:
        for aviso in (
            cliente.table("avisos_meteorologicos").select("municipio_id,descricao,severidade,inicio,fim,riscos")
            .gte("fim", agora.isoformat()).execute().data or []
        ):
            avisos.setdefault(str(aviso["municipio_id"]).strip(), []).append(aviso)
        dias = (cfg.get("meteorologia") or {}).get("dias_previsao", 3)
        limite = (agora + timedelta(days=dias)).date().isoformat()
        for linha in (
            cliente.table("previsao_tempo").select("municipio_id,data,chuva_prevista_mm")
            .eq("periodo", "dia").gte("data", agora.date().isoformat()).lte("data", limite)
            .order("data").execute().data or []
        ):
            chuva.setdefault(str(linha["municipio_id"]).strip(), []).append(linha)
    except Exception:
        LOGGER.warning("Meteorologia indisponível (aplique a migration 202610140008)", exc_info=True)
    return avisos, chuva


def _buscar_fontes_oficiais(cliente: Any, agora: datetime, cfg: dict[str, Any]) -> dict[str, Any]:
    """SACE por município, maior chuva de 24 h (Cemaden) e focos de 24 h (INPE); vazio sem as tabelas."""
    regras = cfg.get("fontes_oficiais") or {}
    dados: dict[str, Any] = {"sace": {}, "chuva_24h": {}, "focos_24h": {}, "relevantes": set()}
    try:
        for ponto in cliente.table("sace_pontos").select("nome,municipio_id,situacao,cota_cm,medido_em").execute().data or []:
            if ponto.get("municipio_id"):
                codigo = str(ponto["municipio_id"]).strip()
                dados["sace"].setdefault(codigo, []).append(ponto)
                if (regras.get("situacao_sace") or {}).get(str(ponto.get("situacao") or "")):
                    dados["relevantes"].add(codigo)
        for estacao in cliente.table("chuva_cemaden").select("municipio_id,acc24h_mm").execute().data or []:
            if estacao.get("municipio_id") and estacao.get("acc24h_mm") is not None:
                codigo = str(estacao["municipio_id"]).strip()
                dados["chuva_24h"][codigo] = max(dados["chuva_24h"].get(codigo, 0), float(estacao["acc24h_mm"]))
        desde = (agora - timedelta(hours=24)).isoformat()
        for foco in cliente.table("focos_calor").select("municipio_id").gte("data_hora", desde).limit(20000).execute().data or []:
            if foco.get("municipio_id"):
                codigo = str(foco["municipio_id"]).strip()
                dados["focos_24h"][codigo] = dados["focos_24h"].get(codigo, 0) + 1
    except Exception:
        LOGGER.warning("Fontes SACE/Cemaden/INPE indisponíveis (aplique a migration 202610140010)", exc_info=True)
        return dados
    for chave, limite in (("chuva_24h", "chuva_observada_24h_mm"), ("focos_24h", "focos_24h")):
        corte = (regras.get(limite) or {}).get("atencao", float("inf"))
        dados["relevantes"].update(c for c, v in dados[chave].items() if v >= corte)
    return dados


def _buscar_dados(cliente: Any, agora: datetime, cfg: dict[str, Any]) -> tuple[list, dict, dict]:
    estacoes = _ler_estacoes(cliente)
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
    pausa: Callable[[float], None] = time.sleep,
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
    avisos, chuva = _buscar_meteorologia(cliente, agora, cfg)
    for municipio_id in avisos:  # municípios sem estação, mas com aviso oficial do INMET
        por_municipio.setdefault(municipio_id, [])
    oficiais = _buscar_fontes_oficiais(cliente, agora, cfg)
    for municipio_id in oficiais.get("relevantes", set()):  # SACE/Cemaden/INPE acima do limite
        por_municipio.setdefault(municipio_id, [])

    resultados = []
    for municipio_id, analises in por_municipio.items():
        municipio = municipios.get(municipio_id, {"id_ibge": municipio_id, "nome": municipio_id})
        resultado = consolidar_municipio(municipio, analises)
        aplicar_meteorologia(resultado, avisos.get(municipio_id, []), chuva.get(municipio_id, []), cfg)
        aplicar_fontes_oficiais(resultado, {
            "sace": oficiais["sace"].get(municipio_id, []),
            "chuva_24h": oficiais["chuva_24h"].get(municipio_id),
            "focos_24h": oficiais["focos_24h"].get(municipio_id),
        }, cfg)
        resultados.append((municipio_id, analises, resultado))
    # Maior risco primeiro: a cota gratuita de IA vai para os municípios mais críticos.
    resultados.sort(key=lambda item: (-ORDEM_SINAIS.index(item[2]["sinal"]), item[0]))

    resumo = {"municipios": 0, "ia": 0, "modelo_fixo": 0, "alertas": 0, "erros": 0}
    chamadas_ia = 0
    for municipio_id, analises, resultado in resultados:
        try:
            texto_fixo = texto_modelo_fixo(resultado)
            if chamadas_ia < cfg["ia"]["max_chamadas_por_execucao"]:
                if chamadas_ia and os.environ.get(cfg["ia"]["variavel_chave"]):
                    pausa(cfg["ia"].get("intervalo_segundos", 0))
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
            resposta = cliente.table("analises_risco").insert(
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
                    ] + [
                        {"nome": f"INMET aviso: {a['descricao']} ({a['severidade']})", "data_hora_leitura": a.get("fim")}
                        for a in resultado.get("avisos") or []
                    ] + [
                        {"nome": f"SGB/SACE {p['ponto']}: {p['situacao']}", "data_hora_leitura": p.get("medido_em")}
                        for p in resultado.get("sace") or [] if p.get("situacao")
                    ],
                    "data_hora_leitura_referencia": resultado["data_hora_leitura_referencia"],
                }
            ).execute()
            resumo["municipios"] += 1
            resumo[metodo] += 1
            analise_id = ((getattr(resposta, "data", None) or [{}])[0]).get("id")
            if _criar_alerta_rascunho(
                cliente,
                municipio_id=municipio_id,
                sinal=resultado["sinal"],
                texto=texto,
                analise_id=analise_id,
                agora=agora,
                cfg=cfg,
            ):
                resumo["alertas"] += 1
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
    # Qualquer erro deixa a etapa vermelha no GitHub (sem sucesso enganoso).
    return 1 if resumo["erros"] or not resumo["municipios"] else 0


if __name__ == "__main__":
    sys.exit(main())
