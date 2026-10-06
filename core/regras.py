"""Avaliação declarativa de regras do motor de alertas."""

from __future__ import annotations

import operator
from typing import Any, Mapping

COMPARADORES = {
    "igual": operator.eq,
    "maior_que": operator.gt,
    "maior_ou_igual": operator.ge,
    "menor_que": operator.lt,
    "menor_ou_igual": operator.le,
}


def regra_corresponde(condicao: Mapping[str, Any], contexto: Mapping[str, Any]) -> bool:
    """Avalia condição escalar estruturada; nunca usa eval."""
    campo = condicao.get("campo")
    comparador = condicao.get("operador")
    esperado = condicao.get("valor")
    if not isinstance(campo, str) or campo not in contexto:
        return False
    atual = contexto[campo]
    if atual is None:
        return False
    if comparador == "entre":
        if (
            not isinstance(esperado, list)
            or len(esperado) != 2
            or not all(isinstance(valor, (int, float)) for valor in esperado)
            or not isinstance(atual, (int, float))
        ):
            return False
        inferior, superior = esperado
        return inferior <= atual <= superior
    funcao = COMPARADORES.get(comparador)
    if funcao is None:
        return False
    try:
        return bool(funcao(atual, esperado))
    except TypeError:
        return False


def avaliar_regras(
    regras: list[dict[str, Any]], contexto: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Retorna apenas regras ativas que correspondam ao contexto calculado."""
    correspondentes = []
    for regra in regras:
        if regra.get("ativa") is not True:
            continue
        condicao = regra.get("condicao_json")
        if isinstance(condicao, dict) and regra_corresponde(condicao, contexto):
            correspondentes.append(regra)
    return correspondentes


def carregar_regras_supabase(cliente: Any) -> list[dict[str, Any]]:
    resultado = (
        cliente.table("regras")
        .select("id,condicao_json,classe,acao_recomendada,reavaliar_em_horas,ativa")
        .eq("ativa", True)
        .execute()
    )
    return resultado.data or []
