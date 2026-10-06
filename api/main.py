"""API pública somente leitura. Usa a chave anon/publishable: o RLS do banco
limita a resposta a municípios e alertas já enviados."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query

from core.indicador import calcular_indicador

AVISO = "Protótipo sem validação oficial; confirme nos órgãos oficiais."

app = FastAPI(
    title="API pública — Centro de Inteligência da Defesa Civil",
    description=AVISO,
    version="0.5.0",
)


@lru_cache(maxsize=1)
def _cliente() -> Any:
    from supabase import create_client

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not chave:
        raise RuntimeError("SUPABASE_URL/SUPABASE_ANON_KEY não configuradas")
    return create_client(url, chave)


def _consultar(funcao: Any) -> Any:
    try:
        return funcao(_cliente())
    except Exception as erro:
        raise HTTPException(status_code=503, detail="Fonte de dados indisponível") from erro


@app.get("/saude")
def saude() -> dict[str, str]:
    return {"status": "ok", "aviso": AVISO}


@app.get("/municipios")
def municipios(uf: str | None = Query(None, min_length=2, max_length=2)) -> dict[str, Any]:
    def consulta(cliente: Any) -> list[dict[str, Any]]:
        busca = cliente.table("municipios").select("id_ibge,nome,uf,populacao")
        if uf:
            busca = busca.eq("uf", uf.upper())
        return busca.order("nome").limit(1000).execute().data or []

    return {"aviso": AVISO, "dados": _consultar(consulta)}


@app.get("/alertas")
def alertas(limite: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    def consulta(cliente: Any) -> list[dict[str, Any]]:
        return (
            cliente.table("alertas")
            .select("id,municipio_id,classe,texto,emitido_em,status")
            .eq("status", "enviado")
            .order("emitido_em", desc=True)
            .limit(limite)
            .execute()
            .data
            or []
        )

    return {"aviso": AVISO, "dados": _consultar(consulta)}


@app.get("/indicador")
def indicador() -> dict[str, Any]:
    def consulta(cliente: Any) -> list[dict[str, Any]]:
        return cliente.rpc("indicador_latencia_publica").execute().data or []

    resumo = calcular_indicador(_consultar(consulta))
    return {"aviso": AVISO, "dados": resumo}
