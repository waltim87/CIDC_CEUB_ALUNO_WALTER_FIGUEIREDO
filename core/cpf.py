"""Validação e máscara de CPF (dígitos verificadores da Receita Federal)."""

from __future__ import annotations

import re


def limpar(cpf: str | None) -> str:
    return re.sub(r"\D", "", cpf or "")


def valido(cpf: str | None) -> bool:
    numeros = limpar(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(numeros[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[posicao]):
            return False
    return True


def formatar(cpf: str | None) -> str:
    n = limpar(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else (cpf or "")


def mascarar(cpf: str | None) -> str:
    """Exibe só os 5 últimos dígitos (padrão usado em documentos públicos)."""
    n = limpar(cpf)
    return f"***.***.{n[6:9]}-{n[9:]}" if len(n) == 11 else ""
