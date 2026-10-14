"""Meteorologia: avisos e previsão oficiais do INMET + chuva prevista do Open-Meteo.

``python -m collectors.inmet`` (GitHub Actions, a cada 3 h):

- Avisos meteorológicos ativos do INMET (https://apiprevmet3.inmet.gov.br/avisos/ativos,
  sem chave): grava um registro por município do AM coberto (pelo código IBGE do aviso).
- Previsão do INMET por município (https://apiprevmet3.inmet.gov.br/previsao/{ibge}):
  resumo, temperaturas, umidade e vento por período (manhã/tarde/noite) e por dia.
- Chuva prevista em mm (Open-Meteo, modelo numérico, gratuito, uma consulta para todos
  os municípios): https://api.open-meteo.com — atribuição "Weather data by Open-Meteo.com".

Cada parte falha de forma isolada e o estado vai para a saúde das fontes (INMET).
Observações das estações automáticas do INMET exigem token e não são usadas; a chuva
observada vem dos pluviômetros das estações da ANA.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao

LOGGER = logging.getLogger(__name__)
URL_AVISOS = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
URL_PREVISAO = "https://apiprevmet3.inmet.gov.br/previsao/{codigo}"
URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
NOME_FONTE = "INMET"
CABECALHO = {"User-Agent": "CIDC-prototipo-defesa-civil/1.0"}
PERIODOS = {"manha": "manha", "tarde": "tarde", "noite": "noite"}


def coletar(configuracao: dict[str, Any] | None = None, *, sessao: Any = requests) -> list[dict[str, Any]]:
    """Adaptador genérico configurável (mantido por compatibilidade com config/fontes.yaml)."""
    return coletar_configurado("inmet", configuracao or carregar_configuracao("inmet"), sessao=sessao)


def _instante(dia: str | None, hora: str | None) -> str | None:
    """'2026-10-14T00:00:00.000Z' + '08:50' -> ISO em horário de Brasília (como o INMET publica)."""
    if not dia:
        return None
    return f"{str(dia)[:10]}T{(hora or '00:00')[:5]}:00-03:00"


def _lista(texto: Any) -> str | None:
    """O INMET envia riscos/instruções como texto de lista Python; vira texto corrido."""
    if not texto:
        return None
    limpo = str(texto).strip().strip("[]")
    partes = [p.strip().strip("'\"").strip() for p in limpo.split("', '")]
    return " ".join(p for p in partes if p) or None


def avisos_para_linhas(payload: dict[str, Any], municipios: set[str]) -> list[dict[str, Any]]:
    linhas: dict[tuple[str, str], dict[str, Any]] = {}
    for grupo in ("hoje", "futuro"):
        for aviso in payload.get(grupo) or []:
            if str(aviso.get("encerrado")).lower() == "true":
                continue
            codigos = {c.strip() for c in str(aviso.get("geocodes") or "").split(",") if c.strip()}
            for municipio_id in codigos & municipios:
                linhas[(aviso["codigo"], municipio_id)] = {
                    "codigo": aviso["codigo"],
                    "municipio_id": municipio_id,
                    "descricao": aviso.get("descricao") or "Aviso meteorológico",
                    "severidade": aviso.get("severidade") or "não informada",
                    "cor": aviso.get("aviso_cor"),
                    "inicio": _instante(aviso.get("data_inicio"), aviso.get("hora_inicio")),
                    "fim": _instante(aviso.get("data_fim"), aviso.get("hora_fim")),
                    "riscos": _lista(aviso.get("riscos")),
                    "instrucoes": _lista(aviso.get("instrucoes")),
                    "atualizado_em": datetime.now(timezone.utc).isoformat(),
                }
    return list(linhas.values())


def previsao_para_linhas(municipio_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    linhas = []
    dias = payload.get(municipio_id) or payload.get(str(int(municipio_id))) or {}
    for data_br, conteudo in dias.items():
        try:
            dia = datetime.strptime(data_br, "%d/%m/%Y").date().isoformat()
        except ValueError:
            continue
        blocos = (
            {PERIODOS[p]: conteudo[p] for p in PERIODOS if isinstance(conteudo.get(p), dict)}
            if any(p in conteudo for p in PERIODOS) else {"dia": conteudo}
        )
        for periodo, b in blocos.items():
            linhas.append({
                "municipio_id": municipio_id, "data": dia, "periodo": periodo,
                "resumo": b.get("resumo"), "temp_max": b.get("temp_max"), "temp_min": b.get("temp_min"),
                "umidade_max": b.get("umidade_max"), "umidade_min": b.get("umidade_min"),
                "vento": " ".join(x for x in (b.get("int_vento"), b.get("dir_vento")) if x) or None,
                "fonte": "INMET - previsão do tempo (prevmet)",
                "atualizado_em": datetime.now(timezone.utc).isoformat(),
            })
    return linhas


def chuva_open_meteo(municipios: list[dict[str, Any]], sessao: Any = requests) -> list[dict[str, Any]]:
    """Chuva diária prevista (mm) para os próximos dias, uma linha 'dia' por município."""
    com_coordenadas = [m for m in municipios if m.get("latitude") is not None and m.get("longitude") is not None]
    linhas = []
    for inicio in range(0, len(com_coordenadas), 50):
        lote = com_coordenadas[inicio:inicio + 50]
        resposta = sessao.get(
            URL_OPEN_METEO,
            params={
                "latitude": ",".join(str(m["latitude"]) for m in lote),
                "longitude": ",".join(str(m["longitude"]) for m in lote),
                "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
                "forecast_days": 4, "timezone": "America/Manaus",
            },
            headers=CABECALHO, timeout=60,
        )
        resposta.raise_for_status()
        corpo = resposta.json()
        resultados = corpo if isinstance(corpo, list) else [corpo]
        for municipio, resultado in zip(lote, resultados):
            diario = resultado.get("daily") or {}
            for posicao, dia in enumerate(diario.get("time") or []):
                linhas.append({
                    "municipio_id": str(municipio["id_ibge"]).strip(), "data": dia, "periodo": "dia",
                    "chuva_prevista_mm": (diario.get("precipitation_sum") or [None])[posicao],
                    "temp_max": (diario.get("temperature_2m_max") or [None])[posicao],
                    "temp_min": (diario.get("temperature_2m_min") or [None])[posicao],
                    "fonte": "Open-Meteo (modelo numérico; Weather data by Open-Meteo.com)",
                    "atualizado_em": datetime.now(timezone.utc).isoformat(),
                })
    return linhas


def _mesclar_dia(previsao_inmet: list[dict], chuva: list[dict]) -> list[dict]:
    """Linha 'dia' do INMET (dias distantes) recebe a chuva do Open-Meteo; senão entra a do Open-Meteo."""
    por_chave = {(l["municipio_id"], l["data"], l["periodo"]): l for l in previsao_inmet}
    for linha in chuva:
        chave = (linha["municipio_id"], linha["data"], "dia")
        if chave in por_chave:
            por_chave[chave]["chuva_prevista_mm"] = linha["chuva_prevista_mm"]
            por_chave[chave]["fonte"] += " + chuva: Open-Meteo"
        else:
            por_chave[chave] = linha
    return list(por_chave.values())


def coletar_meteorologia(cliente: Any, *, sessao: Any = requests, pausa: float = 0.3) -> dict[str, Any]:
    municipios = cliente.table("municipios").select("id_ibge,nome,latitude,longitude").execute().data or []
    codigos = {str(m["id_ibge"]).strip() for m in municipios}
    resumo: dict[str, Any] = {"avisos": 0, "previsoes": 0, "erros": []}

    try:
        resposta = sessao.get(URL_AVISOS, headers=CABECALHO, timeout=60)
        resposta.raise_for_status()
        avisos = avisos_para_linhas(resposta.json(), codigos)
        # Avisos vigentes substituem os anteriores (encerrados somem da tela).
        cliente.table("avisos_meteorologicos").delete().neq("codigo", "").execute()
        for inicio in range(0, len(avisos), 200):
            cliente.table("avisos_meteorologicos").upsert(avisos[inicio:inicio + 200], on_conflict="codigo,municipio_id").execute()
        resumo["avisos"] = len(avisos)
    except Exception as erro:
        LOGGER.exception("Avisos do INMET indisponíveis")
        resumo["erros"].append(f"avisos: {type(erro).__name__}")

    previsoes: list[dict] = []
    for municipio_id in sorted(codigos):
        try:
            resposta = sessao.get(URL_PREVISAO.format(codigo=municipio_id), headers=CABECALHO, timeout=60)
            resposta.raise_for_status()
            previsoes.extend(previsao_para_linhas(municipio_id, resposta.json()))
        except Exception as erro:
            resumo["erros"].append(f"previsão {municipio_id}: {type(erro).__name__}")
        if pausa:
            time.sleep(pausa)
    try:
        chuva = chuva_open_meteo(municipios, sessao)
    except Exception as erro:
        LOGGER.exception("Open-Meteo indisponível")
        resumo["erros"].append(f"open-meteo: {type(erro).__name__}")
        chuva = []
    linhas = _mesclar_dia(previsoes, chuva)
    hoje = date.today().isoformat()
    cliente.table("previsao_tempo").delete().lt("data", hoje).execute()
    for inicio in range(0, len(linhas), 300):
        cliente.table("previsao_tempo").upsert(linhas[inicio:inicio + 300], on_conflict="municipio_id,data,periodo").execute()
    resumo["previsoes"] = len(linhas)
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    cliente = create_client(url, chave)
    agora = datetime.now(timezone.utc).isoformat()
    try:
        resumo = coletar_meteorologia(cliente)
        LOGGER.info("Meteorologia: %s", {k: v for k, v in resumo.items() if k != "erros"})
        falhas = resumo["erros"]
        estado = {"status": "operacional" if not falhas or resumo["previsoes"] else "erro",
                  "ultima_verificacao": agora, "ultimo_erro": "; ".join(falhas[:5]) or None}
        if resumo["avisos"] or resumo["previsoes"]:
            estado["ultima_coleta"] = agora
    except Exception as erro:
        LOGGER.exception("Coleta meteorológica falhou")
        estado = {"status": "erro", "ultima_verificacao": agora, "ultimo_erro": f"{type(erro).__name__}: {erro}"[:500]}
    cliente.table("fontes").update(estado).eq("nome", NOME_FONTE).execute()
    return 0


if __name__ == "__main__":
    sys.exit(main())
