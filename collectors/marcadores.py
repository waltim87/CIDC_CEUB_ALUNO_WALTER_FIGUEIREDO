"""Marcadores históricos de cheia e seca por estação (série oficial da ANA).

Fonte: ServiceANA.asmx/HidroSerieHistorica (cotas diárias, tipoDados=1).
Regras (reprodutíveis):
- usa apenas dias desde ANO_INICIAL, evitando mudanças antigas de referência da régua;
- para o mesmo mês, prefere dado consistido (2) ao bruto (1);
- descarta picos isolados: dia que difere mais de LIMITE_PICO cm da mediana dos
  vizinhos (até 3 dias antes e depois), típicos de erro de digitação;
- confere a régua: a cota convencional do último dia disponível deve bater com a
  média da telemetria no mesmo dia (diferença máxima TOLERANCIA_REGUA cm).

``python -m collectors.marcadores`` preenche, no Supabase, as estações que ainda
não têm marcadores (até MAX_POR_EXECUCAO por vez). Se o serviço histórico da ANA
estiver fora do ar, registra aviso e sai sem erro: tenta de novo na próxima execução.
"""

from __future__ import annotations

import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
ANO_INICIAL = 1990
LIMITE_PICO = 150
TOLERANCIA_REGUA = 10
DIAS_MINIMOS = 365
MAX_POR_EXECUCAO = 15


class SerieIndisponivelError(RuntimeError):
    """O serviço de série histórica da ANA não respondeu."""


def _registros(texto: str, no: str) -> list[dict[str, str]]:
    return [
        {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
        for item in ET.fromstring(texto).iter()
        if item.tag.split("}")[-1] == no
    ]


def cotas_diarias(codigo: str, sessao: Any = requests) -> list[tuple[float, date, int]]:
    resposta = sessao.get(
        f"{URL}/HidroSerieHistorica",
        params={"codEstacao": codigo, "dataInicio": "01/01/1900",
                "dataFim": date.today().strftime("%d/%m/%Y"), "tipoDados": 1,
                "nivelConsistencia": ""},
        timeout=180,
    )
    if resposta.status_code >= 500:
        raise SerieIndisponivelError(f"HTTP {resposta.status_code}")
    resposta.raise_for_status()
    meses: dict[str, tuple[int, dict[str, str]]] = {}
    for r in _registros(resposta.text, "SerieHistorica"):
        if not r.get("DataHora"):
            continue
        chave, nivel = r["DataHora"][:7], int(r.get("NivelConsistencia") or 1)
        if chave not in meses or nivel > meses[chave][0]:
            meses[chave] = (nivel, r)
    cotas = []
    for chave, (nivel, r) in meses.items():
        ano, mes = int(chave[:4]), int(chave[5:7])
        if ano < ANO_INICIAL:
            continue
        for dia in range(1, 32):
            valor = r.get(f"Cota{dia:02d}")
            if not valor:
                continue
            try:
                cotas.append((float(valor), date(ano, mes, dia), nivel))
            except ValueError:
                continue
    return sorted(cotas, key=lambda c: c[1])


def sem_picos(cotas: list[tuple[float, date, int]]) -> list[tuple[float, date, int]]:
    saida = []
    for i, cota in enumerate(cotas):
        vizinhos = sorted(
            v[0] for v in cotas[max(0, i - 3):i] + cotas[i + 1:i + 4]
            if abs((v[1] - cota[1]).days) <= 5
        )
        if len(vizinhos) >= 2 and abs(cota[0] - vizinhos[len(vizinhos) // 2]) > LIMITE_PICO:
            continue
        saida.append(cota)
    return saida


def media_telemetria(codigo: str, dia: date, sessao: Any = requests) -> float | None:
    resposta = sessao.get(
        f"{URL}/DadosHidrometeorologicos",
        params={"codEstacao": codigo, "dataInicio": f"{dia:%d/%m/%Y}", "dataFim": f"{dia:%d/%m/%Y}"},
        timeout=60,
    )
    resposta.raise_for_status()
    niveis = [float(r["Nivel"]) for r in _registros(resposta.text, "DadosHidrometereologicos") if r.get("Nivel")]
    return sum(niveis) / len(niveis) if niveis else None


def calcular_marcadores(codigo: str, sessao: Any = requests) -> dict[str, Any] | None:
    """Cheia/seca recordes com fonte; None se a série for curta ou a régua não conferir."""
    cotas = sem_picos(cotas_diarias(codigo, sessao))
    if len(cotas) < DIAS_MINIMOS:
        LOGGER.info("%s: série curta (%s dias); sem marcadores", codigo, len(cotas))
        return None
    cheia = max(cotas, key=lambda c: c[0])
    seca = min(cotas, key=lambda c: c[0])
    ultimo = cotas[-1]
    telemetria = media_telemetria(codigo, ultimo[1], sessao)
    if telemetria is None or abs(telemetria - ultimo[0]) > TOLERANCIA_REGUA:
        LOGGER.info("%s: régua não conferida com a telemetria; sem marcadores", codigo)
        return None
    return {
        "cheia_historica_cm": cheia[0],
        "cheia_historica_data": cheia[1].isoformat(),
        "seca_historica_cm": seca[0],
        "seca_historica_data": seca[1].isoformat(),
        "historico_fonte": (
            f"ANA HidroSerieHistorica {ANO_INICIAL}-{ultimo[1].year}, cotas diárias "
            f"(cheia {'consistida' if cheia[2] == 2 else 'bruta'}, "
            f"seca {'consistida' if seca[2] == 2 else 'bruta'}; picos isolados > {LIMITE_PICO} cm "
            f"descartados; régua conferida com telemetria em {ultimo[1]:%d/%m/%Y}: "
            f"{ultimo[0]:g} x {telemetria:.1f} cm)"
        ),
    }


def preencher_pendentes(cliente: Any, *, limite: int = MAX_POR_EXECUCAO, sessao: Any = requests) -> dict[str, int]:
    """Calcula marcadores das estações sem seca/cheia cadastradas; para no primeiro HTTP 5xx."""
    pendentes = (
        cliente.table("estacoes")
        .select("id,codigo_oficial,historico_fonte")
        .not_.is_("codigo_oficial", "null")
        .is_("seca_historica_cm", "null")
        .limit(200)
        .execute()
        .data
        or []
    )
    # Estações já avaliadas sem marcador confiável ficam marcadas e não são refeitas.
    pendentes = [p for p in pendentes if not (p.get("historico_fonte") or "").startswith("sem marcador")]
    resumo = {"pendentes": len(pendentes), "preenchidas": 0, "sem_marcador": 0, "erros": 0}
    for estacao in pendentes[:limite]:
        codigo = estacao["codigo_oficial"]
        try:
            valores = calcular_marcadores(codigo, sessao)
        except SerieIndisponivelError as erro:
            LOGGER.warning("Série histórica da ANA indisponível (%s); tenta na próxima execução", erro)
            break
        except Exception:
            LOGGER.exception("Falha ao calcular marcadores da estação %s", codigo)
            resumo["erros"] += 1
            continue
        if valores is None:
            valores = {"historico_fonte": f"sem marcador confiável em {date.today():%d/%m/%Y} (série curta ou régua divergente)"}
            resumo["sem_marcador"] += 1
        else:
            resumo["preenchidas"] += 1
        cliente.table("estacoes").update(valores).eq("id", estacao["id"]).execute()
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    LOGGER.info("Marcadores: %s", preencher_pendentes(create_client(url, chave)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
