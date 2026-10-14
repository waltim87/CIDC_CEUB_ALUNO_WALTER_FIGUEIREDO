"""Calcula cheia e seca históricas por estação a partir da série oficial da ANA.

Fonte: ServiceANA.asmx/HidroSerieHistorica (cotas diárias, tipoDados=1).
Regras (reprodutíveis):
- usa apenas dias desde ANO_INICIAL, evitando mudanças antigas de referência
  da régua;
- para o mesmo mês, prefere dado consistido (2) ao bruto (1);
- descarta picos isolados: dia que difere mais de LIMITE_PICO cm da mediana dos
  vizinhos (até 3 dias antes e depois), típicos de erro de digitação;
- confere a régua: a cota convencional do último dia disponível deve bater com
  a média da telemetria no mesmo dia (diferença máxima TOLERANCIA_REGUA cm).

Uso:  python scripts/extremos_historicos.py > saida.sql
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.ana import carregar_configuracao  # noqa: E402

URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
ANO_INICIAL = 1990
LIMITE_PICO = 150
TOLERANCIA_REGUA = 10


def _registros(texto: str, no: str) -> list[dict[str, str]]:
    return [
        {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
        for item in ET.fromstring(texto).iter()
        if item.tag.split("}")[-1] == no
    ]


def cotas_diarias(codigo: str) -> list[tuple[float, date, int]]:
    resposta = requests.get(
        f"{URL}/HidroSerieHistorica",
        params={"codEstacao": codigo, "dataInicio": "01/01/1900",
                "dataFim": date.today().strftime("%d/%m/%Y"), "tipoDados": 1,
                "nivelConsistencia": ""},
        timeout=180,
    )
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


def media_telemetria(codigo: str, dia: date) -> float | None:
    resposta = requests.get(
        f"{URL}/DadosHidrometeorologicos",
        params={"codEstacao": codigo, "dataInicio": f"{dia:%d/%m/%Y}", "dataFim": f"{dia:%d/%m/%Y}"},
        timeout=60,
    )
    resposta.raise_for_status()
    niveis = [float(r["Nivel"]) for r in _registros(resposta.text, "DadosHidrometereologicos") if r.get("Nivel")]
    return sum(niveis) / len(niveis) if niveis else None


def main() -> None:
    linhas = []
    for estacao in carregar_configuracao()["estacoes"]:
        codigo = estacao["codigo_oficial"]
        cotas = sem_picos(cotas_diarias(codigo))
        cheia = max(cotas, key=lambda c: c[0])
        seca = min(cotas, key=lambda c: c[0])
        ultimo = cotas[-1]
        telemetria = media_telemetria(codigo, ultimo[1])
        if telemetria is None or abs(telemetria - ultimo[0]) > TOLERANCIA_REGUA:
            print(f"-- {codigo}: régua não confere com a telemetria; estação ignorada", file=sys.stderr)
            continue
        fonte = (
            f"ANA HidroSerieHistorica {ANO_INICIAL}-{ultimo[1].year}, cotas diárias "
            f"(cheia {'consistida' if cheia[2] == 2 else 'bruta'}, "
            f"seca {'consistida' if seca[2] == 2 else 'bruta'}; picos isolados > {LIMITE_PICO} cm descartados; "
            f"régua conferida com telemetria em {ultimo[1]:%d/%m/%Y}: {ultimo[0]:g} x {telemetria:.1f} cm)"
        )
        linhas.append(
            f"    ('{codigo}', {cheia[0]:g}, date '{cheia[1]}', {seca[0]:g}, date '{seca[1]}', '{fonte}')"
        )
    print(",\n".join(linhas))


if __name__ == "__main__":
    main()
