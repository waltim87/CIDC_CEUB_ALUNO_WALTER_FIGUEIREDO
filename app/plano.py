"""Plano de Contingência operacional: protocolo por nível, acionamento e tarefas dos 5 eixos.

Fluxo: a coordenação monta o protocolo (o que fazer em Atenção, Alerta e Alto). Quando um
alerta é APROVADO, o banco aciona o plano e cria as tarefas com prazo e função responsável
(migration 202610140013). A coordenação também pode acionar manualmente. Cada equipe vê e
atualiza as suas tarefas em "Minhas tarefas".
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import streamlit as st

from core.notificacoes_telegram import notificar_responsaveis_por_funcao

EIXOS = {
    "prevencao": "Prevenção", "mitigacao": "Mitigação", "preparacao": "Preparação",
    "resposta": "Resposta", "recuperacao": "Recuperação",
}
NIVEIS = {"atencao": "🟡 Atenção", "alerta": "🟠 Alerta", "alto": "🔴 Alto"}
AMEACAS = {"qualquer": "Qualquer ameaça", "cheia": "Cheia / inundação", "seca": "Seca / vazante",
           "incendio": "Incêndio / fumaça"}
FUNCOES = {
    "coordenador_municipal": "Coordenação municipal", "operador_monitoramento": "Monitoramento",
    "agente_campo": "Agente de campo", "saude_assistencia": "Saúde e assistência",
    "logistica_abastecimento": "Logística", "voluntario": "Voluntários",
}
STATUS = {"pendente": "⏳ Pendente", "em_andamento": "🔧 Em andamento", "concluida": "✅ Concluída",
          "cancelada": "🚫 Cancelada"}
ABERTAS = {"pendente", "em_andamento"}
PERFIS_LEITURA = {"coordenador_municipal", "administrador", "voluntario", "gestor_nacional", "gestor_estadual",
                  "operador_monitoramento", "agente_campo", "saude_assistencia", "logistica_abastecimento"}
PERFIS_EQUIPE = {"operador_monitoramento", "agente_campo", "saude_assistencia", "logistica_abastecimento",
                 "coordenador_municipal", "voluntario"}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _instante(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        quando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def _data_br(valor: Any) -> str:
    quando = _instante(valor)
    return quando.astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m %H:%M") if quando else ""


def atrasada(tarefa: dict[str, Any], agora: datetime | None = None) -> bool:
    prazo = _instante(tarefa.get("prazo"))
    return bool(prazo and tarefa.get("status") in ABERTAS and prazo < (agora or _agora()))


def resumo_por_eixo(tarefas: list[dict[str, Any]], agora: datetime | None = None) -> dict[str, dict[str, int]]:
    saida = {e: {"abertas": 0, "atrasadas": 0, "concluidas": 0} for e in EIXOS}
    for t in tarefas:
        contagem = saida.setdefault(t["eixo"], {"abertas": 0, "atrasadas": 0, "concluidas": 0})
        if t["status"] in ABERTAS:
            contagem["abertas"] += 1
            contagem["atrasadas"] += atrasada(t, agora)
        elif t["status"] == "concluida":
            contagem["concluidas"] += 1
    return saida


def linhas_tarefas(tarefas: list[dict[str, Any]], agora: datetime | None = None) -> list[dict[str, Any]]:
    ordem = {"pendente": 0, "em_andamento": 1, "concluida": 2, "cancelada": 3}
    tarefas = sorted(tarefas, key=lambda t: (ordem.get(t["status"], 9), str(t.get("prazo") or "9")))
    return [
        {
            "Situação": ("⚠️ ATRASADA" if atrasada(t, agora) else STATUS.get(t["status"], t["status"])),
            "Eixo": EIXOS.get(t["eixo"], t["eixo"]),
            "Tarefa": t["descricao"],
            "Responsável": FUNCOES.get(t.get("responsavel_funcao"), t.get("responsavel_funcao") or "—"),
            "Prazo": _data_br(t.get("prazo")),
            "Origem": "plano" if t.get("origem") == "plano" else "manual",
            "Concluída em": _data_br(t.get("concluida_em")),
            "Observação": t.get("observacao") or "",
        }
        for t in tarefas
    ]


def _municipio_da_tela(cliente: Any, perfil: dict[str, Any], chave: str) -> str | None:
    from app.comum import carregar_municipios

    municipio_id = perfil.get("municipio_id")
    if perfil["perfil"] in {"voluntario", "gestor_nacional", "gestor_estadual"} or (
        perfil["perfil"] == "administrador" and not municipio_id
    ):
        municipios = carregar_municipios(cliente)
        codigos = sorted(municipios, key=lambda c: municipios[c]["nome"])
        if not codigos:
            return None
        municipio_id = st.selectbox(
            "Município", codigos, format_func=lambda c: f"{municipios[c]['nome']}/{municipios[c]['uf']}",
            index=codigos.index(municipio_id) if municipio_id in codigos else 0, key=f"municipio-{chave}",
        )
    return municipio_id


# ---------------------------------------------------------------- tarefas
def _carregar_tarefas(cliente: Any, municipio_id: str) -> list[dict[str, Any]]:
    return (
        cliente.table("acoes").select("*").eq("municipio_id", municipio_id)
        .order("prazo").limit(2000).execute().data or []
    )


def _form_status(cliente: Any, tarefas: list[dict[str, Any]], chave: str) -> None:
    abertas = {t["id"]: t for t in tarefas if t["status"] in ABERTAS}
    if not abertas:
        return
    with st.form(f"status-{chave}", clear_on_submit=True):
        st.markdown("**Atualizar uma tarefa**")
        tarefa_id = st.selectbox(
            "Tarefa", list(abertas),
            format_func=lambda i: f"{EIXOS[abertas[i]['eixo']]} · {abertas[i]['descricao'][:70]} · prazo "
                                  f"{_data_br(abertas[i].get('prazo'))}",
        )
        c1, c2 = st.columns([1, 2])
        novo = c1.selectbox("Nova situação", ["em_andamento", "concluida", "cancelada", "pendente"],
                            format_func=STATUS.get)
        observacao = c2.text_input("Observação (o que foi feito, quem, onde)", max_chars=300)
        if st.form_submit_button("Salvar", type="primary"):
            dados: dict[str, Any] = {"status": novo}
            if observacao.strip():
                dados["observacao"] = observacao.strip()
            try:
                feito = cliente.table("acoes").update(dados).eq("id", tarefa_id).execute()
                if not feito.data:
                    st.error("Você não tem permissão para atualizar esta tarefa (ela é de outra equipe).")
                    return
            except Exception as erro:
                st.error(f"Não foi possível atualizar: {erro}")
                return
            st.success("Tarefa atualizada.")
            st.rerun()


def bloco_tarefas(
    cliente: Any, perfil: dict[str, Any], municipio_id: str, editavel: bool, tarefas: list[dict] | None = None
) -> list[dict[str, Any]]:
    """Tarefas dos 5 eixos do município: resumo, lista com atrasos, atualização e criação manual."""
    if tarefas is None:
        tarefas = _carregar_tarefas(cliente, municipio_id)
    resumo = resumo_por_eixo(tarefas)
    colunas = st.columns(len(EIXOS))
    for coluna, (eixo, rotulo) in zip(colunas, EIXOS.items()):
        r = resumo[eixo]
        coluna.metric(rotulo, f"{r['abertas']} abertas", f"{r['atrasadas']} atrasadas" if r["atrasadas"] else None,
                      delta_color="inverse")
        coluna.caption(f"{r['concluidas']} concluídas")

    c1, c2, c3 = st.columns(3)
    ver = c1.radio("Mostrar", ["abertas", "todas"], horizontal=True, key=f"ver-{municipio_id}",
                   format_func=lambda v: "Só abertas" if v == "abertas" else "Todas")
    eixo = c2.selectbox("Eixo", ["todos"] + list(EIXOS), key=f"eixo-{municipio_id}",
                        format_func=lambda e: "Todos" if e == "todos" else EIXOS[e])
    funcao = c3.selectbox("Responsável", ["todos"] + list(FUNCOES), key=f"funcao-{municipio_id}",
                          format_func=lambda f: "Todos" if f == "todos" else FUNCOES[f])
    filtradas = [t for t in tarefas
                 if (ver == "todas" or t["status"] in ABERTAS)
                 and (eixo == "todos" or t["eixo"] == eixo)
                 and (funcao == "todos" or t.get("responsavel_funcao") == funcao)]
    if filtradas:
        st.dataframe(linhas_tarefas(filtradas), hide_index=True, width="stretch")
    elif tarefas:
        st.info("Nenhuma tarefa com esses filtros.")
    else:
        st.info("Nenhuma tarefa ainda. Elas são criadas ao acionar o plano (ou manualmente abaixo).")

    # Gestores e voluntários só leem aqui (voluntário atualiza as suas em "Minhas tarefas").
    if perfil["perfil"] in PERFIS_EQUIPE - {"voluntario"} | {"administrador"}:
        _form_status(cliente, filtradas or tarefas, f"mun-{municipio_id}")
    if editavel:
        with st.expander("➕ Nova tarefa manual (qualquer eixo, sem precisar de alerta)"):
            with st.form(f"nova-tarefa-{municipio_id}", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                novo_eixo = c1.selectbox("Eixo", list(EIXOS), format_func=EIXOS.get)
                nova_funcao = c2.selectbox("Responsável", list(FUNCOES), format_func=FUNCOES.get)
                prazo = c3.date_input("Prazo", value=date.today() + timedelta(days=7), format="DD/MM/YYYY")
                descricao = st.text_input("Tarefa", max_chars=300,
                                          placeholder="Ex.: Vistoriar a contenção da orla do bairro São José")
                if st.form_submit_button("Criar tarefa"):
                    if len(descricao.strip()) < 5:
                        st.error("Descreva a tarefa.")
                    else:
                        try:
                            cliente.table("acoes").insert({
                                "municipio_id": municipio_id, "eixo": novo_eixo, "descricao": descricao.strip(),
                                "responsavel_funcao": nova_funcao, "origem": "manual",
                                "prazo": datetime.combine(prazo, time(18), timezone(timedelta(hours=-4))).isoformat(),
                            }).execute()
                            # Avisa via Telegram os responsáveis da função que têm Telegram vinculado (opt-in).
                            prazo_texto = prazo.strftime("%d/%m/%Y")
                            notificar_responsaveis_por_funcao(
                                cliente, municipio_id, nova_funcao, descricao.strip(),
                                prazo_texto,
                            )
                            st.success("Tarefa criada. Aviso enviado por Telegram para quem tem cadastro ativo.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível criar: {erro}")
    return linhas_tarefas(tarefas)


# ---------------------------------------------------------------- protocolo
def _bloco_protocolo(cliente: Any, municipio_id: str, editavel: bool) -> list[dict[str, Any]]:
    protocolo = (
        cliente.table("plano_protocolo").select("*").eq("municipio_id", municipio_id)
        .order("ordem").limit(500).execute().data or []
    )
    if not protocolo:
        st.info("Este município ainda não tem protocolo. Sem protocolo, aprovar um alerta não cria tarefas.")
        if editavel:
            st.markdown("Comece pelo **modelo sugerido** (20 ações para municípios ribeirinhos: cheia, seca e "
                        "incêndio) e ajuste ao plano oficial do município.")
            if st.button("Carregar modelo sugerido", type="primary", key=f"modelo-{municipio_id}"):
                try:
                    total = cliente.rpc("cidc_carregar_modelo_plano", {"p_municipio_id": municipio_id}).execute().data
                    st.success(f"{total} ações carregadas. Revise abaixo.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível carregar: {erro}")
        return []

    st.caption("No nível **Alto** entram também as ações de Atenção e Alerta que ainda não foram feitas. "
               "Ações de \"qualquer ameaça\" valem para cheia, seca e incêndio.")
    linhas = [
        {"id": p["id"], "Nível": p["nivel"], "Ameaça": p["ameaca"], "Eixo": p["eixo"], "Ação": p["descricao"],
         "Responsável": p.get("responsavel_funcao"), "Prazo (horas)": p["prazo_horas"], "Ativa": p["ativo"]}
        for p in sorted(protocolo, key=lambda p: (list(NIVEIS).index(p["nivel"]), p["ordem"]))
    ]
    configuracao = {
        "id": None,
        "Nível": st.column_config.SelectboxColumn(options=list(NIVEIS), required=True, width="small"),
        "Ameaça": st.column_config.SelectboxColumn(options=list(AMEACAS), required=True, width="small"),
        "Eixo": st.column_config.SelectboxColumn(options=list(EIXOS), required=True, width="small"),
        "Ação": st.column_config.TextColumn(required=True, max_chars=300, width="large"),
        "Responsável": st.column_config.SelectboxColumn(options=list(FUNCOES), width="medium"),
        "Prazo (horas)": st.column_config.NumberColumn(min_value=1, max_value=2160, step=1, required=True, width="small"),
        "Ativa": st.column_config.CheckboxColumn(width="small"),
    }
    legenda = ("Níveis: atencao, alerta, alto · Ameaças: qualquer, cheia, seca, incendio · Responsável: "
               + ", ".join(FUNCOES))
    if not editavel:
        st.dataframe([{k: v for k, v in l.items() if k != "id"} for l in linhas], hide_index=True, width="stretch")
        return _linhas_relatorio(linhas)

    st.caption("Edite direto na tabela; para incluir, use a última linha; para excluir, selecione a linha e "
               "aperte Delete. Depois clique em **Salvar protocolo**. " + legenda)
    editado = st.data_editor(linhas, column_config=configuracao, num_rows="dynamic", hide_index=True,
                             width="stretch", key=f"protocolo-{municipio_id}")
    if st.button("Salvar protocolo", type="primary", key=f"salvar-protocolo-{municipio_id}"):
        salvar_protocolo(cliente, municipio_id, linhas, editado)
    return _linhas_relatorio(linhas)


def _linhas_relatorio(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"Nível": NIVEIS.get(l["Nível"], l["Nível"]).split(" ", 1)[-1], "Ameaça": AMEACAS.get(l["Ameaça"], l["Ameaça"]),
         "Eixo": EIXOS.get(l["Eixo"], l["Eixo"]), "Ação": l["Ação"],
         "Responsável": FUNCOES.get(l["Responsável"], l["Responsável"] or "—"),
         "Prazo (h)": l["Prazo (horas)"], "Ativa": "sim" if l["Ativa"] else "não"}
        for l in linhas
    ]


def diferencas_protocolo(
    originais: list[dict[str, Any]], editados: list[dict[str, Any]]
) -> tuple[list[dict], list[tuple[str, dict]], list[str], list[str]]:
    """(novas, alteradas, excluídas, erros) entre a tabela original e a editada."""
    import math

    def limpo(valor: Any) -> Any:
        return None if isinstance(valor, float) and math.isnan(valor) else valor

    if hasattr(editados, "to_dict"):
        editados = editados.to_dict("records")
    editados = [{k: limpo(v) for k, v in linha.items()} for linha in editados]
    campos = {"Nível": "nivel", "Ameaça": "ameaca", "Eixo": "eixo", "Ação": "descricao",
              "Responsável": "responsavel_funcao", "Prazo (horas)": "prazo_horas", "Ativa": "ativo"}
    por_id = {l["id"]: l for l in originais}
    novas, alteradas, erros = [], [], []
    vistos = set()
    for posicao, linha in enumerate(editados, start=1):
        dados = {coluna: linha.get(origem) for origem, coluna in campos.items()}
        if not any(v not in (None, "", False) for v in dados.values()):
            continue
        dados["descricao"] = str(dados["descricao"] or "").strip()
        if (dados["nivel"] not in NIVEIS or dados["ameaca"] not in AMEACAS or dados["eixo"] not in EIXOS
                or len(dados["descricao"]) < 5 or not dados["prazo_horas"]):
            erros.append(f"Linha {posicao}: preencha nível, ameaça, eixo, ação (5+ letras) e prazo.")
            continue
        dados["prazo_horas"] = int(dados["prazo_horas"])
        dados["ativo"] = bool(dados["ativo"]) if dados["ativo"] is not None else True
        if dados["responsavel_funcao"] not in FUNCOES:
            dados["responsavel_funcao"] = None
        identificador = linha.get("id")
        if identificador and identificador in por_id:
            vistos.add(identificador)
            original = {coluna: por_id[identificador].get(origem) for origem, coluna in campos.items()}
            if dados != original:
                alteradas.append((identificador, dados))
        else:
            novas.append(dados)
    excluidas = [i for i in por_id if i not in vistos]
    return novas, alteradas, excluidas, erros


def salvar_protocolo(cliente: Any, municipio_id: str, originais: list[dict], editados: list[dict]) -> None:
    novas, alteradas, excluidas, erros = diferencas_protocolo(originais, editados)
    if erros:
        for erro in erros:
            st.error(erro)
        return
    try:
        for dados in novas:
            cliente.table("plano_protocolo").insert({**dados, "municipio_id": municipio_id, "ordem": 500}).execute()
        for identificador, dados in alteradas:
            cliente.table("plano_protocolo").update(dados).eq("id", identificador).execute()
        if excluidas:
            cliente.table("plano_protocolo").delete().in_("id", excluidas).execute()
    except Exception as erro:
        st.error(f"Não foi possível salvar o protocolo: {erro}")
        return
    st.success(f"Protocolo salvo: {len(novas)} nova(s), {len(alteradas)} alterada(s), {len(excluidas)} excluída(s).")
    st.rerun()


# ---------------------------------------------------------------- acionamentos
def _bloco_acionamentos(cliente: Any, municipio_id: str, editavel: bool, tarefas: list[dict]) -> list[dict]:
    acionamentos = (
        cliente.table("plano_acionamentos").select("*").eq("municipio_id", municipio_id)
        .order("acionado_em", desc=True).limit(100).execute().data or []
    )
    por_acionamento: dict[str, list[dict]] = {}
    for t in tarefas:
        if t.get("acionamento_id"):
            por_acionamento.setdefault(t["acionamento_id"], []).append(t)
    abertos = [a for a in acionamentos if not a.get("encerrado_em")]
    if abertos:
        for a in abertos:
            feitas = sum(1 for t in por_acionamento.get(a["id"], []) if t["status"] in {"concluida", "cancelada"})
            total = len(por_acionamento.get(a["id"], []))
            st.error(f"**Plano ACIONADO — {NIVEIS[a['nivel']]} · {AMEACAS[a['ameaca']]}** desde "
                     f"{_data_br(a['acionado_em'])} ({'alerta aprovado' if a['origem'] == 'alerta_aprovado' else 'manual'}). "
                     f"Tarefas: {feitas} de {total} resolvidas.")
            if total:
                st.progress(feitas / total)
            if editavel and st.button("Encerrar este acionamento", key=f"encerrar-{a['id']}"):
                cliente.table("plano_acionamentos").update({"encerrado_em": _agora().isoformat()}).eq("id", a["id"]).execute()
                st.rerun()
    else:
        st.success("Nenhum acionamento em andamento.")

    if editavel:
        with st.form(f"acionar-{municipio_id}"):
            st.markdown("**Acionar o plano agora** (sem esperar um alerta aprovado)")
            c1, c2 = st.columns(2)
            nivel = c1.selectbox("Nível", list(NIVEIS), format_func=NIVEIS.get, index=1)
            ameaca = c2.selectbox("Ameaça", list(AMEACAS), format_func=AMEACAS.get, index=1)
            observacao = st.text_input("Motivo", placeholder="Ex.: régua do porto passou de 17 m; relatos de alagamento")
            if st.form_submit_button("Acionar plano", type="primary"):
                try:
                    cliente.rpc("cidc_acionar_plano", {"p_municipio_id": municipio_id, "p_nivel": nivel,
                                                       "p_ameaca": ameaca, "p_observacao": observacao}).execute()
                    st.success("Plano acionado; as tarefas foram criadas.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível acionar: {erro}")
        st.caption("Automático: quando um alerta deste município é **aprovado**, o plano é acionado no nível do "
                   "alerta. O robô só cria rascunhos; quem decide é sempre uma pessoa.")

    historico = [
        {"Acionado em": _data_br(a["acionado_em"]), "Nível": NIVEIS[a["nivel"]].split(" ", 1)[1],
         "Ameaça": AMEACAS[a["ameaca"]], "Origem": "alerta aprovado" if a["origem"] == "alerta_aprovado" else "manual",
         "Tarefas criadas": a["tarefas_criadas"], "Encerrado em": _data_br(a.get("encerrado_em")) or "em andamento",
         "Motivo": a.get("observacao") or ""}
        for a in acionamentos
    ]
    if historico:
        st.markdown("**Histórico de acionamentos**")
        st.dataframe(historico, hide_index=True, width="stretch")
    return historico


# ---------------------------------------------------------------- páginas
def renderizar_plano() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.relatorio_menu import painel_relatorio

    st.title("📋 Plano de contingência")
    st.caption("O que cada equipe faz em cada nível de risco. Ao aprovar um alerta, as tarefas são criadas "
               "sozinhas, com prazo e responsável, nos 5 eixos: prevenção, mitigação, preparação, resposta e "
               "recuperação.")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil(PERFIS_LEITURA)
        municipio_id = _municipio_da_tela(cliente, perfil, "plano")
        if not municipio_id:
            st.info("Associe um município ao seu perfil para abrir o plano.")
            return
        editavel = perfil["perfil"] == "administrador" or (
            perfil["perfil"] == "coordenador_municipal" and perfil.get("municipio_id") == municipio_id)
        municipio = carregar_municipios(cliente).get(municipio_id)
        tarefas_brutas = _carregar_tarefas(cliente, municipio_id)
        aba_acionamento, aba_tarefas, aba_protocolo = st.tabs(["🚨 Acionamento", "✅ Tarefas", "📋 Protocolo"])
        with aba_acionamento:
            historico = _bloco_acionamentos(cliente, municipio_id, editavel, tarefas_brutas)
        with aba_tarefas:
            tarefas = bloco_tarefas(cliente, perfil, municipio_id, editavel, tarefas_brutas)
        with aba_protocolo:
            protocolo = _bloco_protocolo(cliente, municipio_id, editavel)
    except Exception as erro:
        st.error(f"Não foi possível carregar o plano (aplique a migration 202610140013): {erro}")
        return
    resumo = resumo_por_eixo(tarefas_brutas)
    painel_relatorio(
        "Plano de contingência",
        [("Acionamentos", historico), ("Tarefas", tarefas), ("Protocolo", protocolo)],
        subtitulo=f"{municipio['nome']}/{municipio['uf']}" if municipio else municipio_id,
        resumo={f"{EIXOS[e]} (abertas / atrasadas / concluídas)": f"{r['abertas']} / {r['atrasadas']} / {r['concluidas']}"
                for e, r in resumo.items()},
    )


def renderizar_minhas_tarefas() -> None:
    from app.comum import exigir_perfil

    st.title("✅ Minhas tarefas")
    try:
        cliente, perfil = exigir_perfil(PERFIS_EQUIPE)
    except Exception as erro:
        st.error(str(erro))
        return
    municipio_id = perfil.get("municipio_id")
    funcao = perfil["perfil"]
    try:
        consulta = cliente.table("acoes").select("*").order("prazo").limit(500)
        if funcao == "coordenador_municipal":
            dados = consulta.eq("municipio_id", municipio_id).execute().data or []
        else:
            dados = consulta.or_(f"responsavel_id.eq.{perfil['id']},and(responsavel_funcao.eq.{funcao},"
                                 f"municipio_id.eq.{municipio_id})").execute().data or []
    except Exception as erro:
        st.error(f"Não foi possível carregar as tarefas: {erro}")
        return
    abertas = [t for t in dados if t["status"] in ABERTAS]
    atrasadas = [t for t in abertas if atrasada(t)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Abertas", len(abertas))
    c2.metric("Atrasadas", len(atrasadas))
    c3.metric("Concluídas", sum(1 for t in dados if t["status"] == "concluida"))
    st.caption(f"Tarefas da função **{FUNCOES.get(funcao, funcao)}** no seu município"
               + (" (todas, como coordenação)" if funcao == "coordenador_municipal" else "") + ".")
    if not abertas:
        st.success("Nenhuma tarefa aberta para você agora.")
    else:
        st.dataframe(linhas_tarefas(abertas), hide_index=True, width="stretch")
        _form_status(cliente, abertas, "minhas")
    concluidas = [t for t in dados if t["status"] not in ABERTAS]
    if concluidas:
        with st.expander(f"Concluídas e canceladas ({len(concluidas)})"):
            st.dataframe(linhas_tarefas(concluidas), hide_index=True, width="stretch")
