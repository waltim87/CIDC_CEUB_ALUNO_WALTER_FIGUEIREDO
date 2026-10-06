"""Cálculo explicável do Índice de Impacto Humanitário (hipótese configurável)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "pesos.yaml"
COMPONENTES = (
    "hidrologia",
    "populacao",
    "infraestrutura",
    "logistica",
    "vulnerabilidade",
)
COLUNAS = {
    "hidrologia": "score_hidrologia",
    "populacao": "score_populacao",
    "infraestrutura": "score_infra",
    "logistica": "score_logistica",
    "vulnerabilidade": "score_vulnerabilidade",
}
ROTULOS = {
    "hidrologia": "Hidrologia",
    "populacao": "População exposta",
    "infraestrutura": "Infraestrutura crítica",
    "logistica": "Logística",
    "vulnerabilidade": "Vulnerabilidade e duração",
}


class IndiceIndisponivelError(ValueError):
    """Não há componentes suficientes para calcular o índice."""


def carregar_pesos(caminho: Path = CONFIG_PATH) -> dict[str, Any]:
    """Lê os pesos de configuração versionada, não de constantes do cálculo."""
    with caminho.open(encoding="utf-8") as arquivo:
        configuracao = yaml.safe_load(arquivo)
    if not isinstance(configuracao, dict):
        raise ValueError(f"Configuração de pesos inválida em {caminho}")
    return configuracao


def validar_pesos(pesos: Mapping[str, float]) -> None:
    if set(pesos) != set(COMPONENTES):
        faltantes = sorted(set(COMPONENTES) - set(pesos))
        extras = sorted(set(pesos) - set(COMPONENTES))
        raise ValueError(f"Componentes de peso inválidos; faltantes={faltantes}, extras={extras}")
    for nome, peso in pesos.items():
        if isinstance(peso, bool) or not isinstance(peso, (int, float)):
            raise ValueError(f"Peso '{nome}' deve ser numérico")
        if not math.isfinite(peso) or peso < 0:
            raise ValueError(f"Peso '{nome}' deve ser finito e não negativo")
    if not math.isclose(sum(pesos.values()), 100.0, abs_tol=1e-6):
        raise ValueError("A soma dos pesos deve ser 100")


def classificar(score: float) -> str:
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("O score total deve estar entre 0 e 100")
    if score <= 20:
        return "Normal"
    if score <= 40:
        return "Atenção"
    if score <= 60:
        return "Alerta"
    if score <= 80:
        return "Alto"
    return "Crítico"


def calcular_indice(
    componentes: Mapping[str, float | int | None],
    *,
    pesos: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Calcula média ponderada dos componentes disponíveis e explica a contribuição.

    Pesos são lidos de ``config/pesos.yaml`` quando não fornecidos. Valores de
    componentes ausentes são excluídos e os pesos restantes são normalizados.
    Sem nenhum componente válido, o índice é indisponível em vez de presumir 0.
    """
    validacao_oficial = False
    if pesos is None:
        configuracao = carregar_pesos()
        pesos = configuracao.get("pesos", {})
        validacao_oficial = bool(configuracao.get("validacao_oficial", False))
    validar_pesos(pesos)
    desconhecidos = set(componentes) - set(COMPONENTES)
    if desconhecidos:
        raise ValueError(f"Componentes desconhecidos: {sorted(desconhecidos)}")

    observados: dict[str, float] = {}
    for nome in COMPONENTES:
        valor = componentes.get(nome)
        if valor is None:
            continue
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"Score '{nome}' deve ser numérico ou nulo")
        if not math.isfinite(valor) or not 0 <= valor <= 100:
            raise ValueError(f"Score '{nome}' deve estar entre 0 e 100")
        observados[nome] = float(valor)
    peso_total_observado = sum(float(pesos[nome]) for nome in observados)
    if not observados or peso_total_observado <= 0:
        raise IndiceIndisponivelError(
            "Não há componentes com peso positivo suficientes para calcular o índice"
        )

    contribuicoes = []
    score_total = 0.0
    for nome in COMPONENTES:
        if nome not in observados:
            continue
        participacao = float(pesos[nome]) / peso_total_observado
        pontos = observados[nome] * participacao
        score_total += pontos
        contribuicoes.append(
            {
                "componente": nome,
                "rotulo": ROTULOS[nome],
                "score": observados[nome],
                "peso_percentual_configurado": float(pesos[nome]),
                "peso_percentual_aplicado": participacao * 100,
                "contribuicao_pontos": pontos,
            }
        )
    contribuicoes.sort(key=lambda item: item["contribuicao_pontos"], reverse=True)
    return {
        "score_total": score_total,
        "classe": classificar(score_total),
        "componentes": observados,
        "explicacao": contribuicoes,
        "pesos_configurados": dict(pesos),
        "validacao_oficial": validacao_oficial,
        "dados_suficientes": True,
    }


def construir_registro_indice(
    municipio_id: str,
    componentes: Mapping[str, float | int | None],
    *,
    pesos: Mapping[str, float] | None = None,
    data_hora: datetime | None = None,
    data_hora_leitura_referencia: datetime | None = None,
    fontes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    calculado = calcular_indice(componentes, pesos=pesos)
    calculado["municipio_id"] = municipio_id
    calculado["data_hora"] = (
        data_hora or datetime.now(timezone.utc)
    ).astimezone(timezone.utc).isoformat()
    calculado["data_hora_leitura_referencia"] = (
        None
    )
    if data_hora_leitura_referencia:
        if data_hora_leitura_referencia.tzinfo is None:
            raise ValueError("A leitura de referência precisa informar fuso horário")
        calculado["data_hora_leitura_referencia"] = (
            data_hora_leitura_referencia.astimezone(timezone.utc).isoformat()
        )
    calculado["fontes_json"] = fontes or []
    calculado["explicacao_json"] = calculado.pop("explicacao")
    for nome, coluna in COLUNAS.items():
        calculado[coluna] = calculado["componentes"].get(nome)
    calculado.pop("componentes")
    calculado.pop("pesos_configurados")
    calculado.pop("dados_suficientes")
    return calculado


def carregar_pesos_supabase(cliente: Any) -> tuple[dict[str, float], bool]:
    """Obtém pesos ativos da linha de configuração persistida no Supabase."""
    resultado = (
        cliente.table("configuracao_pesos")
        .select("pesos_json,validacao_oficial")
        .eq("nome", "hipotese_inicial_indice_impacto_humanitario")
        .single()
        .execute()
    )
    dados = resultado.data
    if not isinstance(dados, dict) or not isinstance(dados.get("pesos_json"), dict):
        raise ValueError("Pesos do índice ausentes ou inválidos no Supabase")
    pesos = dados["pesos_json"]
    validar_pesos(pesos)
    return pesos, bool(dados.get("validacao_oficial", False))


def persistir_indice(cliente: Any, registro: dict[str, Any]) -> dict[str, Any]:
    payload = {
        chave: valor
        for chave, valor in registro.items()
        if chave in {"municipio_id", "data_hora", *COLUNAS.values(), "score_total", "classe"}
    }
    payload["explicacao_json"] = registro["explicacao_json"]
    payload["data_hora_leitura_referencia"] = registro.get(
        "data_hora_leitura_referencia"
    )
    payload["fontes_json"] = registro.get("fontes_json", [])
    resposta = cliente.table("indices").insert(payload).execute()
    if not resposta.data:
        raise RuntimeError("Supabase não retornou o índice inserido")
    return resposta.data[0]


def ler_indices(cliente: Any, *, limite: int = 500) -> list[dict[str, Any]]:
    if not 1 <= limite <= 5000:
        raise ValueError("limite deve estar entre 1 e 5000")
    resultado = (
        cliente.table("indices")
        .select(
            "id,municipio_id,data_hora,score_hidrologia,score_populacao,"
            "score_infra,score_logistica,score_vulnerabilidade,score_total,"
            "classe,explicacao_json,data_hora_leitura_referencia,fontes_json"
        )
        .order("data_hora", desc=True)
        .limit(limite)
        .execute()
    )
    return resultado.data or []
