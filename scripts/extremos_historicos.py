"""Mostra cheia e seca históricas das estações do config, em formato de VALUES SQL.

As regras ficam em collectors/marcadores.py (mesmo cálculo usado pelo robô para
preencher estações sem marcadores). Útil para conferência manual.

Uso:  python scripts/extremos_historicos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.ana import carregar_configuracao  # noqa: E402
from collectors.marcadores import calcular_marcadores  # noqa: E402


def main() -> None:
    linhas = []
    for estacao in carregar_configuracao()["estacoes"]:
        codigo = estacao["codigo_oficial"]
        m = calcular_marcadores(codigo)
        if m is None:
            print(f"-- {codigo}: sem marcador confiável", file=sys.stderr)
            continue
        fonte = m["historico_fonte"].replace("'", "''")
        linhas.append(
            f"    ('{codigo}', {m['cheia_historica_cm']:g}, date '{m['cheia_historica_data']}', "
            f"{m['seca_historica_cm']:g}, date '{m['seca_historica_data']}', '{fonte}')"
        )
    print(",\n".join(linhas))


if __name__ == "__main__":
    main()
