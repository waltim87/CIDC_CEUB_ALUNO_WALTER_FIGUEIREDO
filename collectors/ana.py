"""Coletor da ANA HidroWebService.

Os detalhes de endpoint, autenticação e formato da resposta ficam em
``config/fontes.yaml``. O coletor se mantém desativado enquanto esses dados
oficiais não forem confirmados.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "fontes.yaml"
VALOR_PENDENTE = "CONFIRMAR"


class ConfiguracaoPendenteError(RuntimeError):
    """Indica que a integração ainda depende de confirmação na fonte oficial."""


def carregar_configuracao(caminho: Path = CONFIG_PATH) -> dict[str, Any]:
    """Carrega a configuração YAML do coletor ANA."""
    with caminho.open(encoding="utf-8") as arquivo:
        configuracao = yaml.safe_load(arquivo)
    if not isinstance(configuracao, dict) or not isinstance(configuracao.get("ana"), dict):
        raise ValueError(f"Configuração ANA ausente ou inválida em {caminho}")
    return configuracao["ana"]


def _caminho_valor(registro: Any, caminho: str) -> Any:
    valor = registro
    for parte in caminho.split("."):
        if isinstance(valor, dict) and parte in valor:
            valor = valor[parte]
        else:
            raise ValueError(f"Campo '{caminho}' não encontrado na resposta da ANA")
    return valor


def _data_hora_com_fuso(valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValueError("data_hora_leitura deve ser uma string ISO-8601")
    try:
        data_hora = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as erro:
        raise ValueError(f"Data/hora de leitura inválida: {valor}") from erro
    if data_hora.tzinfo is None:
        raise ValueError("data_hora_leitura precisa incluir fuso horário")
    return data_hora.astimezone(timezone.utc).isoformat()


def _numero_opcional(registro: Any, caminho: str | None) -> float | None:
    if caminho is None:
        return None
    valor = _caminho_valor(registro, caminho)
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"Valor numérico inválido em '{caminho}': {valor}") from erro


def normalizar_registros(
    registros: list[dict[str, Any]],
    *,
    codigo_estacao: str,
    campos: dict[str, str | None],
    coletado_em: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normaliza registros já extraídos segundo os caminhos confirmados em YAML."""
    coletado_em = coletado_em or datetime.now(timezone.utc)
    saida: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for registro in registros:
        data_hora = _data_hora_com_fuso(
            _caminho_valor(registro, campos["data_hora_leitura"])
        )
        if data_hora in vistos:
            continue
        vistos.add(data_hora)

        nivel_cm = _numero_opcional(registro, campos.get("nivel_cm"))
        vazao = _numero_opcional(registro, campos.get("vazao"))
        chuva_mm = _numero_opcional(registro, campos.get("chuva_mm"))
        if nivel_cm is None and vazao is None and chuva_mm is None:
            raise ValueError("Registro sem nível, vazão ou chuva")

        tendencia_caminho = campos.get("tendencia")
        tendencia = (
            _caminho_valor(registro, tendencia_caminho)
            if tendencia_caminho
            else None
        )
        saida.append(
            {
                "codigo_estacao": codigo_estacao,
                "data_hora_leitura": data_hora,
                "nivel_cm": nivel_cm,
                "vazao": vazao,
                "chuva_mm": chuva_mm,
                "tendencia": str(tendencia) if tendencia is not None else None,
                "coletado_em": coletado_em.astimezone(timezone.utc).isoformat(),
            }
        )
    return saida


def _validar_configuracao(configuracao: dict[str, Any]) -> None:
    obrigatorios = {
        "endpoint": configuracao.get("endpoint"),
        "status": configuracao.get("status"),
        "parametros": configuracao.get("parametros"),
        "autenticacao.tipo": configuracao.get("autenticacao", {}).get("tipo"),
    }
    resposta = configuracao.get("resposta", {})
    obrigatorios["resposta.caminho_registros"] = resposta.get("caminho_registros")
    campos = resposta.get("campos", {})
    obrigatorios["resposta.campos.data_hora_leitura"] = campos.get(
        "data_hora_leitura"
    )
    if not any(campos.get(campo) for campo in ("nivel_cm", "vazao", "chuva_mm")):
        obrigatorios["resposta.campos.medida"] = None

    pendentes = [
        nome for nome, valor in obrigatorios.items()
        if valor is None
        or valor == VALOR_PENDENTE
        or (isinstance(valor, str) and VALOR_PENDENTE in valor)
    ]
    if configuracao.get("status") != "ativo":
        pendentes.append("status deve ser 'ativo' após validação")
    autenticacao = configuracao.get("autenticacao", {})
    if autenticacao.get("tipo") == "cabecalho":
        for campo in ("nome_cabecalho", "variavel_ambiente", "prefixo"):
            valor = autenticacao.get(campo)
            if valor is None or valor == VALOR_PENDENTE:
                pendentes.append(f"autenticacao.{campo}")
    elif autenticacao.get("tipo") != "sem_autenticacao":
        pendentes.append("autenticacao.tipo deve ser confirmado")
    parametros = configuracao.get("parametros")
    if isinstance(parametros, dict):
        if any(
            valor is None
            or valor == VALOR_PENDENTE
            or (isinstance(valor, str) and VALOR_PENDENTE in valor)
            for valor in parametros.values()
        ):
            pendentes.append("parametros")
    else:
        pendentes.append("parametros deve ser um objeto")
    if isinstance(resposta.get("caminho_registros"), str) and VALOR_PENDENTE in resposta[
        "caminho_registros"
    ]:
        pendentes.append("resposta.caminho_registros")
    if any(
        caminho == VALOR_PENDENTE
        or (isinstance(caminho, str) and VALOR_PENDENTE in caminho)
        for caminho in campos.values()
    ):
        pendentes.append("resposta.campos")
    estacoes = configuracao.get("estacoes", [])
    if not estacoes:
        pendentes.append("estacoes")
    for indice, estacao in enumerate(estacoes):
        if estacao.get("codigo_oficial") in (None, VALOR_PENDENTE):
            pendentes.append(f"estacoes[{indice}].codigo_oficial")
    if pendentes:
        raise ConfiguracaoPendenteError(
            "Coleta ANA bloqueada; confirme na documentação oficial: "
            + ", ".join(pendentes)
        )


def _extrair_registros(payload: Any, caminho: str) -> list[dict[str, Any]]:
    if caminho:
        payload = _caminho_valor(payload, caminho)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("A resposta ANA não contém uma lista de registros reconhecida")
    return payload


def coletar(
    configuracao: dict[str, Any] | None = None,
    *,
    sessao: Any = requests,
) -> list[dict[str, Any]]:
    """Busca leituras das estações configuradas, isolando falhas por estação."""
    configuracao = configuracao or carregar_configuracao()
    _validar_configuracao(configuracao)

    autenticacao = configuracao.get("autenticacao", {})
    headers: dict[str, str] = {}
    if autenticacao.get("nome_cabecalho") not in (None, ""):
        variavel = autenticacao.get("variavel_ambiente")
        token = os.environ.get(variavel) if variavel else None
        if not token:
            raise ConfiguracaoPendenteError(
                f"Defina a variável de ambiente {variavel or 'de autenticação da ANA'}"
            )
        prefixo = autenticacao.get("prefixo", "")
        headers[autenticacao["nome_cabecalho"]] = f"{prefixo}{token}"

    resultado: list[dict[str, Any]] = []
    falhas = 0
    for estacao in configuracao["estacoes"]:
        codigo = str(estacao["codigo_oficial"])
        parametros = {
            chave: str(valor).replace("{codigo_oficial}", codigo)
            for chave, valor in configuracao["parametros"].items()
        }
        try:
            resposta_http = sessao.get(
                configuracao["endpoint"],
                params=parametros,
                headers=headers,
                timeout=30,
            )
            resposta_http.raise_for_status()
            payload = resposta_http.json()
            registros = _extrair_registros(
                payload, configuracao["resposta"]["caminho_registros"]
            )
            leituras = normalizar_registros(
                registros,
                codigo_estacao=codigo,
                campos=configuracao["resposta"]["campos"],
            )
            resultado.extend(leituras)
        except Exception:
            falhas += 1
            LOGGER.exception("Falha ao coletar a estação ANA %s; seguindo para a próxima", codigo)
    if falhas == len(configuracao["estacoes"]):
        raise RuntimeError(
            f"Falha em todas as {falhas} estações configuradas da ANA"
        )
    return resultado


def persistir_no_supabase(
    leituras: list[dict[str, Any]],
    *,
    configuracao: dict[str, Any] | None = None,
) -> int:
    """Faz upsert de leituras no Supabase sem expor credenciais no código."""
    if not leituras:
        return 0

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    chave = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not chave:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente")

    from supabase import create_client

    configuracao = configuracao or carregar_configuracao()
    cliente = create_client(url, chave)
    fonte_resultado = (
        cliente.table("fontes")
        .select("id")
        .eq("nome", configuracao["nome"])
        .single()
        .execute()
    )
    fonte_id = fonte_resultado.data["id"]
    persistidas = 0

    for leitura in leituras:
        estacao_resultado = (
            cliente.table("estacoes")
            .select("id")
            .eq("codigo_oficial", leitura["codigo_estacao"])
            .single()
            .execute()
        )
        valores = {
            chave_coluna: leitura[chave_coluna]
            for chave_coluna in (
                "data_hora_leitura",
                "nivel_cm",
                "vazao",
                "chuva_mm",
                "tendencia",
                "coletado_em",
            )
        }
        valores.update(estacao_id=estacao_resultado.data["id"], fonte_id=fonte_id)
        cliente.table("leituras").upsert(
            valores, on_conflict="estacao_id,data_hora_leitura"
        ).execute()
        persistidas += 1
    return persistidas


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    try:
        leituras = coletar()
        quantidade = persistir_no_supabase(leituras)
    except Exception:
        LOGGER.exception("Execução do coletor ANA interrompida")
        raise
    LOGGER.info("%s leitura(s) gravada(s) no Supabase", quantidade)


if __name__ == "__main__":
    main()
