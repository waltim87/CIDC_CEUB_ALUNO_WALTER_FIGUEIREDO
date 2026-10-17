"""Abre o painel no Streamlit Community Cloud e, se estiver dormindo, clica em acordar.

No plano gratuito o app dorme depois de um tempo sem visitas. Rodado pelo GitHub Actions
(.github/workflows/acordar.yml) algumas vezes por dia, com um navegador de verdade (Playwright):
uma requisição HTTP simples não conta como visita, porque não abre a sessão do app.
"""

from __future__ import annotations

import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL") or "https://sistematizacao-defesa-civil-walter-ceub-eng-ia.streamlit.app"
BOTAO_ACORDAR = re.compile(r"get this app back up|wake", re.IGNORECASE)
TEXTO_DO_APP = "Centro de Inteligência"   # título da tela de login e da página pública
ESPERA_MAXIMA_S = 240


def app_carregou(pagina) -> bool:
    # O app roda dentro de um iframe; procura o título em todos os quadros.
    for quadro in pagina.frames:
        try:
            if quadro.get_by_text(TEXTO_DO_APP).count():
                return True
        except Exception:
            continue
    return False


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pagina.wait_for_timeout(8_000)
        acordou = False
        inicio = time.monotonic()
        while time.monotonic() - inicio < ESPERA_MAXIMA_S:
            if app_carregou(pagina):
                print(f"App no ar ({'acordado agora' if acordou else 'já estava acordado'}) "
                      f"em {time.monotonic() - inicio:.0f} s")
                pagina.wait_for_timeout(15_000)   # mantém a sessão aberta um pouco: conta como visita
                navegador.close()
                return 0
            botao = pagina.get_by_role("button", name=BOTAO_ACORDAR)
            if not acordou and botao.count():
                print("App dormindo: clicando em acordar")
                botao.first.click()
                acordou = True
            pagina.wait_for_timeout(5_000)
        print(f"O app não carregou em {ESPERA_MAXIMA_S} s", file=sys.stderr)
        pagina.screenshot(path="acordar_falhou.png", full_page=True)
        navegador.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
