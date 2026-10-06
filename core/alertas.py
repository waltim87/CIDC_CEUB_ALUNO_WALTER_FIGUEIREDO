"""Geração e ciclo de aprovação humana de alertas."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from dotenv import load_dotenv

from core.indice import ROTULOS
from core.regras import avaliar_regras


def formatar_fontes(fontes: list[dict[str, Any]] | None) -> str:
    entradas = []
    for fonte in fontes or []:
        if not isinstance(fonte, dict):
            continue
        nome = fonte.get("nome", fonte.get("fonte"))
        data_hora = fonte.get("data_hora_leitura")
        if nome:
            horario = data_hora or "horário da leitura não informado"
            entradas.append(f"{nome} ({horario})")
    return ", ".join(entradas) or "não informada"


def texto_sugerido(
    municipio: Mapping[str, Any],
    indice: Mapping[str, Any],
    regra: Mapping[str, Any],
) -> str:
    """Redige mensagem usando apenas dados do índice e da regra, sem criar fatos."""
    explicacao = indice.get("explicacao_json") or []
    partes = []
    for item in explicacao:
        nome = item.get("rotulo") or ROTULOS.get(
            item.get("componente"), item.get("componente", "Componente")
        )
        partes.append(
            f"{nome}: {float(item['score']):.1f}/100 "
            f"(peso aplicado {float(item['peso_percentual_aplicado']):.1f}%)"
        )
    componentes = "; ".join(partes) if partes else "componentes não disponíveis"
    local = municipio.get("nome", municipio.get("id_ibge", "Município não identificado"))
    uf = municipio.get("uf")
    if uf:
        local = f"{local}/{uf}"
    score = indice.get("score_total")
    score_texto = f"{float(score):.1f}/100" if score is not None else "indisponível"
    data_hora = indice.get("data_hora_leitura_referencia", "não informada")
    nomes_fontes = formatar_fontes(indice.get("fontes_json"))
    acao = regra.get("acao_recomendada", "Revisar a situação com a coordenação responsável.")
    return (
        f"SUGESTÃO DE ALERTA — revisão humana obrigatória\n"
        f"Município: {local}\n"
        f"Classe calculada: {regra['classe']} (índice {score_texto}).\n"
        f"Data/hora da leitura de referência: {data_hora}.\n"
        f"Fonte(s): {nomes_fontes}.\n"
        f"Componentes que contribuíram: {componentes}.\n"
        f"Ação recomendada pela regra: {acao}\n"
        "Protótipo sem validação oficial. Confirme leituras e orientações nos órgãos oficiais."
    )


def gerar_rascunhos(
    municipio: Mapping[str, Any],
    indice: Mapping[str, Any],
    regras: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not indice.get("id"):
        raise ValueError("O índice precisa estar persistido antes de gerar alertas")
    contexto = {**indice, **(indice.get("componentes") or {})}
    correspondentes = avaliar_regras(regras, contexto)
    return [
        {
            "municipio_id": indice["municipio_id"],
            "indice_id": indice["id"],
            "regra_id": regra["id"],
            "classe": regra["classe"],
            "texto": texto_sugerido(municipio, indice, regra),
            "canal": None,
            "status": "rascunho",
        }
        for regra in correspondentes
    ]


def criar_rascunhos_supabase(
    cliente: Any,
    municipio: Mapping[str, Any],
    indice: Mapping[str, Any],
    regras: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Insere rascunhos idempotentes; não envia notificações."""
    if regras is None:
        from core.regras import carregar_regras_supabase

        regras = carregar_regras_supabase(cliente)
    rascunhos = gerar_rascunhos(municipio, indice, regras)
    inseridos = []
    for rascunho in rascunhos:
        existente = (
            cliente.table("alertas")
            .select("id")
            .eq("indice_id", rascunho["indice_id"])
            .eq("regra_id", rascunho["regra_id"])
            .limit(1)
            .execute()
        )
        if existente.data:
            continue
        resposta = cliente.table("alertas").insert(rascunho).execute()
        if not resposta.data:
            raise RuntimeError("Supabase não retornou o alerta inserido")
        inseridos.append(resposta.data[0])
    return inseridos


def cliente_supabase():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente")
    from supabase import create_client

    return create_client(url, chave)


def listar_alertas(
    cliente: Any, *, status: str | None = None, limite: int = 200
) -> list[dict[str, Any]]:
    if not 1 <= limite <= 1000:
        raise ValueError("limite deve estar entre 1 e 1000")
    consulta = (
        cliente.table("alertas")
        .select(
            "id,municipio_id,indice_id,regra_id,classe,texto,canal,criado_em,"
            "emitido_em,status,aprovado_por"
        )
        .order("criado_em", desc=True)
        .limit(limite)
    )
    if status:
        consulta = consulta.eq("status", status)
    resultado = consulta.execute()
    alertas = resultado.data or []
    ids = sorted({alerta["municipio_id"] for alerta in alertas})
    if not ids:
        return alertas
    municipios = (
        cliente.table("municipios")
        .select("id_ibge,nome,uf")
        .in_("id_ibge", ids)
        .execute()
        .data
        or []
    )
    por_id = {municipio["id_ibge"].strip(): municipio for municipio in municipios}
    for alerta in alertas:
        alerta["municipio"] = por_id.get(alerta["municipio_id"].strip(), {})
    indice_ids = sorted(
        {alerta["indice_id"] for alerta in alertas if alerta.get("indice_id")}
    )
    if indice_ids:
        indices = (
            cliente.table("indices")
            .select("id,data_hora,data_hora_leitura_referencia,fontes_json")
            .in_("id", indice_ids)
            .execute()
            .data
            or []
        )
        indices_por_id = {indice["id"]: indice for indice in indices}
        for alerta in alertas:
            alerta["indice"] = indices_por_id.get(alerta.get("indice_id"), {})
    return alertas


def atualizar_alerta(
    cliente: Any,
    alerta_id: str,
    *,
    acao: str,
    texto: str | None = None,
    aprovado_por: str | None = None,
) -> dict[str, Any]:
    if acao not in {"aprovar", "rejeitar"}:
        raise ValueError("Ação deve ser 'aprovar' ou 'rejeitar'")
    if acao == "aprovar" and (not texto or not texto.strip()):
        raise ValueError("O texto do alerta aprovado não pode ficar vazio")
    payload: dict[str, Any] = {
        "status": "aprovado" if acao == "aprovar" else "rejeitado",
    }
    if acao == "aprovar":
        payload["texto"] = texto.strip()
        if aprovado_por:
            payload["aprovado_por"] = aprovado_por
    resultado = (
        cliente.table("alertas")
        .update(payload)
        .eq("id", alerta_id)
        .eq("status", "rascunho")
        .execute()
    )
    if not resultado.data:
        raise RuntimeError("Alerta não encontrado ou não está mais em rascunho")
    return resultado.data[0]


def marcar_enviado(
    cliente: Any, alerta_id: str, *, emitido_em: datetime | None = None
) -> dict[str, Any]:
    """Fase 3 não envia mensagens; permite registar envio externo aprovado."""
    instante = (emitido_em or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resultado = (
        cliente.table("alertas")
        .update({"status": "enviado", "emitido_em": instante.isoformat()})
        .eq("id", alerta_id)
        .eq("status", "aprovado")
        .execute()
    )
    if not resultado.data:
        raise RuntimeError("Somente alertas aprovados podem ser marcados como enviados")
    return resultado.data[0]
