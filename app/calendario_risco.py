"""Calendário anual de risco (prevenção).

Pelos marcadores históricos da ANA (série oficial), mostra o mês típico da
cheia e da seca por estação e avisa "faltam X dias para o período crítico".
Não presume: só onde houver série oficial da ANA.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import streamlit as st

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}
MESES_CURTO = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
               7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}
FUSO_MANHAS = timezone(timedelta(hours=-4))


ICONES_SINAL = {"sem_dados": "⚪", "normal": "🟢", "atencao": "🟡", "alerta": "🟠", "alto": "🔴"}
LEITURA_ANTIGA_H = 12   # mesmo limite do robô (config/robo.yaml)


def status_atual(estacao: dict[str, Any], por_codigo: dict[str, dict[str, Any]],
                 ultima_leitura: dict[str, dict[str, Any]], agora: datetime | None = None) -> dict[str, Any]:
    """Nível medido mais recente e status da estação.

    Primeiro a análise do robô (sinal, posição entre seca e cheia recordes); sem ela, a última
    leitura da ANA, sem classificar (o app não inventa status que o robô não calculou).
    """
    from core.robo import ROTULOS_SINAL

    agora = agora or datetime.now(timezone.utc)
    analise = por_codigo.get(str(estacao.get("codigo_oficial") or ""))
    leitura = ultima_leitura.get(estacao["id"]) or {}
    nivel = (analise or {}).get("nivel_cm")
    quando = (analise or {}).get("data_hora_leitura")
    if nivel is None and leitura.get("nivel_cm") is not None:
        nivel, quando = leitura["nivel_cm"], leitura.get("data_hora_leitura")
    instante = None
    if quando:
        try:
            instante = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
            instante = instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)
        except ValueError:
            instante = None
    antiga = bool(instante and (agora - instante) > timedelta(hours=LEITURA_ANTIGA_H))
    if analise and analise.get("sinal"):
        sinal = analise["sinal"]
        status = f"{ICONES_SINAL.get(sinal, '⚪')} {ROTULOS_SINAL.get(sinal, sinal)}"
    elif nivel is not None:
        status = "⚪ Medido (sem análise do robô)"
    else:
        status = "⚪ Sem leitura"
    if antiga and nivel is not None:
        status += " · leitura antiga"
    return {
        # Números vazios ficam None (célula em branco), não "—": a tabela não mistura texto e número.
        "Nível atual (cm)": round(float(nivel)) if nivel is not None else None,
        "Status atual": status,
        "Posição seca→cheia (%)": (round(float(analise["posicao_pct"])) if analise and analise.get("posicao_pct")
                                   is not None else None),
        "Medido em": instante.astimezone(FUSO_MANHAS).strftime("%d/%m %H:%M") if instante else "—",
    }


def _data_br(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _mes_nome(mes: int) -> str:
    return MESES.get(mes, str(mes))


def _dias_para(proxima: date) -> int:
    return (proxima - date.today()).days


def _proxima_data(mes_alvo: int, ano: int | None = None) -> date:
    """Próxima ocorrência do mês alvo (a partir de hoje)."""
    hoje = date.today()
    ano = ano or hoje.year
    candidato = date(ano, mes_alvo, 1)
    if candidato < hoje:
        # Já passou neste ano: tenta no próximo ano
        try:
            candidato = date(ano + 1, mes_alvo, 1)
        except ValueError:
            candidato = date(ano + 1, 1, 1)
    return candidato


def renderizar_calendario_risco(cliente: Any, perfil: dict[str, Any]) -> None:
    from app.comum import carregar_municipios, mostrar_aviso
    from app.plano import _municipio_da_tela
    from app.relatorio_menu import painel_relatorio

    st.title("📅 Calendário anual de risco")
    st.caption("Pelos marcadores históricos oficiais da ANA (série HidroSerieHistorica, "
               "1990 em diante), mostra o mês típico da cheia e da seca por estação "
               "e avisa quantos dias faltam para o período crítico. "
               "Não presume: só onde houver série oficial.")
    mostrar_aviso()

    try:
        municipio_id = _municipio_da_tela(cliente, perfil, "calendario_risco")
        if not municipio_id:
            st.info("Associe um município ao seu perfil.")
            return
        municipios = carregar_municipios(cliente)
        nome_municipio = municipios.get(municipio_id, {}).get("nome", municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar os municípios: {erro}")
        return

    try:
        estacoes = (cliente.table("estacoes")
                    .select("id,codigo_oficial,nome,rio,municipio_id,latitude,longitude,"
                            "cheia_historica_cm,cheia_historica_data,"
                            "seca_historica_cm,seca_historica_data,historico_fonte")
                    .eq("municipio_id", municipio_id)
                    .order("nome")
                    .execute().data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar as estações (aplique a migration 202610140004): {erro}")
        return

    # Situação medida agora: análise mais recente do robô por estação e última leitura da ANA.
    from app.visual import carregar_analises

    por_codigo: dict[str, dict[str, Any]] = {}
    analise_municipio = carregar_analises(cliente).get(str(municipio_id).strip()) or {}
    for item in analise_municipio.get("estacoes_json") or []:
        por_codigo[str(item.get("codigo") or "")] = item
    ultima_leitura: dict[str, dict[str, Any]] = {}
    if estacoes:
        try:
            desde = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            for leitura in (cliente.table("leituras").select("estacao_id,nivel_cm,data_hora_leitura")
                            .in_("estacao_id", [e["id"] for e in estacoes]).gte("data_hora_leitura", desde)
                            .not_.is_("nivel_cm", "null").order("data_hora_leitura", desc=True)
                            .limit(2000).execute().data or []):
                ultima_leitura.setdefault(leitura["estacao_id"], leitura)
        except Exception:
            ultima_leitura = {}

    # Filtra só estações com marcador histórico
    com_historico = [e for e in estacoes
                     if e.get("cheia_historica_data") or e.get("seca_historica_data")]
    sem_historico = len(estacoes) - len(com_historico)

    # ---------- KPIs ----------
    c1, c2, c3 = st.columns(3)
    c1.metric("Estações com série histórica", len(com_historico))
    c2.metric("Estações sem série", sem_historico)
    proximo_critico = None
    for e in com_historico:
        for campo in ("cheia_historica_data", "seca_historica_data"):
            if e.get(campo):
                dados = datetime.fromisoformat(str(e[campo])).date()
                d = _dias_para(_proxima_dia_ou_mes(dados))
                if proximo_critico is None or d < proximo_critico:
                    proximo_critico = d
    c3.metric("Próximo período crítico", f"{proximo_critico} dias" if proximo_critico is not None else "—")

    if not com_historico:
        st.info("Nenhuma estação deste município tem marcadores históricos da ANA cadastrados. "
                "Execute o script de extremos históricos para preencher.")
        if estacoes:
            st.subheader("Situação medida agora")
            st.dataframe([{"Estação": f"{e['nome']} ({e.get('codigo_oficial')})", **status_atual(e, por_codigo, ultima_leitura)}
                          for e in estacoes], hide_index=True, width="stretch")
        return

    # ---------- Tabela por estação ----------
    st.subheader("Estações e períodos críticos")
    st.caption("**Status atual** = sinal da última análise do robô (a cada 3 h) para o nível medido: "
               "🟢 Normal · 🟡 Atenção · 🟠 Alerta · 🔴 Alto. **Posição** = onde o nível está entre a seca (0%) "
               "e a cheia (100%) recordes. \"Leitura antiga\" = mais de 12 h sem dado novo da ANA.")
    linhas_tabela = []
    for e in com_historico:
        cheia_data = e.get("cheia_historica_data")
        seca_data = e.get("seca_historica_data")
        cheia_mes = datetime.fromisoformat(str(cheia_data)).month if cheia_data else None
        seca_mes = datetime.fromisoformat(str(seca_data)).month if seca_data else None

        # Próxima data crítica (cheia ou seca, o que vier primeiro)
        datas_futuras = []
        if cheia_mes:
            datas_futuras.append(_proxima_data(cheia_mes))
        if seca_mes:
            datas_futuras.append(_proxima_data(seca_mes))
        proxima = min(datas_futuras) if datas_futuras else None
        dias_faltando = _dias_para(proxima) if proxima else None
        tipo_proximo = "cheia" if cheia_mes and proxima == _proxima_data(cheia_mes) else (
            "seca" if seca_mes and proxima == _proxima_data(seca_mes) else "—")

        linhas_tabela.append({
            "Estação": f"{e['nome']} ({e.get('codigo_oficial')})",
            "Rio": e.get("rio") or "—",
            **status_atual(e, por_codigo, ultima_leitura),
            "Mês típico cheia": _mes_nome(cheia_mes) if cheia_mes else "—",
            "Mês típico seca": _mes_nome(seca_mes) if seca_mes else "—",
            "Próximo crítico": tipo_proximo.title(),
            "Dias faltando": dias_faltando if dias_faltando is not None else "—",
            "Nível cheia recorde (cm)": e.get("cheia_historica_cm") or "—",
            "Nível seca recorde (cm)": e.get("seca_historica_cm") or "—",
        })
    st.dataframe(linhas_tabela, hide_index=True, width="stretch")

    # ---------- Calendário visual por mês ----------
    st.subheader("Calendário de risco por mês")
    meses_risco: dict[int, list[str]] = {}
    for linha in linhas_tabela:
        for campo, tipo in (("Mês típico cheia", "Cheia"), ("Mês típico seca", "Seca")):
            mes_nome = linha[campo]
            if mes_nome and mes_nome != "—":
                mes_num = next((m for m, n in MESES.items() if n == mes_nome), None)
                if mes_num:
                    meses_risco.setdefault(mes_num, []).append(tipo)

    colunas = st.columns(4)
    for posicao in range(1, 13):
        tipos = meses_risco.get(posicao, [])
        with colunas[(posicao - 1) % 4]:
            if tipos:
                st.markdown(f"**{MESES_CURTO[posicao]}** · {', '.join(tipos)}")
            else:
                st.markdown(f"*{MESES_CURTO[posicao]}* · sem histórico")

    # ---------- Relatório ----------
    linhas_relatorio = []
    for e in com_historico:
        cheia_data = e.get("cheia_historica_data")
        seca_data = e.get("seca_historica_data")
        cheia_mes = datetime.fromisoformat(str(cheia_data)).month if cheia_data else None
        seca_mes = datetime.fromisoformat(str(seca_data)).month if seca_data else None
        atual = status_atual(e, por_codigo, ultima_leitura)
        linhas_relatorio.append({
            "Estação": e["nome"],
            "Código": e.get("codigo_oficial"),
            "Rio": e.get("rio") or "",
            "Nível atual (cm)": atual["Nível atual (cm)"],
            # PDF usa fonte Latin-1: o status vai sem o ícone colorido.
            "Status atual": atual["Status atual"].split(" ", 1)[-1],
            "Posição seca-cheia (%)": atual["Posição seca→cheia (%)"],
            "Medido em": atual["Medido em"],
            "Mês típico cheia": _mes_nome(cheia_mes) if cheia_mes else "",
            "Mês típico seca": _mes_nome(seca_mes) if seca_mes else "",
            "Cheia recorde (cm)": e.get("cheia_historica_cm") or "",
            "Data cheia recorde": _data_br(cheia_data) if cheia_data else "",
            "Seca recorde (cm)": e.get("seca_historica_cm") or "",
            "Data seca recorde": _data_br(seca_data) if seca_data else "",
            "Fonte": e.get("historico_fonte") or "",
        })
    painel_relatorio(
        "Calendário anual de risco",
        [("Estações e períodos críticos", linhas_relatorio)],
        subtitulo=nome_municipio,
        resumo={"Estações com histórico": len(com_historico),
                "Estações sem histórico": sem_historico,
                "Próximo período crítico": f"{proximo_critico} dias" if proximo_critico is not None else "—"},
    )


def _proxima_dia_ou_mes(dados: date) -> date:
    """Próxima data com o mesmo mês e dia a partir de hoje."""
    hoje = date.today()
    ano = hoje.year
    while True:
        try:
            candidato = date(ano, dados.month, dados.day)
        except ValueError:
            # Dia não existe neste mês (ex: 31 de fevereiro): usa último dia do mês
            if dados.month == 12:
                candidato = date(ano, 12, 31)
                ano += 1
            else:
                candidato = date(ano, dados.month + 1, 1) - timedelta(days=1)
        if candidato >= hoje:
            return candidato
        ano += 1
