"""Funções compartilhadas para adaptadores de fontes configuradas em YAML."""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "fontes.yaml"
VALOR_PENDENTE = "CONFIRMAR"


class ConfiguracaoPendenteError(RuntimeError):
    """A fonte não pode ser consultada antes de confirmar os metadados oficiais."""


def carregar_configuracao(fonte: str, caminho: Path = CONFIG_PATH) -> dict[str, Any]:
    with caminho.open(encoding="utf-8") as arquivo:
        configuracoes = yaml.safe_load(arquivo)
    if not isinstance(configuracoes, dict) or not isinstance(configuracoes.get(fonte), dict):
        raise ValueError(f"Configuração ausente para a fonte '{fonte}' em {caminho}")
    return configuracoes[fonte]


def _pendente(valor: Any) -> bool:
    return valor is None or (
        isinstance(valor, str) and VALOR_PENDENTE in valor
    )


def validar_configuracao(configuracao: dict[str, Any]) -> None:
    pendencias = []
    for campo in ("nome", "status", "endpoint", "formato", "caminho_registros"):
        if _pendente(configuracao.get(campo)):
            pendencias.append(campo)
    if configuracao.get("status") != "ativo":
        pendencias.append("status deve ser 'ativo' após confirmação oficial")
    formato = configuracao.get("formato")
    if formato not in ("json", "csv"):
        pendencias.append("formato deve ser 'json' ou 'csv'")
    if formato in ("json", "csv"):
        campos = configuracao.get("campos")
        if not isinstance(campos, dict) or not campos:
            pendencias.append("campos deve mapear os campos normalizados")
        elif any(_pendente(valor) for valor in campos.values()):
            pendencias.append("campos contém valores não confirmados")
    if configuracao.get("autenticacao", {}).get("tipo", "sem_autenticacao") == "CONFIRMAR":
        pendencias.append("autenticacao.tipo")
    if pendencias:
        raise ConfiguracaoPendenteError(
            "Coleta bloqueada; confirme na documentação oficial: "
            + ", ".join(dict.fromkeys(pendencias))
        )


def _extrair_caminho(payload: Any, caminho: str) -> Any:
    if caminho == "":
        return payload
    valor = payload
    for parte in caminho.split("."):
        if isinstance(valor, dict) and parte in valor:
            valor = valor[parte]
        else:
            raise ValueError(f"Caminho '{caminho}' não encontrado na resposta")
    return valor


def _valor_campo(registro: dict[str, Any], caminho: Any) -> Any:
    if not isinstance(caminho, str):
        return caminho
    valor: Any = registro
    for parte in caminho.split("."):
        if isinstance(valor, dict) and parte in valor:
            valor = valor[parte]
        else:
            raise ValueError(f"Campo '{caminho}' não encontrado no registro")
    return valor


def normalizar_registros(
    registros: list[dict[str, Any]],
    *,
    nome_fonte: str,
    campos: dict[str, Any],
    coletado_em: datetime | None = None,
) -> list[dict[str, Any]]:
    """Projeta campos configurados e acrescenta metadados de proveniência."""
    instante_coleta = (coletado_em or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    resultado: list[dict[str, Any]] = []
    for registro in registros:
        normalizado = {
            destino: _valor_campo(registro, caminho)
            for destino, caminho in campos.items()
        }
        normalizado["fonte"] = nome_fonte
        normalizado["coletado_em"] = instante_coleta.isoformat()
        resultado.append(normalizado)
    return resultado


def coletar_configurado(
    fonte: str,
    configuracao: dict[str, Any] | None = None,
    *,
    sessao: Any = requests,
) -> list[dict[str, Any]]:
    """Busca JSON/CSV de um adaptador e normaliza seus campos configurados."""
    configuracao = configuracao or carregar_configuracao(fonte)
    validar_configuracao(configuracao)

    headers: dict[str, str] = {}
    autenticacao = configuracao.get("autenticacao", {})
    tipo_autenticacao = autenticacao.get("tipo", "sem_autenticacao")
    if tipo_autenticacao == "cabecalho":
        variavel = autenticacao.get("variavel_ambiente")
        nome_cabecalho = autenticacao.get("nome_cabecalho")
        if not variavel or not nome_cabecalho:
            raise ConfiguracaoPendenteError(
                "Confirme nome_cabecalho e variavel_ambiente da autenticação"
            )
        token = os.environ.get(variavel)
        if not token:
            raise ConfiguracaoPendenteError(f"Defina a variável de ambiente {variavel}")
        prefixo = autenticacao.get("prefixo", "")
        headers[nome_cabecalho] = f"{prefixo}{token}"
    elif tipo_autenticacao != "sem_autenticacao":
        raise ConfiguracaoPendenteError(
            f"Tipo de autenticação não suportado ou pendente: {tipo_autenticacao}"
        )

    resposta = sessao.get(
        configuracao["endpoint"],
        params=configuracao.get("parametros"),
        headers=headers,
        timeout=30,
    )
    resposta.raise_for_status()
    if configuracao["formato"] == "json":
        payload = _extrair_caminho(
            resposta.json(), configuracao["caminho_registros"]
        )
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) for item in payload
        ):
            raise ValueError("A resposta configurada não contém uma lista JSON de objetos")
        registros = payload
    else:
        texto = getattr(resposta, "text", None)
        if not isinstance(texto, str):
            raise ValueError("A resposta CSV não contém texto")
        leitor = csv.DictReader(io.StringIO(texto))
        if not leitor.fieldnames:
            raise ValueError("O CSV não contém cabeçalho")
        linhas = list(leitor)
        caminho = configuracao["caminho_registros"]
        if caminho not in ("", None):
            raise ValueError("CSV deve usar caminho_registros vazio")
        registros = [dict(linha) for linha in linhas]

    return normalizar_registros(
        registros,
        nome_fonte=configuracao["nome"],
        campos=configuracao["campos"],
    )
