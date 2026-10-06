"""Orquestra o índice e gera apenas rascunhos sujeitos a revisão humana."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from core.alertas import criar_rascunhos_supabase
from core.indice import construir_registro_indice, carregar_pesos_supabase, persistir_indice
from core.regras import carregar_regras_supabase


def calcular_e_gerar_rascunhos(
    cliente: Any,
    municipio_id: str,
    componentes: Mapping[str, float | int | None],
    *,
    fontes: list[dict[str, str]],
) -> dict[str, Any]:
    """Calcula e persiste um índice com proveniência, depois gera rascunhos."""
    if not fontes:
        raise ValueError("Informe ao menos uma fonte com data/hora das leituras usadas")
    instantes: list[datetime] = []
    for fonte in fontes:
        if not isinstance(fonte, dict):
            raise ValueError("Cada fonte precisa ser informada como um objeto")
        nome = fonte.get("nome")
        data_hora = fonte.get("data_hora_leitura")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("Cada fonte precisa informar um nome")
        if not isinstance(data_hora, str) or not data_hora:
            raise ValueError("Cada fonte precisa informar nome e data_hora_leitura")
        try:
            instante = datetime.fromisoformat(data_hora.replace("Z", "+00:00"))
        except ValueError as erro:
            raise ValueError(f"Data/hora inválida para a fonte {nome}") from erro
        if instante.tzinfo is None:
            raise ValueError(
                f"Data/hora da fonte {nome} precisa informar fuso horário"
            )
        instantes.append(instante.astimezone(timezone.utc))

    pesos, validacao_oficial = carregar_pesos_supabase(cliente)
    registro = construir_registro_indice(
        municipio_id,
        componentes,
        pesos=pesos,
        data_hora_leitura_referencia=max(instantes),
        fontes=fontes,
    )
    persistido = persistir_indice(cliente, registro)
    municipio_resultado = (
        cliente.table("municipios")
        .select("id_ibge,nome,uf")
        .eq("id_ibge", municipio_id)
        .single()
        .execute()
    )
    if not municipio_resultado.data:
        raise ValueError(f"Município IBGE {municipio_id} não encontrado")
    regras = carregar_regras_supabase(cliente)
    indice_para_alertas = {
        **registro,
        **persistido,
        "componentes": registro["explicacao_json"],
    }
    indice_para_alertas["componentes"] = registro.get("componentes", componentes)
    alertas = criar_rascunhos_supabase(
        cliente, municipio_resultado.data, indice_para_alertas, regras
    )
    return {
        "indice": persistido,
        "alertas": alertas,
        "pesos_validacao_oficial": validacao_oficial,
    }
