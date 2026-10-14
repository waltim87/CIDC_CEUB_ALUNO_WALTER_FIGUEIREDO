"""Gera a migration que cadastra as estações do inventário (sem duplicatas).

Entrada: JSON de scripts/inventario_estacoes_am.py. Os marcadores de cheia/seca
não entram aqui: o GitHub Actions os calcula e grava a cada execução
(python -m collectors.marcadores), inclusive quando o serviço histórico da ANA
estiver temporariamente fora do ar.

Uso:  python scripts/gerar_migration_estacoes.py inventario.json saida.sql
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path


def _sql_texto(valor: str | None) -> str:
    return "null" if valor is None else "'" + str(valor).replace("'", "''") + "'"


def main() -> None:
    inventario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    unicas = {e["codigo"]: e for e in inventario}  # a lista da ANA repete algumas estações
    linhas = [
        "    ({}, {}, {}, {}, {}, {})".format(
            _sql_texto(e["codigo"]), _sql_texto(e["nome"]), _sql_texto(e["rio"]),
            _sql_texto(e["municipio_id"]), e["lat"], e["lon"],
        )
        for e in sorted(unicas.values(), key=lambda e: e["codigo"])
    ]
    valores = ",\n".join(linhas)
    sql = f"""-- Estações telemétricas de rio da ANA no Amazonas que transmitiam nível em
-- {date.today():%d/%m/%Y}: {len(linhas)} estações em {len({e['municipio_id'] for e in unicas.values()})} municípios.
-- Gerado por scripts/inventario_estacoes_am.py + scripts/gerar_migration_estacoes.py.
-- Marcadores de cheia/seca: preenchidos automaticamente por collectors/marcadores.py.

alter table public.estacoes
    add column if not exists latitude double precision,
    add column if not exists longitude double precision;

insert into public.estacoes (codigo_oficial, fonte_id, nome, rio, municipio_id, latitude, longitude, geom)
select
    v.codigo, f.id, v.nome, v.rio, v.municipio_id, v.lat, v.lon,
    extensions.st_setsrid(extensions.st_makepoint(v.lon, v.lat), 4326)
from public.fontes f
cross join (
values
{valores}
) as v(codigo, nome, rio, municipio_id, lat, lon)
where f.nome = 'ANA HidroWebService'
on conflict (codigo_oficial) do update
set nome = excluded.nome,
    rio = excluded.rio,
    municipio_id = excluded.municipio_id,
    latitude = excluded.latitude,
    longitude = excluded.longitude,
    geom = excluded.geom;

-- O robô grava os marcadores históricos calculados (somente estas colunas).
grant update (
    cheia_historica_cm, cheia_historica_data, seca_historica_cm, seca_historica_data, historico_fonte
) on public.estacoes to service_role;
"""
    Path(sys.argv[2]).write_text(sql, encoding="utf-8")
    print(f"{len(linhas)} estações -> {sys.argv[2]}", file=sys.stderr)


if __name__ == "__main__":
    main()
