"""Renderização das páginas operacionais e públicas do Streamlit."""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from app.comum import (
    AVISO_PROTOTIPO,
    carregar_municipios,
    carregar_pesos,
    cliente_supabase,
    exigir_perfil,
    mostrar_aviso,
)
from app.cadastros import (
    bloco_abrigos,
    bloco_comunidades,
    bloco_infraestrutura,
    bloco_plano,
    bloco_recursos,
    bloco_situacao,
)
from app.visual import (
    AVISO_ROBO,
    aplicar_estilo,
    carregar_analises,
    carregar_municipios_mapa,
    carregar_series,
    cartao_analise,
    grafico_barras,
    grafico_estacao_marcadores,
    grafico_faixa_historica,
    grafico_series,
    grafico_sinais,
    grafico_variacao,
    kpis_robo,
    mapa_risco,
)
from core.relatorio_robo import gerar_relatorio_robo
from core.robo import ROTULOS_SINAL
from core.alertas import (
    atualizar_alerta,
    formatar_fontes,
    listar_alertas,
    marcar_enviado,
)
from core.indicador import calcular_indicador, ler_alertas_emitidos
from core.indice import COMPONENTES, ler_indices, validar_pesos
from core.relatorios import (
    COLUNAS_DETALHADAS,
    COLUNAS_PDF_DETALHADO,
    SEM_INDICE,
    carregar_dados_relatorio,
    detalhar_situacao,
    gerar_csv,
    gerar_pdf,
    montar_situacao_municipal,
    resumo_por_classe,
    totais_detalhados,
)

EIXOS = {
    "prevencao": "Prevenção",
    "mitigacao": "Mitigação",
    "preparacao": "Preparação",
    "resposta": "Resposta",
    "recuperacao": "Recuperação",
}
STATUS_ACAO = ["pendente", "em_andamento", "concluida"]

PERFIS_GESTAO = {
    "gestor_nacional",
    "gestor_estadual",
    "administrador",
}
PERFIS_REVISAO = PERFIS_GESTAO | {
    "operador_monitoramento",
    "coordenador_municipal",
}
PERFIS_TODOS = {
    "gestor_nacional",
    "gestor_estadual",
    "coordenador_municipal",
    "operador_monitoramento",
    "agente_campo",
    "saude_assistencia",
    "logistica_abastecimento",
    "pesquisador",
    "administrador",
}


def _nome_municipio(municipios: dict[str, dict[str, str]], codigo: str) -> str:
    municipio = municipios.get(codigo.strip(), {})
    if not municipio:
        return codigo
    return f"{municipio.get('nome', codigo)}/{municipio.get('uf', '')}"


def _buscar_municipio(cliente: Any, municipio_id: str | None) -> dict[str, Any]:
    if not municipio_id:
        return {}
    resultado = (
        cliente.table("municipios")
        .select("id_ibge,nome,uf,populacao")
        .eq("id_ibge", municipio_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else {}


def _classes_indice(indices: list[dict[str, Any]]) -> dict[str, str]:
    """Classe do índice mais recente por município (ler_indices já vem ordenado)."""
    classes: dict[str, str] = {}
    for indice in indices:
        classes.setdefault(indice["municipio_id"].strip(), indice["classe"])
    return classes


def _secao_situacao_visual(
    cliente: Any,
    municipios: dict[str, dict[str, str]],
    indices: list[dict[str, Any]],
    *,
    limite_cartoes: int = 12,
) -> dict[str, dict[str, Any]]:
    """KPIs, mapa de risco por cidade, gráficos e análises do robô."""
    aplicar_estilo()
    analises = carregar_analises(cliente)
    municipios_mapa = carregar_municipios_mapa(cliente)
    if not analises:
        st.info(
            "O robô ainda não gerou análises (roda a cada 3 horas pelo GitHub Actions). "
            "Sem análise não há sinal: isso não significa risco zero."
        )
    kpis_robo(analises, municipios_mapa)
    aba_mapa, aba_graficos, aba_analises = st.tabs(
        ["🗺️ Mapa de risco", "📈 Gráficos", "🤖 Análises do robô"]
    )
    with aba_mapa:
        mapa_risco(municipios_mapa, analises, classes_indice=_classes_indice(indices))
    with aba_graficos:
        nomes = {codigo: m.get("nome", codigo) for codigo, m in municipios.items()}
        coluna_a, coluna_b = st.columns(2)
        with coluna_a:
            grafico_sinais(analises)
        with coluna_b:
            if indices:
                contagem: dict[str, int] = {}
                for classe in _classes_indice(indices).values():
                    contagem[classe] = contagem.get(classe, 0) + 1
                grafico_barras(contagem, "Municípios por classe do índice")
            else:
                st.info("Índice indisponível: faltam cotas oficiais de alerta nas estações.")
        grafico_faixa_historica(analises, nomes)
        grafico_variacao(analises, nomes)
        try:
            series = carregar_series(cliente)
            grafico_estacao_marcadores(series, analises, nomes)
            grafico_series(series)
        except Exception as erro:
            st.warning(f"Série de níveis indisponível: {erro}")
    with aba_analises:
        st.caption(AVISO_ROBO)
        if analises:
            try:
                st.download_button(
                    "📄 Baixar relatório do robô (PDF)",
                    gerar_relatorio_robo(
                        analises, {c: _nome_municipio(municipios, c) for c in analises}
                    ),
                    file_name="relatorio_risco_robo.pdf",
                    mime="application/pdf",
                )
            except Exception as erro:
                st.warning(f"Relatório do robô indisponível: {erro}")
        ordem = {"alto": 0, "alerta": 1, "atencao": 2, "normal": 3, "sem_dados": 4}
        for codigo, analise in sorted(
            analises.items(), key=lambda item: ordem.get(item[1].get("sinal"), 9)
        )[:limite_cartoes]:
            cartao_analise(_nome_municipio(municipios, codigo), analise)
    return analises


def _graficos_pdf(
    resumo: dict[str, int], linhas: list[dict[str, Any]]
) -> list[tuple[str, dict[str, float]]]:
    """Gráficos do relatório: classes do índice e sinais do robô."""
    classes = {
        rotulo.replace("Municípios — ", ""): valor
        for rotulo, valor in resumo.items()
        if rotulo.startswith("Municípios — ")
    }
    sinais: dict[str, float] = {}
    for linha in linhas:
        sinal = linha.get("Sinal do robô") or "Sem estação"
        sinais[sinal] = sinais.get(sinal, 0) + 1
    return [("Municípios por classe do índice", classes), ("Municípios por sinal do robô", sinais)]


def renderizar_painel_principal() -> None:
    st.title("Centro de Inteligência da Defesa Civil")
    st.caption("Painel principal — situação e tendência municipal")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(PERFIS_TODOS)
        pesos, validacao_oficial = carregar_pesos(cliente)
        municipios = carregar_municipios(cliente)
        indices = ler_indices(cliente)
    except Exception as erro:
        st.error(f"Não foi possível carregar o painel: {erro}")
        return

    _secao_situacao_visual(cliente, municipios, indices)

    st.subheader("Pesos do Índice de Impacto Humanitário")
    st.caption(
        "Hipótese configurável, nunca fixa no código. "
        + ("Validação oficial registrada." if validacao_oficial else "Ainda sem validação oficial.")
    )
    grafico_barras(
        {nome.replace("_", " ").title(): peso for nome, peso in pesos.items()},
        "Peso de cada componente (%)",
    )
    if perfil["perfil"] not in PERFIS_GESTAO and perfil.get("municipio_id"):
        indices = [
            indice
            for indice in indices
            if indice["municipio_id"].strip() == perfil["municipio_id"]
        ]
    if not indices:
        st.info(
            "Ainda não há índices calculados com evidências disponíveis para seu "
            "escopo. A ausência de leituras não é tratada como risco zero."
        )
        return

    linhas = []
    for indice in indices:
        linhas.append(
            {
                "Município": _nome_municipio(municipios, indice["municipio_id"]),
                "Classe": indice["classe"],
                "Índice": indice["score_total"],
                "Data/hora do índice (UTC)": indice["data_hora"],
                "Data/hora da leitura de referência (UTC)": indice.get(
                    "data_hora_leitura_referencia"
                ),
                "Fontes e leituras": formatar_fontes(indice.get("fontes_json")),
            }
        )
    st.dataframe(linhas, hide_index=True, width="stretch")
    posicao = st.selectbox(
        "Explicação do índice",
        range(len(indices)),
        format_func=lambda indice_pos: (
            f"{_nome_municipio(municipios, indices[indice_pos]['municipio_id'])} — "
            f"{indices[indice_pos]['classe']} ({indices[indice_pos]['score_total']})"
        ),
    )
    indice = indices[posicao]
    st.caption(
        f"Fontes e leituras: {formatar_fontes(indice.get('fontes_json'))} · "
        f"Índice calculado em {indice['data_hora']}"
    )
    st.dataframe(indice.get("explicacao_json", []), hide_index=True)


def renderizar_gestor() -> None:
    st.title("Visão nacional/estadual")
    st.caption("Situação de todos os municípios, resumo por classe e relatórios")
    mostrar_aviso()
    try:
        cliente, _ = exigir_perfil(PERFIS_GESTAO)
        municipios = carregar_municipios(cliente)
        indices = ler_indices(cliente, limite=5000)
        alertas = (
            cliente.table("alertas")
            .select("id,municipio_id,classe,status,criado_em")
            .order("criado_em", desc=True)
            .limit(2000)
            .execute()
            .data
            or []
        )
    except Exception as erro:
        st.error(f"Não foi possível carregar a visão de gestão: {erro}")
        return

    ufs = sorted({m.get("uf", "") for m in municipios.values() if m.get("uf")})
    uf = st.selectbox("UF", ["Todas", *ufs])
    if uf != "Todas":
        municipios = {c: m for c, m in municipios.items() if m.get("uf") == uf}
    dados, avisos_dados = carregar_dados_relatorio(cliente)
    for aviso in avisos_dados:
        st.warning(f"Fonte de dados indisponível no relatório — {aviso}")
    linhas = detalhar_situacao(
        montar_situacao_municipal(municipios, indices, alertas),
        indices,
        alertas,
        dados,
    )
    resumo = resumo_por_classe(linhas)
    totais = totais_detalhados(linhas)

    st.subheader("Resumo por classe")
    colunas_resumo = st.columns(min(len(resumo), 4))
    for posicao, (rotulo, valor) in enumerate(resumo.items()):
        colunas_resumo[posicao % len(colunas_resumo)].metric(
            rotulo.replace("Municípios — ", ""), valor
        )
    if not indices:
        st.info(
            "Nenhum índice calculado ainda: municípios aparecem como "
            f'"{SEM_INDICE}" até o motor gerar índices verificáveis.'
        )

    analises = _secao_situacao_visual(cliente, municipios, indices, limite_cartoes=30)
    for linha in linhas:
        analise = analises.get(str(linha.get("Código IBGE", "")).strip())
        linha["Sinal do robô"] = ROTULOS_SINAL.get(analise["sinal"]) if analise else "Sem estação"
        linha["Análise do robô"] = analise["texto"] if analise else ""

    st.subheader("Totais do recorte")
    colunas_totais = st.columns(4)
    for posicao, (rotulo, valor) in enumerate(totais.items()):
        colunas_totais[posicao % 4].metric(rotulo, "n/d" if valor is None else valor)
    st.caption(
        "Totais somam apenas o que está cadastrado na plataforma; zero pode "
        "significar ausência de cadastro, não ausência de risco."
    )

    st.subheader("Situação por município")
    visao = st.radio("Visão", ["Resumida", "Completa"], horizontal=True)
    colunas_tabela = COLUNAS_PDF_DETALHADO if visao == "Resumida" else COLUNAS_DETALHADAS
    st.dataframe(
        [{c: linha.get(c) for c in colunas_tabela} for linha in linhas],
        hide_index=True,
        width="stretch",
    )

    st.subheader("Detalhe de um município")
    escolhido = st.selectbox(
        "Município", [linha["Município"] for linha in linhas], key="detalhe_municipio"
    )
    linha_escolhida = next(l for l in linhas if l["Município"] == escolhido)
    st.table(
        [
            {"Campo": c, "Valor": "" if linha_escolhida.get(c) is None else str(linha_escolhida[c])}
            for c in COLUNAS_DETALHADAS
        ]
    )
    st.caption("Calhas não comparáveis sem geometria e vínculo hidrológico confirmados.")

    resumo_indicador: dict[str, Any] = {}
    try:
        resumo_indicador = calcular_indicador(ler_alertas_emitidos(cliente))
        st.subheader("Indicador: tempo leitura → emissão do alerta")
        media = resumo_indicador["media_minutos"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Média (min)", "sem dados" if media is None else f"{media:.1f}")
        c2.metric("Meta (min)", f"{resumo_indicador['meta_minutos']:.0f}")
        c3.metric("Alertas medidos", resumo_indicador["alertas_medidos"])
        st.caption(
            "Linha de base do projeto: 30 min; meta: 10 min. Só entram alertas emitidos "
            "com horário de leitura verificável; a meta é hipótese sem validação oficial."
        )
    except Exception as erro:
        st.warning(f"Indicador indisponível: {erro}")

    st.subheader("Exportar relatório")
    sufixo = "" if uf == "Todas" else f"_{uf}"
    colunas_csv = [*COLUNAS_DETALHADAS, "Sinal do robô", "Análise do robô"]
    st.download_button(
        "Baixar CSV",
        gerar_csv(linhas, colunas_csv),
        file_name=f"situacao_municipios{sufixo}.csv",
        mime="text/csv",
    )
    try:
        resumo_pdf = {**resumo, **totais}
        if resumo_indicador:
            media = resumo_indicador["media_minutos"]
            resumo_pdf["Indicador leitura-emissao (min, média)"] = media
            resumo_pdf["Meta (min)"] = resumo_indicador["meta_minutos"]
        st.download_button(
            "Baixar PDF",
            gerar_pdf(
                "Situação dos municípios — Centro de Inteligência da Defesa Civil",
                linhas,
                COLUNAS_PDF_DETALHADO,
                resumo=resumo_pdf,
                colunas_detalhe=COLUNAS_DETALHADAS,
                graficos=_graficos_pdf(resumo, linhas),
                analises=[
                    {
                        "Município": _nome_municipio(municipios, codigo),
                        "sinal": ROTULOS_SINAL.get(analise["sinal"], analise["sinal"]),
                        "texto": analise["texto"],
                        "gerado_em": analise["gerado_em"],
                    }
                    for codigo, analise in analises.items()
                    if codigo in municipios
                ],
            ),
            file_name=f"situacao_municipios{sufixo}.pdf",
            mime="application/pdf",
        )
    except Exception as erro:
        st.warning(f"PDF indisponível: {erro}")

def renderizar_alertas() -> None:
    st.title("Painel secundário de alertas")
    st.caption("Sugestões do motor — revisão humana necessária antes de enviar")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(PERFIS_REVISAO)
        alertas = listar_alertas(cliente, limite=300)
    except Exception as erro:
        st.error(f"Não foi possível carregar os alertas: {erro}")
        return
    if perfil["perfil"] in {"coordenador_municipal", "administrador"}:
        _renderizar_assinaturas(cliente, perfil)
    pendentes = [alerta for alerta in alertas if alerta["status"] == "rascunho"]
    st.metric("Rascunhos aguardando revisão", len(pendentes))
    if not alertas:
        st.info("Não há alertas registrados.")
        return

    for alerta in alertas:
        municipio = alerta.get("municipio") or {}
        titulo = (
            f"{alerta['classe']} — {municipio.get('nome', alerta['municipio_id'])}/"
            f"{municipio.get('uf', '')} — {alerta['status']}"
        )
        with st.expander(titulo):
            indice = alerta.get("indice") or {}
            st.caption(
                f"Fontes/leituras: {formatar_fontes(indice.get('fontes_json'))} · "
                f"Leitura de referência: "
                f"{indice.get('data_hora_leitura_referencia') or 'não informada'} · "
                f"Alerta emitido: {alerta.get('emitido_em') or 'ainda não emitido'}"
            )
            if alerta["status"] == "rascunho":
                with st.form(f"revisao-{alerta['id']}"):
                    texto = st.text_area(
                        "Texto sugerido (edite antes de aprovar)", alerta["texto"]
                    )
                    col_aprovar, col_rejeitar = st.columns(2)
                    aprovar = col_aprovar.form_submit_button("Aprovar versão revisada")
                    rejeitar = col_rejeitar.form_submit_button("Rejeitar")
                    if aprovar:
                        try:
                            atualizar_alerta(
                                cliente,
                                alerta["id"],
                                acao="aprovar",
                                texto=texto,
                                aprovado_por=perfil["id"],
                            )
                            st.success("Alerta aprovado. O envio ainda exige ação explícita.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível aprovar: {erro}")
                    if rejeitar:
                        try:
                            atualizar_alerta(cliente, alerta["id"], acao="rejeitar")
                            st.success("Rascunho rejeitado.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível rejeitar: {erro}")
            else:
                st.text(alerta["texto"])
                if perfil["perfil"] in {
                    "coordenador_municipal",
                    "administrador",
                }:
                    entregas = (
                        cliente.table("entregas_alerta")
                        .select(
                            "canal,destino_mascarado,status,erro,tentado_em"
                        )
                        .eq("alerta_id", alerta["id"])
                        .order("tentado_em", desc=True)
                        .limit(100)
                        .execute()
                        .data
                        or []
                    )
                    if entregas:
                        st.caption("Histórico de tentativas (destinos mascarados)")
                        st.dataframe(
                            entregas,
                            hide_index=True,
                            width="stretch",
                        )
                if alerta["status"] == "aprovado" and st.button(
                    "Enviar alerta aprovado",
                    key=f"enviar-{alerta['id']}",
                    disabled=perfil["perfil"]
                    not in {"coordenador_municipal", "administrador"},
                ):
                    try:
                        from core.notificacoes import enviar_alerta_aprovado

                        resultado = enviar_alerta_aprovado(cliente, alerta["id"])
                        marcar_enviado(cliente, alerta["id"])
                        st.success(
                            f"Alerta enviado a {resultado['enviados']} destino(s)."
                        )
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Envio incompleto ou não realizado: {erro}")


def renderizar_coordenador() -> None:
    st.title("Gestão municipal da Defesa Civil")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil({"coordenador_municipal", "administrador"})
        municipio_id = perfil.get("municipio_id")
        if perfil["perfil"] == "administrador" and not municipio_id:
            municipios = carregar_municipios(cliente)
            municipio_id = st.selectbox(
                "Município", list(municipios), format_func=lambda codigo: _nome_municipio(municipios, codigo)
            )
        municipio = _buscar_municipio(cliente, municipio_id)
        if not municipio_id or not municipio:
            st.info("Associe um município ao perfil para abrir este painel.")
            return
        st.subheader(f"{municipio['nome']}/{municipio['uf']}")
        aplicar_estilo()
        analise = carregar_analises(cliente).get(str(municipio_id).strip())
        if analise:
            cartao_analise(f"{municipio['nome']}/{municipio['uf']}", analise)
        else:
            st.info("Sem análise do robô para este município (sem estação monitorada ou ainda não gerada).")
        abas = st.tabs(
            ["🏘️ Comunidades", "📦 Recursos", "🏠 Abrigos", "📋 Plano", "🏥 Infraestrutura",
             "📢 Situação oficial", "✅ Tarefas por eixo"]
        )
        with abas[0]:
            bloco_comunidades(cliente, municipio_id)
        with abas[1]:
            bloco_recursos(cliente, municipio_id)
        with abas[2]:
            bloco_abrigos(cliente, municipio_id)
        with abas[3]:
            bloco_plano(cliente, municipio_id)
        with abas[4]:
            bloco_infraestrutura(cliente, municipio_id)
        with abas[5]:
            bloco_situacao(cliente, municipio_id)
        with abas[6]:
            _renderizar_acoes(cliente, municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar a gestão municipal: {erro}")


def _renderizar_acoes(cliente: Any, municipio_id: str) -> None:
    """Tarefas por eixo do PN-PDC, vinculadas a alertas do município."""
    st.subheader("Tarefas por eixo")
    alertas = (
        cliente.table("alertas")
        .select("id,classe,criado_em,status")
        .eq("municipio_id", municipio_id)
        .order("criado_em", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    if not alertas:
        st.info("Sem alertas neste município; as tarefas são vinculadas a um alerta.")
        return
    ids = [alerta["id"] for alerta in alertas]
    acoes = (
        cliente.table("acoes")
        .select("id,alerta_id,eixo,descricao,prazo,status")
        .in_("alerta_id", ids)
        .order("prazo")
        .limit(500)
        .execute()
        .data
        or []
    )
    for codigo, rotulo in EIXOS.items():
        do_eixo = [acao for acao in acoes if acao["eixo"] == codigo]
        with st.expander(f"{rotulo} ({len(do_eixo)})"):
            if do_eixo:
                st.dataframe(
                    [
                        {
                            "Descrição": a["descricao"],
                            "Prazo": a["prazo"],
                            "Status": a["status"],
                        }
                        for a in do_eixo
                    ],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.caption("Nenhuma tarefa neste eixo.")
    por_id = {alerta["id"]: alerta for alerta in alertas}
    with st.form("nova-acao"):
        alerta_id = st.selectbox(
            "Alerta de origem",
            ids,
            format_func=lambda i: f"{por_id[i]['classe']} · {str(por_id[i]['criado_em'])[:16]} · {por_id[i]['status']}",
        )
        eixo = st.selectbox("Eixo", list(EIXOS), format_func=lambda c: EIXOS[c])
        descricao = st.text_input("Descrição da tarefa", max_chars=300).strip()
        criar = st.form_submit_button("Criar tarefa")
    if criar:
        if not descricao:
            st.error("Informe a descrição da tarefa.")
        else:
            inserida = (
                cliente.table("acoes")
                .insert({"alerta_id": alerta_id, "eixo": eixo, "descricao": descricao})
                .execute()
            )
            if not inserida.data:
                raise RuntimeError("Tarefa não criada; verifique as permissões.")
            st.success("Tarefa criada.")
            st.rerun()
    if acoes:
        por_acao = {a["id"]: a for a in acoes}
        with st.form("atualizar-acao"):
            acao_id = st.selectbox(
                "Atualizar tarefa",
                list(por_acao),
                format_func=lambda i: f"{EIXOS[por_acao[i]['eixo']]} · {por_acao[i]['descricao'][:50]}",
            )
            novo = st.selectbox("Novo status", STATUS_ACAO)
            salvar = st.form_submit_button("Salvar status")
        if salvar:
            alterada = (
                cliente.table("acoes").update({"status": novo}).eq("id", acao_id).execute()
            )
            if not alterada.data:
                raise RuntimeError("Tarefa não alterada; verifique as permissões.")
            st.success("Status atualizado.")
            st.rerun()


def renderizar_monitoramento() -> None:
    st.title("Sala de monitoramento")
    mostrar_aviso()
    try:
        cliente, _ = exigir_perfil({"operador_monitoramento", "administrador"})
        fontes = (
            cliente.table("fontes")
            .select("nome,tipo,status,ultima_coleta,ultima_verificacao,ultimo_erro")
            .order("nome")
            .execute()
        )
        estacoes = (
            cliente.table("estacoes")
            .select("codigo_oficial,nome,rio,municipio_id")
            .limit(1000)
            .execute()
        )
        leituras = (
            cliente.table("leituras")
            .select("estacao_id,data_hora_leitura,nivel_cm,vazao,chuva_mm,coletado_em,fonte_id")
            .order("data_hora_leitura", desc=True)
            .limit(200)
            .execute()
        )
        st.subheader("Saúde das fontes")
        st.dataframe(fontes.data or [], hide_index=True, width="stretch")
        aplicar_estilo()
        grafico_series(carregar_series(cliente))
        analises = carregar_analises(cliente)
        nomes_municipios = {c: m["nome"] for c, m in carregar_municipios(cliente).items()}
        grafico_variacao(analises, nomes_municipios)
        st.subheader("Estações")
        st.dataframe(estacoes.data or [], hide_index=True, width="stretch")
        st.subheader("Leituras recentes")
        st.dataframe(leituras.data or [], hide_index=True, width="stretch")
        _renderizar_comparacao_historica(cliente, leituras.data or [])
    except Exception as erro:
        st.error(f"Não foi possível carregar o monitoramento: {erro}")


def _renderizar_comparacao_historica(cliente: Any, leituras: list[dict[str, Any]]) -> None:
    from core.historico import comparar_com_historico, extremos_observados

    st.subheader("Nível atual x cheia e seca históricas")
    st.caption(
        "Marcadores históricos só aparecem quando preenchidos a partir de série oficial "
        "(ANA/Hidroweb, SGB); nada é presumido."
    )
    try:
        estacoes = (
            cliente.table("estacoes")
            .select(
                "id,nome,rio,cheia_historica_cm,cheia_historica_data,"
                "seca_historica_cm,seca_historica_data,historico_fonte"
            )
            .limit(1000)
            .execute()
            .data
            or []
        )
    except Exception as erro:
        st.warning(f"Marcadores históricos indisponíveis (aplique a migration 202610060003): {erro}")
        return
    linhas = []
    for estacao in estacoes:
        serie = [x for x in leituras if x.get("estacao_id") == estacao["id"]]
        if not serie:
            continue
        atual = serie[0]
        comparacao = comparar_com_historico(
            atual.get("nivel_cm"),
            estacao.get("cheia_historica_cm"),
            estacao.get("seca_historica_cm"),
        )
        maior, menor = extremos_observados([x.get("nivel_cm") for x in serie])
        linhas.append(
            {
                "Estação": estacao.get("nome"),
                "Nível atual (cm)": atual.get("nivel_cm"),
                "Cheia histórica (cm)": estacao.get("cheia_historica_cm"),
                "Seca histórica (cm)": estacao.get("seca_historica_cm"),
                "Dif. p/ cheia (cm)": comparacao["dif_cheia_cm"],
                "Dif. p/ seca (cm)": comparacao["dif_seca_cm"],
                "Posição seca→cheia (%)": comparacao["posicao_pct"],
                "Situação": comparacao["situacao"],
                "Máx. na série carregada": maior,
                "Mín. na série carregada": menor,
                "Fonte do histórico": estacao.get("historico_fonte"),
            }
        )
    if not linhas:
        st.info("Sem leituras de estações para comparar ainda.")
        return
    st.dataframe(linhas, hide_index=True, width="stretch")


def renderizar_agente_campo() -> None:
    st.title("Registro de campo")
    st.caption("Formulário simples; conexão e dispositivo são responsabilidade do usuário.")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(
            {"agente_campo", "coordenador_municipal", "administrador"}
        )
        municipio_id = perfil.get("municipio_id")
        if perfil["perfil"] == "administrador" and not municipio_id:
            municipios = carregar_municipios(cliente)
            municipio_id = st.selectbox(
                "Município", list(municipios), format_func=lambda codigo: _nome_municipio(municipios, codigo)
            )
        if not municipio_id:
            st.info("Associe um município ao perfil antes de registrar atendimentos.")
            return
        comunidades = (
            cliente.table("comunidades")
            .select("id,nome")
            .eq("municipio_id", municipio_id)
            .order("nome")
            .execute()
            .data
            or []
        )
        if not comunidades:
            st.info(
                "Nenhuma comunidade cadastrada para este município. Cadastre a primeira abaixo "
                "(coordenação municipal ou administração)."
            )
            bloco_comunidades(cliente, municipio_id)
            return
        with st.form("registro-familias", clear_on_submit=True):
            comunidade_id = st.selectbox(
                "Comunidade",
                [item["id"] for item in comunidades],
                format_func=lambda codigo: next(
                    item["nome"] for item in comunidades if item["id"] == codigo
                ),
            )
            familias = st.number_input("Famílias afetadas", min_value=0, step=1)
            pessoas = st.number_input("Pessoas afetadas", min_value=0, step=1)
            necessidades = st.multiselect(
                "Necessidades informadas",
                ["água", "alimento", "medicamento", "abrigo", "transporte", "outra"],
            )
            salvar = st.form_submit_button("Registrar")
        if salvar:
            resultado = (
                cliente.table("pessoas_afetadas")
                .insert(
                    {
                        "comunidade_id": comunidade_id,
                        "familias": int(familias),
                        "pessoas": int(pessoas),
                        "necessidades": necessidades,
                        "data": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )
            if not resultado.data:
                raise RuntimeError("O Supabase não confirmou o registro")
            st.success("Registro salvo com auditoria.")
        _resumo_afetados(cliente, municipio_id)
        with st.expander("Cadastrar nova comunidade"):
            bloco_comunidades(cliente, municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível registrar o atendimento: {erro}")


def _resumo_afetados(cliente: Any, municipio_id: str) -> None:
    """Totais e últimos registros de famílias afetadas nas comunidades do município."""
    comunidades = {
        c["id"]: c["nome"]
        for c in (
            cliente.table("comunidades").select("id,nome").eq("municipio_id", municipio_id)
            .execute().data or []
        )
    }
    if not comunidades:
        st.info("Sem comunidades cadastradas neste município.")
        return
    registros = (
        cliente.table("pessoas_afetadas")
        .select("comunidade_id,familias,pessoas,necessidades,data")
        .in_("comunidade_id", list(comunidades))
        .order("data", desc=True)
        .limit(200)
        .execute()
        .data
        or []
    )
    st.subheader("Famílias e pessoas afetadas")
    if not registros:
        st.info("Nenhum registro de campo ainda.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(registros))
    c2.metric("Famílias", sum(r["familias"] for r in registros))
    c3.metric("Pessoas", sum(r["pessoas"] for r in registros))
    necessidades: dict[str, int] = {}
    for registro in registros:
        for item in registro.get("necessidades") or []:
            necessidades[item] = necessidades.get(item, 0) + 1
    if necessidades:
        grafico_barras(dict(sorted(necessidades.items(), key=lambda i: -i[1])), "Necessidades mais citadas")
    st.dataframe(
        [
            {
                "Data (UTC)": str(r["data"])[:16].replace("T", " "),
                "Comunidade": comunidades.get(r["comunidade_id"], r["comunidade_id"]),
                "Famílias": r["familias"],
                "Pessoas": r["pessoas"],
                "Necessidades": ", ".join(r.get("necessidades") or []),
            }
            for r in registros[:50]
        ],
        hide_index=True,
        width="stretch",
    )


def renderizar_saude() -> None:
    st.title("Saúde e assistência social")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(
            {"saude_assistencia", "coordenador_municipal", "administrador"}
        )
        municipio_id = perfil.get("municipio_id")
        if perfil["perfil"] == "administrador" and not municipio_id:
            municipios = carregar_municipios(cliente)
            municipio_id = st.selectbox(
                "Município", list(municipios), format_func=lambda codigo: _nome_municipio(municipios, codigo)
            )
        if not municipio_id:
            st.info("Associe um município ao perfil.")
            return
        aba_unidades, aba_estoque, aba_afetados = st.tabs(
            ["🏥 Unidades de saúde", "💊 Medicamentos e oxigênio", "👪 Famílias afetadas"]
        )
        with aba_unidades:
            bloco_infraestrutura(cliente, municipio_id, ["ubs"])
        with aba_estoque:
            bloco_recursos(cliente, municipio_id, ["medicamento", "oxigenio"])
        with aba_afetados:
            _resumo_afetados(cliente, municipio_id)
        st.caption("Rotas de evacuação médica: registre-as no plano de contingência (Gestão municipal).")
    except Exception as erro:
        st.error(f"Não foi possível carregar o painel de saúde: {erro}")


def renderizar_logistica() -> None:
    st.title("Logística e abastecimento")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(
            {"logistica_abastecimento", "coordenador_municipal", "administrador"}
        )
        municipio_id = perfil.get("municipio_id")
        if perfil["perfil"] == "administrador" and not municipio_id:
            municipios = carregar_municipios(cliente)
            municipio_id = st.selectbox(
                "Município", list(municipios), format_func=lambda codigo: _nome_municipio(municipios, codigo)
            )
        if not municipio_id:
            st.info("Associe um município ao perfil.")
            return
        aba_estoque, aba_abrigos, aba_infra, aba_rotas, aba_assinaturas = st.tabs(
            ["📦 Pré-posicionamento", "🏠 Abrigos", "⚓ Portos, captação e energia",
             "🛶 Rotas alternativas", "🔔 Assinaturas de alertas"]
        )
        with aba_estoque:
            bloco_recursos(cliente, municipio_id, ["agua", "alimento", "combustivel", "purificador"])
        with aba_abrigos:
            bloco_abrigos(cliente, municipio_id)
        with aba_infra:
            bloco_infraestrutura(cliente, municipio_id, ["porto", "captacao", "energia"])
        with aba_rotas:
            bloco_plano(cliente, municipio_id)
        with aba_assinaturas:
            _renderizar_assinaturas(cliente, perfil)
    except Exception as erro:
        st.error(f"Não foi possível carregar logística: {erro}")


def _renderizar_assinaturas(cliente: Any, perfil: dict[str, Any]) -> None:
    municipio_id = perfil.get("municipio_id")
    if perfil["perfil"] == "administrador" and not municipio_id:
        municipios = carregar_municipios(cliente)
        municipio_id = st.selectbox(
            "Município das assinaturas",
            list(municipios),
            format_func=lambda codigo: _nome_municipio(municipios, codigo),
            key="municipio-assinaturas",
        )
    if not municipio_id:
        st.info("Associe um município ao perfil para gerenciar assinaturas.")
        return
    st.subheader("Assinaturas de alertas")
    st.caption(
        "Cadastre contatos somente com consentimento. Uma pessoa responsável deve "
        "verificar o controle do endereço/conta antes de ativar a assinatura."
    )
    try:
        assinaturas = (
            cliente.table("assinaturas_alerta")
            .select("id,canal,destino,ativo,confirmado_em")
            .eq("municipio_id", municipio_id)
            .order("criado_em", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
        if assinaturas:
            from core.notificacoes import mascara_destino

            st.dataframe(
                [
                    {
                        "Canal": item["canal"],
                        "Destino": mascara_destino(item["canal"], item["destino"]),
                        "Ativa": item["ativo"],
                        "Confirmada em": item["confirmado_em"],
                    }
                    for item in assinaturas
                ],
                hide_index=True,
                width="stretch",
            )
            por_id = {item["id"]: item for item in assinaturas}
            assinatura_id = st.selectbox(
                "Gerenciar assinatura",
                list(por_id),
                format_func=lambda codigo: (
                    f"{por_id[codigo]['canal']} · "
                    f"{mascara_destino(por_id[codigo]['canal'], por_id[codigo]['destino'])} · "
                    f"{'ativa' if por_id[codigo]['ativo'] else 'inativa'}"
                ),
            )
            escolhida = por_id[assinatura_id]
            with st.form("alterar-assinatura"):
                consentimento = st.checkbox(
                    "Confirmei consentimento do destinatário e controle deste contato.",
                    disabled=escolhida["ativo"],
                )
                atualizar = st.form_submit_button(
                    "Desativar" if escolhida["ativo"] else "Confirmar e ativar"
                )
            if atualizar:
                ativo = not escolhida["ativo"]
                if ativo and not consentimento:
                    st.error("Confirme o consentimento e a verificação antes de ativar.")
                else:
                    dados = {
                        "ativo": ativo,
                        "confirmado_em": (
                            datetime.now(timezone.utc).isoformat() if ativo else None
                        ),
                    }
                    alteracao = (
                        cliente.table("assinaturas_alerta")
                        .update(dados)
                        .eq("id", assinatura_id)
                        .eq("municipio_id", municipio_id)
                        .execute()
                    )
                    if not alteracao.data:
                        raise RuntimeError("Assinatura não alterada; verifique as permissões.")
                    st.success("Assinatura atualizada.")
                    st.rerun()
        with st.form("nova-assinatura"):
            canal = st.selectbox("Canal", ["telegram", "email"])
            destino = st.text_input(
                "E-mail ou identificador Telegram",
                help="O contato permanecerá inativo até verificação do consentimento.",
            ).strip()
            criar = st.form_submit_button("Cadastrar como inativa")
        if criar:
            if not destino or len(destino) > 320:
                st.error("Informe um destino válido com até 320 caracteres.")
            elif canal == "email" and (
                "@" not in destino or destino.startswith("@") or destino.endswith("@")
            ):
                st.error("Informe um endereço de e-mail válido.")
            else:
                insercao = (
                    cliente.table("assinaturas_alerta")
                    .insert(
                        {
                            "municipio_id": municipio_id,
                            "canal": canal,
                            "destino": destino,
                            "ativo": False,
                            "criado_por": perfil["id"],
                        }
                    )
                    .execute()
                )
                if not insercao.data:
                    raise RuntimeError("Assinatura não cadastrada.")
                st.success("Contato cadastrado inativo; confirme consentimento antes de ativar.")
                st.rerun()
    except Exception as erro:
        st.error(f"Não foi possível gerenciar assinaturas: {erro}")


def renderizar_pesquisador() -> None:
    st.title("Dados e metodologia")
    mostrar_aviso()
    st.markdown(
        "O índice é uma hipótese configurável, não validada oficialmente. "
        "Índices e alertas não são publicados anonimamente nesta fase; esta página "
        "exporta apenas cadastros municipais disponíveis pela leitura pública."
    )
    try:
        cliente = cliente_supabase()
        resultado = (
            cliente.table("municipios")
            .select("id_ibge,nome,uf,calha,populacao")
            .order("nome")
            .limit(1000)
            .execute()
        )
        dados = resultado.data or []
        st.dataframe(dados, hide_index=True, width="stretch")
        if dados:
            buffer = io.StringIO()
            escritor = csv.DictWriter(buffer, fieldnames=list(dados[0]))
            escritor.writeheader()
            escritor.writerows(dados)
            st.download_button(
                "Baixar municípios CSV",
                data=buffer.getvalue().encode("utf-8-sig"),
                file_name="municipios_am.csv",
                mime="text/csv",
            )
    except Exception as erro:
        st.error(f"Não foi possível carregar dados públicos: {erro}")


def renderizar_publico() -> None:
    st.title("Situação pública da Defesa Civil")
    st.caption("Consulte somente alertas que passaram por aprovação humana.")
    st.warning(AVISO_PROTOTIPO, icon="⚠️")
    st.info("Em situação de emergência, ligue para a Defesa Civil pelo número 199.")
    try:
        cliente = cliente_supabase()
        municipios = carregar_municipios(cliente)
        if not municipios:
            st.info("Não há municípios disponíveis.")
            return
        municipio_id = st.selectbox(
            "Município",
            list(municipios),
            format_func=lambda codigo: _nome_municipio(municipios, codigo),
        )
        situacao = (
            cliente.table("situacao_municipal")
            .select("data,situacao,fonte")
            .eq("municipio_id", municipio_id)
            .order("data", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        alertas = (
            cliente.table("alertas")
            .select("classe,texto,criado_em,emitido_em,status")
            .eq("municipio_id", municipio_id)
            .eq("status", "enviado")
            .order("criado_em", desc=True)
            .limit(20)
            .execute()
            .data
            or []
        )
        st.subheader("Situação municipal")
        if situacao:
            estado = situacao[0]
            st.write(f"**{estado['situacao'].title()}** — data: {estado['data']} — fonte: {estado['fonte']}")
        else:
            st.info("Sem atualização municipal disponível. Isso não significa situação normal.")
        st.subheader("Alertas emitidos")
        if not alertas:
            st.info("Não há alerta emitido publicado para este município.")
        for alerta in alertas:
            st.markdown(f"### {alerta['classe']} · {alerta['criado_em']}")
            st.write(alerta["texto"])
            st.caption(f"Emitido em: {alerta.get('emitido_em') or 'ainda não emitido'}")
    except Exception as erro:
        st.error(f"Não foi possível carregar a situação pública: {erro}")


def renderizar_administracao() -> None:
    st.title("Administração de perfis e regras")
    mostrar_aviso()
    try:
        cliente, _ = exigir_perfil({"administrador"})
        municipios = carregar_municipios(cliente)
        tabs = st.tabs(["Usuários", "Fontes", "Regras e pesos"])
        with tabs[0]:
            usuarios = (
                cliente.table("usuarios")
                .select("id,nome,perfil,municipio_id,auth_id")
                .order("nome")
                .limit(500)
                .execute()
                .data
                or []
            )
            st.dataframe(usuarios, hide_index=True, width="stretch")
            if usuarios:
                por_id = {item["id"]: item for item in usuarios}
                usuario_id = st.selectbox("Editar perfil", list(por_id))
                usuario = por_id[usuario_id]
                with st.form("editar-perfil"):
                    nome = st.text_input("Nome", value=usuario["nome"])
                    perfis = sorted(PERFIS_TODOS)
                    perfil_novo = st.selectbox(
                        "Perfil", perfis, index=perfis.index(usuario["perfil"])
                    )
                    codigos = [""] + list(municipios)
                    atual = usuario.get("municipio_id")
                    index_municipio = codigos.index(atual.strip()) if atual and atual.strip() in codigos else 0
                    municipio_novo = st.selectbox(
                        "Município (vazio para escopo nacional/estadual)",
                        codigos,
                        index=index_municipio,
                        format_func=lambda codigo: (
                            "— sem município —"
                            if not codigo
                            else _nome_municipio(municipios, codigo)
                        ),
                    )
                    salvar = st.form_submit_button("Salvar perfil")
                if salvar:
                    atualizado = (
                        cliente.table("usuarios")
                        .update(
                            {
                                "nome": nome.strip(),
                                "perfil": perfil_novo,
                                "municipio_id": municipio_novo or None,
                            }
                        )
                        .eq("id", usuario_id)
                        .execute()
                    )
                    if not atualizado.data:
                        raise RuntimeError("Perfil não alterado; confira o escopo de RLS.")
                    st.success("Perfil atualizado e auditado.")
            st.info(
                "Para criar a conta Auth: Supabase Dashboard > Authentication > Users. "
                "Depois associe o UUID Auth a uma linha de usuarios por um procedimento "
                "administrativo protegido. Não crie contas usando service_role no painel."
            )
        with tabs[1]:
            fontes = (
                cliente.table("fontes")
                .select("id,nome,tipo,status,ultima_verificacao,ultimo_erro")
                .order("nome")
                .execute()
                .data
                or []
            )
            st.dataframe(fontes, hide_index=True, width="stretch")
            if fontes:
                por_id = {fonte["id"]: fonte for fonte in fontes}
                fonte_id = st.selectbox(
                    "Atualizar estado da fonte",
                    list(por_id),
                    format_func=lambda codigo: (
                        f"{por_id[codigo]['nome']} — {por_id[codigo]['status']}"
                    ),
                )
                fonte = por_id[fonte_id]
                estados = ["pendente_confirmacao", "ativo", "erro"]
                estado_atual = fonte["status"] if fonte["status"] in estados else "erro"
                with st.form("editar-estado-fonte"):
                    estado = st.selectbox(
                        "Estado",
                        estados,
                        index=estados.index(estado_atual),
                    )
                    confirmar_fonte = st.checkbox(
                        "Para ativar: confirmei endpoint, formato e campos nos materiais oficiais."
                    )
                    st.caption(
                        "O estado é administrativo. Endpoints e credenciais dos "
                        "coletores continuam configurados em config/fontes.yaml."
                    )
                    salvar_estado = st.form_submit_button("Atualizar estado")
                if salvar_estado:
                    if estado == "ativo" and not confirmar_fonte:
                        st.error("Confirme os dados oficiais antes de ativar a fonte.")
                    else:
                        atualizado = (
                            cliente.table("fontes")
                            .update({"status": estado})
                            .eq("id", fonte_id)
                            .execute()
                        )
                        if not atualizado.data:
                            raise RuntimeError("Estado da fonte não foi atualizado.")
                        st.success("Estado atualizado.")
                        st.rerun()
        with tabs[2]:
            regras = (
                cliente.table("regras")
                .select("id,classe,condicao_json,acao_recomendada,reavaliar_em_horas,ativa")
                .order("classe")
                .execute()
                .data
                or []
            )
            st.dataframe(
                [
                    {
                        "Classe": regra["classe"],
                        "Condição": regra["condicao_json"],
                        "Ação": regra["acao_recomendada"],
                        "Reavaliar (h)": regra["reavaliar_em_horas"],
                        "Ativa": regra["ativa"],
                    }
                    for regra in regras
                ],
                hide_index=True,
                width="stretch",
            )
            classes = ["Normal", "Atenção", "Alerta", "Alto", "Crítico"]
            campos = {"score_total", *COMPONENTES}
            operadores = {
                "igual",
                "maior_que",
                "maior_ou_igual",
                "menor_que",
                "menor_ou_igual",
                "entre",
            }
            for regra in regras:
                with st.expander(f"Editar regra — {regra['classe']}"):
                    with st.form(f"regra-{regra['id']}"):
                        classe = st.selectbox(
                            "Classe",
                            classes,
                            index=classes.index(regra["classe"])
                            if regra["classe"] in classes
                            else 0,
                        )
                        condicao = st.text_area(
                            "Condição JSON",
                            value=json.dumps(
                                regra["condicao_json"],
                                ensure_ascii=False,
                                indent=2,
                            ),
                        )
                        acao = st.text_area(
                            "Ação recomendada",
                            value=regra["acao_recomendada"],
                        )
                        horas = st.number_input(
                            "Reavaliar após (horas)",
                            min_value=1,
                            step=1,
                            value=int(regra["reavaliar_em_horas"]),
                        )
                        ativa = st.checkbox("Ativa", value=bool(regra["ativa"]))
                        confirmar_regra = st.checkbox(
                            "Para ativar: limiar e ação foram revisados para uso operacional."
                        )
                        salvar_regra = st.form_submit_button("Salvar regra")
                    if salvar_regra:
                        try:
                            condicao_json = json.loads(condicao)
                            if (
                                not isinstance(condicao_json, dict)
                                or condicao_json.get("campo") not in campos
                                or condicao_json.get("operador") not in operadores
                            ):
                                raise ValueError(
                                    "Informe campo e operador reconhecidos pelo motor."
                                )
                            valor = condicao_json.get("valor")
                            if condicao_json["operador"] == "entre":
                                if (
                                    not isinstance(valor, list)
                                    or len(valor) != 2
                                    or not all(
                                        isinstance(item, (int, float))
                                        and not isinstance(item, bool)
                                        and math.isfinite(item)
                                        and 0 <= item <= 100
                                        for item in valor
                                    )
                                    or valor[0] > valor[1]
                                ):
                                    raise ValueError(
                                        "O operador 'entre' exige dois números ordenados."
                                    )
                            elif (
                                isinstance(valor, bool)
                                or not isinstance(valor, (int, float))
                                or not math.isfinite(valor)
                                or not 0 <= valor <= 100
                            ):
                                raise ValueError(
                                    "O valor deve ser um número finito entre 0 e 100."
                                )
                            if not acao.strip():
                                raise ValueError("A ação recomendada é obrigatória.")
                            if ativa and not confirmar_regra:
                                raise ValueError(
                                    "Confirme a revisão da regra antes de ativá-la."
                                )
                            atualizada = (
                                cliente.table("regras")
                                .update(
                                    {
                                        "classe": classe,
                                        "condicao_json": condicao_json,
                                        "acao_recomendada": acao.strip(),
                                        "reavaliar_em_horas": int(horas),
                                        "ativa": ativa,
                                    }
                                )
                                .eq("id", regra["id"])
                                .execute()
                            )
                            if not atualizada.data:
                                raise RuntimeError("Regra não atualizada.")
                            st.success("Regra atualizada.")
                            st.rerun()
                        except (ValueError, json.JSONDecodeError) as erro:
                            st.error(f"Regra inválida: {erro}")
                        except Exception as erro:
                            st.error(f"Não foi possível atualizar a regra: {erro}")

            pesos, validacao = carregar_pesos(cliente)
            st.caption(
                "Pesos hipotéticos sem validação oficial."
                if not validacao
                else "Pesos marcados como validados."
            )
            configuracao = (
                cliente.table("configuracao_pesos")
                .select("id,nome,validacao_oficial")
                .eq("nome", "hipotese_inicial_indice_impacto_humanitario")
                .limit(1)
                .execute()
                .data
                or []
            )
            if not configuracao:
                raise RuntimeError("Registro de pesos não encontrado.")
            with st.form("editar-pesos"):
                novos_pesos = {
                    componente: st.number_input(
                        componente.replace("_", " ").title(),
                        min_value=0.0,
                        max_value=100.0,
                        step=1.0,
                        value=float(pesos[componente]),
                    )
                    for componente in COMPONENTES
                }
                salvar_pesos = st.form_submit_button("Salvar pesos")
            if salvar_pesos:
                try:
                    validar_pesos(novos_pesos)
                    atualizacao = (
                        cliente.table("configuracao_pesos")
                        .update(
                            {
                                "pesos_json": novos_pesos,
                                "validacao_oficial": False,
                                "atualizado_em": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                            }
                        )
                        .eq("id", configuracao[0]["id"])
                        .execute()
                    )
                    if not atualizacao.data:
                        raise RuntimeError("Pesos não foram atualizados.")
                    st.success(
                        "Pesos salvos como hipótese não validada oficialmente."
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(f"Pesos inválidos: {erro}")
    except Exception as erro:
        st.error(f"Não foi possível abrir a administração: {erro}")
