"""Coletor da ANA (Telemetria - ServiceANA.asmx/DadosHidrometeorologicos).

Os detalhes de endpoint, autenticação e formato da resposta ficam em
``config/fontes.yaml``. O coletor se mantém desativado enquanto esses dados
não forem confirmados. Suporta respostas JSON (caminhos configurados) e o XML
público da telemetria da ANA (``formato: xml``).
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

from collectors.comum import ConfiguracaoPendenteError

LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "fontes.yaml"
VALOR_PENDENTE = "CONFIRMAR"
TAMANHO_MAXIMO_XML = 2 * 1024 * 1024
NO_REGISTRO_XML = "DadosHidrometereologicos"
TAMANHO_LOTE_UPSERT = 500


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


def _fuso(valor: str | None) -> timezone | None:
    """Converte um deslocamento '-03:00' em timezone; None mantém a exigência de fuso."""
    if valor in (None, ""):
        return None
    try:
        return datetime.fromisoformat(f"2000-01-01T00:00:00{valor}").tzinfo  # type: ignore[return-value]
    except ValueError as erro:
        raise ValueError(f"fuso_horario_fonte inválido: {valor}") from erro


def _data_hora_com_fuso(valor: Any, fuso_padrao: timezone | None = None) -> str:
    if not isinstance(valor, str):
        raise ValueError("data_hora_leitura deve ser uma string ISO-8601")
    try:
        data_hora = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError as erro:
        raise ValueError(f"Data/hora de leitura inválida: {valor}") from erro
    if data_hora.tzinfo is None:
        if fuso_padrao is None:
            raise ValueError("data_hora_leitura precisa incluir fuso horário")
        data_hora = data_hora.replace(tzinfo=fuso_padrao)
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
    fuso_padrao: timezone | None = None,
    ignorar_sem_medida: bool = False,
) -> list[dict[str, Any]]:
    """Normaliza registros já extraídos segundo os caminhos confirmados em YAML.

    ``fuso_padrao`` só é aplicado a horários sem fuso explícito.
    ``ignorar_sem_medida`` descarta linhas sem nível, vazão nem chuva (comuns na
    telemetria da ANA) em vez de abortar a estação inteira.
    """
    coletado_em = coletado_em or datetime.now(timezone.utc)
    saida: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for registro in registros:
        data_hora = _data_hora_com_fuso(
            _caminho_valor(registro, campos["data_hora_leitura"]), fuso_padrao
        )
        if data_hora in vistos:
            continue

        nivel_cm = _numero_opcional(registro, campos.get("nivel_cm"))
        vazao = _numero_opcional(registro, campos.get("vazao"))
        chuva_mm = _numero_opcional(registro, campos.get("chuva_mm"))
        if nivel_cm is None and vazao is None and chuva_mm is None:
            if ignorar_sem_medida:
                continue
            raise ValueError("Registro sem nível, vazão ou chuva")
        vistos.add(data_hora)

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

    if configuracao.get("formato", "json") not in ("json", "xml"):
        obrigatorios["formato (json ou xml)"] = None

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


def _nome_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extrair_registros_xml(texto: str, codigo_estacao: str) -> list[dict[str, str]]:
    """Extrai as linhas DadosHidrometereologicos do XML da telemetria da ANA."""
    if len(texto.encode("utf-8")) > TAMANHO_MAXIMO_XML:
        raise ValueError("XML da ANA excede o limite de segurança de 2 MiB")
    if "<!DOCTYPE" in texto or "<!ENTITY" in texto:
        raise ValueError("XML da ANA com DTD/entidades não é aceito")
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as erro:
        raise ValueError("A resposta da ANA não é um XML válido") from erro
    registros: list[dict[str, str]] = []
    for no in raiz.iter():
        if _nome_local(no.tag) != NO_REGISTRO_XML:
            continue
        registro = {_nome_local(filho.tag): (filho.text or "").strip() for filho in no}
        if registro.get("CodEstacao") != codigo_estacao:
            raise ValueError("Resposta da ANA traz outra estação")
        registros.append(registro)
    return registros


def datas_consulta(agora: datetime | None = None, dias: int = 1) -> dict[str, str]:
    """Janela de consulta (dd/mm/aaaa) de ``dias`` atrás até hoje."""
    agora = agora or datetime.now(timezone.utc)
    return {
        "data_inicio": (agora - timedelta(days=dias)).strftime("%d/%m/%Y"),
        "data_fim": agora.strftime("%d/%m/%Y"),
    }


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

    formato = configuracao.get("formato", "json")
    fuso_padrao = _fuso(configuracao.get("fuso_horario_fonte"))
    janela = datas_consulta(dias=int(configuracao.get("janela_dias", 1)))
    resultado: list[dict[str, Any]] = []
    falhas = 0
    for estacao in configuracao["estacoes"]:
        codigo = str(estacao["codigo_oficial"])
        substituicoes = {"codigo_oficial": codigo, **janela}
        parametros = {}
        for chave, valor in configuracao["parametros"].items():
            texto = str(valor)
            for nome, conteudo in substituicoes.items():
                texto = texto.replace("{" + nome + "}", conteudo)
            parametros[chave] = texto
        try:
            resposta_http = sessao.get(
                configuracao["endpoint"],
                params=parametros,
                headers=headers,
                timeout=30,
            )
            resposta_http.raise_for_status()
            if formato == "xml":
                registros = extrair_registros_xml(resposta_http.text, codigo)
            else:
                registros = _extrair_registros(
                    resposta_http.json(), configuracao["resposta"]["caminho_registros"]
                )
            leituras = normalizar_registros(
                registros,
                codigo_estacao=codigo,
                campos=configuracao["resposta"]["campos"],
                fuso_padrao=fuso_padrao,
                ignorar_sem_medida=formato == "xml",
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

    codigos = sorted({leitura["codigo_estacao"] for leitura in leituras})
    estacoes = (
        cliente.table("estacoes")
        .select("id,codigo_oficial")
        .in_("codigo_oficial", codigos)
        .execute()
        .data
        or []
    )
    ids_por_codigo = {str(e["codigo_oficial"]): e["id"] for e in estacoes}
    sem_cadastro = [codigo for codigo in codigos if codigo not in ids_por_codigo]
    if sem_cadastro:
        LOGGER.warning(
            "Estações sem cadastro em public.estacoes (aplique a migration): %s",
            ", ".join(sem_cadastro),
        )

    linhas = []
    for leitura in leituras:
        estacao_id = ids_por_codigo.get(leitura["codigo_estacao"])
        if estacao_id is None:
            continue
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
        valores.update(estacao_id=estacao_id, fonte_id=fonte_id)
        linhas.append(valores)
    if not linhas:
        raise RuntimeError("Nenhuma estação coletada está cadastrada em public.estacoes")

    # Upsert em lotes: uma requisição por lote em vez de uma por leitura.
    for inicio in range(0, len(linhas), TAMANHO_LOTE_UPSERT):
        cliente.table("leituras").upsert(
            linhas[inicio : inicio + TAMANHO_LOTE_UPSERT],
            on_conflict="estacao_id,data_hora_leitura",
        ).execute()
    return len(linhas)


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
