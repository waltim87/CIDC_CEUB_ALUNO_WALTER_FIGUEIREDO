"""Inventário das estações telemétricas de rio da ANA no Amazonas que transmitem nível.

1. Lista as estações ativas (ServiceANA ListaEstacoesTelemetricas) com UF = AM.
2. Para cada uma, consulta a telemetria das últimas 48 h e guarda só as que têm
   leitura de nível nas últimas 24 h.
3. Associa o município ao código IBGE (API de Localidades) pelo nome normalizado.

Saída: JSON em stdout (codigo, nome, rio, municipio_id, lat, lon, ultima_leitura).
Uso:  python scripts/inventario_estacoes_am.py > inventario.json
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
FUSO_ANA = timezone(timedelta(hours=-3))  # inferido; ver config/fontes.yaml
# Grafias da ANA que diferem do IBGE.
ALIASES = {"SANTA IZABEL DO RIO NEGRO": "SANTA ISABEL DO RIO NEGRO"}


def _linhas(texto: str, no: str) -> list[dict[str, str]]:
    return [
        {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
        for item in ET.fromstring(texto).iter()
        if item.tag.split("}")[-1] == no
    ]


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().replace("-", " ").replace("'", " ").split())


def municipios_ibge() -> dict[str, str]:
    dados = requests.get(
        "https://servicodados.ibge.gov.br/api/v1/localidades/estados/13/municipios", timeout=60
    ).json()
    return {_normalizar(m["nome"]): str(m["id"]) for m in dados}


def ultima_leitura_nivel(codigo: str, agora: datetime) -> datetime | None:
    resposta = requests.get(
        f"{URL}/DadosHidrometeorologicos",
        params={
            "codEstacao": codigo,
            "dataInicio": (agora - timedelta(days=2)).strftime("%d/%m/%Y"),
            "dataFim": agora.strftime("%d/%m/%Y"),
        },
        timeout=60,
    )
    resposta.raise_for_status()
    instantes = [
        datetime.fromisoformat(r["DataHora"].strip()).replace(tzinfo=FUSO_ANA)
        for r in _linhas(resposta.text, "DadosHidrometereologicos")
        if r.get("Nivel") and r.get("DataHora")
    ]
    return max(instantes) if instantes else None


def main() -> None:
    agora = datetime.now(timezone.utc)
    lista = requests.get(
        f"{URL}/ListaEstacoesTelemetricas", params={"statusEstacoes": 0, "origem": 0}, timeout=180
    )
    lista.raise_for_status()
    ibge = municipios_ibge()
    saida, sem_municipio = [], []
    # A lista da ANA repete algumas estações (uma linha por origem); deduplica pelo código.
    candidatas = list({
        r["CodEstacao"]: r for r in _linhas(lista.text, "Table")
        if r.get("Municipio-UF", "").endswith("-AM") and not r["CodEstacao"].startswith("00")
    }.values())
    print(f"{len(candidatas)} estações de rio no AM", file=sys.stderr)
    for r in candidatas:
        codigo = r["CodEstacao"]
        try:
            ultima = ultima_leitura_nivel(codigo, agora)
        except Exception as erro:
            print(f"{codigo}: falha {type(erro).__name__}", file=sys.stderr)
            continue
        time.sleep(0.3)
        if ultima is None or agora - ultima > timedelta(hours=24):
            print(f"{codigo} {r['NomeEstacao']}: sem nível nas últimas 24 h", file=sys.stderr)
            continue
        municipio = r["Municipio-UF"][: -len("-AM")]
        normalizado = _normalizar(municipio)
        municipio_id = ibge.get(ALIASES.get(normalizado, normalizado))
        if not municipio_id:
            sem_municipio.append(municipio)
        rio = r.get("NomeRio") or ""
        saida.append(
            {
                "codigo": codigo,
                "nome": r["NomeEstacao"],
                "rio": rio.replace("RIO ", "").title() if rio else None,
                "municipio": municipio,
                "municipio_id": municipio_id,
                "lat": float(r["Latitude"]),
                "lon": float(r["Longitude"]),
                "ultima_leitura_utc": ultima.astimezone(timezone.utc).isoformat(),
            }
        )
        print(f"{codigo} {r['NomeEstacao']}: OK", file=sys.stderr)
    if sem_municipio:
        print(f"Municípios sem código IBGE: {sorted(set(sem_municipio))}", file=sys.stderr)
    print(json.dumps(saida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
