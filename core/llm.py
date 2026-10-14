"""Redação de textos pela IA (Gemini, camada gratuita) com proteção contra números inventados.

A IA recebe apenas fatos estruturados e devolve um texto curto em linguagem
simples. O texto é rejeitado se citar qualquer número que não esteja nos fatos;
nesse caso, ou se a API falhar, usa-se o modelo de texto fixo. Toda saída é
triagem indicativa e exige revisão humana.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

import requests

LOGGER = logging.getLogger(__name__)
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MAX_CARACTERES = 900

INSTRUCOES = (
    "Você é assistente da Defesa Civil do Amazonas. Escreva em português do Brasil, "
    "em linguagem simples, de 2 a 4 frases, uma análise da situação hidrológica do "
    "município usando SOMENTE os fatos em JSON. Regras: não invente números, datas, "
    "previsões ou causas; cite números exatamente como aparecem nos fatos; diga que "
    "é triagem indicativa sem validação oficial; não dê ordens de evacuação. "
    "Responda apenas com o texto, sem títulos nem listas."
)

_NUMERO = re.compile(r"-?\d+(?:[.,]\d+)?")


def _normalizar_numero(texto: str) -> str:
    # Valor absoluto: o texto expressa o sinal em palavras ("caindo 35 cm" para -35).
    valor = abs(float(texto.replace(",", ".")))
    return f"{valor:g}"


def numeros_permitidos(fatos: Any) -> set[str]:
    """Todos os números presentes nos fatos (inclusive dentro de datas e textos)."""
    return {_normalizar_numero(n) for n in _NUMERO.findall(json.dumps(fatos, ensure_ascii=False))}


def texto_respeita_fatos(texto: str, fatos: Any) -> bool:
    permitidos = numeros_permitidos(fatos)
    return all(_normalizar_numero(n) in permitidos for n in _NUMERO.findall(texto))


def chamar_gemini(
    fatos: dict[str, Any],
    *,
    chave: str,
    modelo: str,
    timeout: int = 30,
    sessao: Any = requests,
) -> str:
    resposta = sessao.post(
        URL_GEMINI.format(modelo=modelo),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave},
        json={
            "systemInstruction": {"parts": [{"text": INSTRUCOES}]},
            "contents": [{"parts": [{"text": json.dumps(fatos, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 300},
        },
        timeout=timeout,
    )
    resposta.raise_for_status()
    payload = resposta.json()
    try:
        texto = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as erro:
        raise ValueError("Resposta do Gemini sem texto") from erro
    return " ".join(str(texto).split())[:MAX_CARACTERES]


def gerar_texto(
    fatos: dict[str, Any],
    texto_fixo: str,
    *,
    modelo: str,
    variavel_chave: str = "GEMINI_API_KEY",
    timeout: int = 30,
    chamador: Callable[..., str] = chamar_gemini,
) -> tuple[str, str, str | None]:
    """Retorna (texto, metodo, modelo). metodo é 'ia' ou 'modelo_fixo'."""
    chave = os.environ.get(variavel_chave, "").strip()
    if not chave:
        return texto_fixo, "modelo_fixo", None
    try:
        texto = chamador(fatos, chave=chave, modelo=modelo, timeout=timeout)
    except Exception as erro:  # a falha da IA nunca interrompe o robô
        LOGGER.warning("IA indisponível (%s); usando modelo fixo", type(erro).__name__)
        return texto_fixo, "modelo_fixo", None
    if not texto or not texto_respeita_fatos(texto, fatos):
        LOGGER.warning("Texto da IA citou números fora dos fatos; usando modelo fixo")
        return texto_fixo, "modelo_fixo", None
    return texto, "ia", modelo
