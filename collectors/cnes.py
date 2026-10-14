"""Estabelecimentos de saúde do CNES (Ministério da Saúde, dados abertos).

``python -m collectors.cnes`` importa para ``public.infraestrutura`` os
estabelecimentos de ATENDIMENTO do Amazonas (postos, UBS, hospitais, pronto
atendimento, unidades móveis fluviais, saúde indígena...) com nome, endereço,
telefone, e-mail, coordenadas e capacidades (internação, cirurgia, parto).
Roda no GitHub Actions, mas só reimporta se a última coleta tiver mais de
INTERVALO_DIAS (dados cadastrais mudam pouco; evita sobrecarregar a API).

API: https://apidadosabertos.saude.gov.br/cnes/estabelecimentos (sem chave,
20 registros por página, filtros codigo_uf e codigo_tipo_unidade).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from collectors.comum import coletar_configurado, carregar_configuracao

LOGGER = logging.getLogger(__name__)
URL = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
NOME_FONTE = "CNES Dados Abertos"
UF_AM = 13
POR_PAGINA = 20
MAX_PAGINAS_POR_TIPO = 60
INTERVALO_DIAS = 7
# Tipos de unidade com atendimento à população (tabela oficial /cnes/tipounidades).
TIPOS_ATENDIMENTO = {
    1: "Posto de saúde",
    2: "Centro de saúde / UBS",
    4: "Policlínica",
    5: "Hospital geral",
    7: "Hospital especializado",
    15: "Unidade mista",
    20: "Pronto-socorro geral",
    21: "Pronto-socorro especializado",
    32: "Unidade móvel fluvial",
    40: "Unidade móvel terrestre",
    42: "Unidade móvel de urgência (pré-hospitalar)",
    61: "Centro de parto normal",
    62: "Hospital-dia",
    72: "Unidade de atenção à saúde indígena",
    73: "Pronto atendimento",
}


def coletar(configuracao: dict[str, Any] | None = None, *, sessao: Any = requests) -> list[dict[str, Any]]:
    """Adaptador genérico configurável (mantido por compatibilidade com config/fontes.yaml)."""
    return coletar_configurado("cnes", configuracao or carregar_configuracao("cnes"), sessao=sessao)


def _texto(valor: Any) -> str | None:
    texto = " ".join(str(valor or "").split())
    return texto or None


def _telefone(valor: Any) -> str | None:
    texto = _texto(valor)
    if not texto or not any(c.isdigit() for c in texto):
        return None
    return texto.replace("( ", "(").replace(" )", ")")


def normalizar(registro: dict[str, Any], municipios: dict[str, str]) -> dict[str, Any] | None:
    """Registro da API -> linha de public.infraestrutura (None se o município não for do AM)."""
    municipio_id = municipios.get(str(registro.get("codigo_municipio") or ""))
    if not municipio_id or not registro.get("codigo_cnes"):
        return None
    endereco = ", ".join(
        p for p in (_texto(registro.get("endereco_estabelecimento")), _texto(registro.get("numero_estabelecimento"))) if p
    )
    lat, lon = registro.get("latitude_estabelecimento_decimo_grau"), registro.get("longitude_estabelecimento_decimo_grau")
    coordenadas_validas = isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and bool(lat) and bool(lon)
    return {
        "tipo": "ubs",
        "cnes_codigo": str(registro["codigo_cnes"]),
        "nome": _texto(registro.get("nome_fantasia")) or _texto(registro.get("nome_razao_social")) or "Sem nome",
        "municipio_id": municipio_id,
        "tipo_unidade": TIPOS_ATENDIMENTO.get(registro.get("codigo_tipo_unidade"), str(registro.get("codigo_tipo_unidade"))),
        "endereco": endereco or None,
        "bairro": _texto(registro.get("bairro_estabelecimento")),
        "cep": _texto(registro.get("codigo_cep_estabelecimento")),
        "telefone": _telefone(registro.get("numero_telefone_estabelecimento")),
        "email": (_texto(registro.get("endereco_email_estabelecimento")) or "").lower() or None,
        "esfera": _texto(registro.get("descricao_esfera_administrativa")),
        "turno": _texto(registro.get("descricao_turno_atendimento")),
        "atendimento_hospitalar": bool(registro.get("estabelecimento_possui_atendimento_hospitalar")),
        "centro_cirurgico": bool(registro.get("estabelecimento_possui_centro_cirurgico")),
        "centro_obstetrico": bool(registro.get("estabelecimento_possui_centro_obstetrico")),
        "latitude": float(lat) if coordenadas_validas else None,
        "longitude": float(lon) if coordenadas_validas else None,
        "geom": f"SRID=4326;POINT({lon} {lat})" if coordenadas_validas else None,
        "fonte": f"CNES/DATASUS (atualizado na base em {registro.get('data_atualizacao') or 'n/d'})",
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }


def baixar_estabelecimentos(sessao: Any = requests, pausa: float = 0.2) -> list[dict[str, Any]]:
    registros: list[dict[str, Any]] = []
    for tipo in TIPOS_ATENDIMENTO:
        for pagina in range(MAX_PAGINAS_POR_TIPO):
            resposta = sessao.get(
                URL,
                params={"codigo_uf": UF_AM, "codigo_tipo_unidade": tipo,
                        "limit": POR_PAGINA, "offset": pagina * POR_PAGINA},
                timeout=60,
            )
            resposta.raise_for_status()
            lote = resposta.json().get("estabelecimentos") or []
            registros.extend(r for r in lote if r.get("codigo_uf") == UF_AM)
            if len(lote) < POR_PAGINA:
                break
            if pausa:
                time.sleep(pausa)
    return registros


def importar(cliente: Any, *, sessao: Any = requests, forcar: bool = False, agora: datetime | None = None) -> dict[str, Any]:
    agora = agora or datetime.now(timezone.utc)
    fonte = cliente.table("fontes").select("ultima_coleta").eq("nome", NOME_FONTE).limit(1).execute().data or [{}]
    ultima = fonte[0].get("ultima_coleta")
    if ultima and not forcar:
        instante = datetime.fromisoformat(str(ultima).replace("Z", "+00:00"))
        if agora - instante < timedelta(days=INTERVALO_DIAS):
            return {"status": "em_dia", "ultima_coleta": ultima}
    # Código do município no CNES = IBGE sem o dígito verificador.
    municipios = {
        str(m["id_ibge"]).strip()[:6]: str(m["id_ibge"]).strip()
        for m in cliente.table("municipios").select("id_ibge").execute().data or []
    }
    linhas = [l for l in (normalizar(r, municipios) for r in baixar_estabelecimentos(sessao)) if l]
    unicas = list({l["cnes_codigo"]: l for l in linhas}.values())
    for inicio in range(0, len(unicas), 200):
        cliente.table("infraestrutura").upsert(unicas[inicio:inicio + 200], on_conflict="cnes_codigo").execute()
    cliente.table("fontes").update(
        {"status": "operacional", "ultima_coleta": agora.isoformat(),
         "ultima_verificacao": agora.isoformat(), "ultimo_erro": None}
    ).eq("nome", NOME_FONTE).execute()
    return {"status": "importado", "estabelecimentos": len(unicas),
            "municipios": len({l["municipio_id"] for l in unicas})}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from supabase import create_client

    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        LOGGER.error("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY")
        return 1
    cliente = create_client(url, chave)
    try:
        LOGGER.info("CNES: %s", importar(cliente, forcar="--forcar" in sys.argv))
    except Exception as erro:
        # Fonte isolada: falha do CNES não derruba a coleta; fica registrada na saúde das fontes.
        LOGGER.exception("Importação do CNES falhou")
        cliente.table("fontes").update(
            {"status": "erro", "ultima_verificacao": datetime.now(timezone.utc).isoformat(),
             "ultimo_erro": f"{type(erro).__name__}: {erro}"[:500]}
        ).eq("nome", NOME_FONTE).execute()
    return 0


if __name__ == "__main__":
    sys.exit(main())
