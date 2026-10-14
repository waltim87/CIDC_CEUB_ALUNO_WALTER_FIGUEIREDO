"""Formulários de cadastro dos painéis (comunidades, recursos, abrigos, plano,
infraestrutura/saúde e situação oficial).

Cada bloco mostra os dados atuais, um formulário para incluir/atualizar e
DEVOLVE as linhas exibidas, usadas pelo relatório do menu. As permissões são
do banco (RLS por perfil e município). Estabelecimentos de saúde vêm do CNES
(importação semanal, collectors/cnes.py) e podem ser complementados à mão.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import streamlit as st

TIPOS_RECURSO = {
    "agua": ("Água", "litros"),
    "alimento": ("Alimento", "cestas"),
    "medicamento": ("Medicamento", "kits"),
    "oxigenio": ("Oxigênio", "cilindros"),
    "combustivel": ("Combustível", "litros"),
    "purificador": ("Purificador de água", "unidades"),
}
TIPOS_INFRA = {
    "ubs": "Estabelecimento de saúde",
    "escola": "Escola",
    "porto": "Porto / atracadouro",
    "captacao": "Captação de água",
    "energia": "Energia (usina/subestação)",
}
ACESSOS = ["fluvial", "terrestre", "aéreo", "fluvial e terrestre", "outro"]
TIPOS_ABRIGO = ["escola", "ginásio", "igreja", "centro comunitário", "outro"]
SITUACOES = {"normal": "Normal", "atencao": "Atenção", "alerta": "Alerta", "emergencia": "Emergência"}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data(valor: Any) -> str:
    texto = str(valor or "")
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) >= 10 else texto


def _sim_nao(valor: Any) -> str:
    return "" if valor is None else ("sim" if valor else "não")


def _local(lat: float | None, lon: float | None) -> dict[str, Any]:
    """Colunas de localização: lat/lon legíveis e geom (EWKT) para consultas espaciais."""
    if lat is None or lon is None:
        return {}
    return {"latitude": lat, "longitude": lon, "geom": f"SRID=4326;POINT({lon} {lat})"}


def _executar(acao: Any, sucesso: str) -> bool:
    try:
        resposta = acao.execute()
    except Exception as erro:
        texto = str(erro)
        if "row-level security" in texto or "42501" in texto:
            st.error("Seu perfil não tem permissão para gravar este dado neste município.")
        elif "column" in texto and ("does not exist" in texto or "schema cache" in texto):
            st.error("Faltam colunas novas no banco: aplique a migration 202610140006 no Supabase.")
        else:
            st.error(f"Não foi possível salvar: {texto}")
        return False
    if getattr(resposta, "data", None) == []:
        st.error("O banco não confirmou a gravação (verifique a permissão do seu perfil).")
        return False
    st.success(sucesso)
    return True


def _ler(cliente: Any, tabela: str, municipio_id: str, ordem: str | None = None, **filtros: Any) -> list[dict]:
    consulta = cliente.table(tabela).select("*").eq("municipio_id", municipio_id)
    for coluna, valores in filtros.items():
        consulta = consulta.in_(coluna, valores)
    if ordem:
        consulta = consulta.order(ordem)
    return consulta.limit(2000).execute().data or []


def _coordenadas(prefixo: str) -> tuple[float | None, float | None]:
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude (opcional)", value=None, format="%.5f", key=f"{prefixo}-lat",
                          min_value=-90.0, max_value=90.0, placeholder="-3.10000")
    lon = c2.number_input("Longitude (opcional)", value=None, format="%.5f", key=f"{prefixo}-lon",
                          min_value=-180.0, max_value=180.0, placeholder="-60.00000")
    return lat, lon


CAMPOS_PESSOAIS = {"Telefone", "Contato", "Responsável"}


def _mascarar(valor: Any) -> Any:
    texto = str(valor or "")
    return f"***{texto[-2:]}" if len(texto) > 2 else ("***" if texto else valor)


def _tabela(linhas: list[dict], mascarar: bool = False) -> list[dict]:
    """Exibe a tabela; no modo leitura (voluntário) mascara contatos pessoais na tela."""
    exibidas = [
        {k: (_mascarar(v) if k in CAMPOS_PESSOAIS else v) for k, v in linha.items()} for linha in linhas
    ] if mascarar else linhas
    st.dataframe(exibidas, hide_index=True, width="stretch")
    return exibidas


# ---------------------------------------------------------------- comunidades
def bloco_comunidades(cliente: Any, municipio_id: str, editavel: bool = True) -> list[dict]:
    dados = _ler(cliente, "comunidades", municipio_id, "nome")
    linhas = _tabela([
        {"Comunidade": d["nome"], "População estimada": d.get("populacao_estimada"),
         "Fonte da população": d.get("populacao_fonte"), "Acesso": d.get("acesso_principal"),
         "Rio": d.get("rio"), "Distância da sede (km)": d.get("distancia_sede_km"),
         "Tempo de acesso (h)": d.get("tempo_acesso_horas"), "Contato": d.get("contato_nome"),
         "Telefone": d.get("contato_telefone"), "Observações": d.get("observacoes")}
        for d in dados
    ], mascarar=not editavel)
    if not editavel:
        return linhas
    with st.form(f"nova-comunidade-{municipio_id}", clear_on_submit=True):
        st.markdown("**Cadastrar comunidade**")
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome da comunidade *")
        rio = c2.text_input("Rio / igarapé")
        c1, c2, c3 = st.columns(3)
        populacao = c1.number_input("População estimada", min_value=0, step=10)
        fonte_pop = c2.text_input("Fonte da população", placeholder="Ex.: ACS, censo indígena, liderança")
        acesso = c3.selectbox("Acesso principal", ACESSOS)
        c1, c2 = st.columns(2)
        distancia = c1.number_input("Distância da sede (km)", min_value=0.0, step=1.0)
        tempo = c2.number_input("Tempo de acesso (horas)", min_value=0.0, step=0.5)
        c1, c2 = st.columns(2)
        contato = c1.text_input("Contato local (liderança, ACS)")
        telefone = c2.text_input("Telefone / rádio")
        observacoes = st.text_area("Observações", placeholder="Ex.: fica isolada na seca abaixo de 300 cm")
        lat, lon = _coordenadas(f"com-{municipio_id}")
        if st.form_submit_button("Salvar comunidade"):
            if not nome.strip():
                st.error("Informe o nome da comunidade.")
            elif _executar(
                cliente.table("comunidades").insert({
                    "municipio_id": municipio_id, "nome": nome.strip(), "rio": rio.strip() or None,
                    "populacao_estimada": int(populacao) or None, "populacao_fonte": fonte_pop.strip() or None,
                    "acesso_principal": acesso, "distancia_sede_km": distancia or None,
                    "tempo_acesso_horas": tempo or None, "contato_nome": contato.strip() or None,
                    "contato_telefone": telefone.strip() or None, "observacoes": observacoes.strip() or None,
                    **_local(lat, lon),
                }),
                f"Comunidade {nome.strip()} cadastrada.",
            ):
                st.rerun()
    return linhas


# ---------------------------------------------------------------- recursos
def bloco_recursos(cliente: Any, municipio_id: str, tipos: list[str] | None = None, editavel: bool = True) -> list[dict]:
    tipos = tipos or list(TIPOS_RECURSO)
    dados = _ler(cliente, "recursos", municipio_id, "tipo", tipo=tipos)
    hoje = date.today().isoformat()
    linhas = _tabela([
        {"Recurso": TIPOS_RECURSO.get(d["tipo"], (d["tipo"],))[0], "Quantidade": d["quantidade"],
         "Unidade": d.get("unidade") or TIPOS_RECURSO.get(d["tipo"], ("", ""))[1],
         "Local de armazenamento": d.get("local_armazenamento"), "Validade": _data(d.get("validade")),
         "Vencido": "SIM" if d.get("validade") and str(d["validade"]) < hoje else "",
         "Responsável": d.get("responsavel"),
         "Atualizado em (UTC)": str(d.get("atualizado_em") or "")[:16].replace("T", " ")}
        for d in dados
    ], mascarar=not editavel)
    if not editavel:
        return linhas
    with st.form(f"recurso-{municipio_id}-{'-'.join(tipos)}", clear_on_submit=True):
        st.markdown("**Atualizar estoque** (substitui a quantidade atual do item)")
        c1, c2 = st.columns(2)
        tipo = c1.selectbox("Item", tipos, format_func=lambda t: f"{TIPOS_RECURSO[t][0]} ({TIPOS_RECURSO[t][1]})")
        quantidade = c2.number_input("Quantidade disponível agora", min_value=0.0, step=1.0)
        c1, c2, c3 = st.columns(3)
        local = c1.text_input("Local de armazenamento")
        validade = c2.date_input("Validade (opcional)", value=None, format="DD/MM/YYYY")
        responsavel = c3.text_input("Responsável")
        observacoes = st.text_input("Observações")
        if st.form_submit_button("Salvar estoque"):
            existente = next((d for d in dados if d["tipo"] == tipo), None)
            valores = {
                "quantidade": quantidade, "atualizado_em": _agora(), "unidade": TIPOS_RECURSO[tipo][1],
                "local_armazenamento": local.strip() or None,
                "validade": validade.isoformat() if validade else None,
                "responsavel": responsavel.strip() or None, "observacoes": observacoes.strip() or None,
            }
            acao = (
                cliente.table("recursos").update(valores).eq("id", existente["id"])
                if existente
                else cliente.table("recursos").insert({"municipio_id": municipio_id, "tipo": tipo, **valores})
            )
            if _executar(acao, f"Estoque de {TIPOS_RECURSO[tipo][0].lower()} atualizado."):
                st.rerun()
    return linhas


# ---------------------------------------------------------------- abrigos
def bloco_abrigos(cliente: Any, municipio_id: str, editavel: bool = True) -> list[dict]:
    dados = _ler(cliente, "abrigos", municipio_id, "nome")
    linhas = _tabela([
        {"Abrigo": d["nome"], "Tipo": d.get("tipo_local"), "Endereço": d.get("endereco"),
         "Capacidade": d["capacidade"], "Ocupação": d["ocupacao"], "Vagas": d["capacidade"] - d["ocupacao"],
         "Ocupação (%)": round(d["ocupacao"] / d["capacidade"] * 100) if d["capacidade"] else None,
         "Água": _sim_nao(d.get("possui_agua")), "Energia": _sim_nao(d.get("possui_energia")),
         "Banheiro": _sim_nao(d.get("possui_banheiro")), "Acessível": _sim_nao(d.get("acessivel")),
         "Responsável": d.get("responsavel"), "Telefone": d.get("telefone")}
        for d in dados
    ], mascarar=not editavel)
    if not editavel:
        return linhas
    c1, c2 = st.columns([3, 2])
    with c1, st.form(f"novo-abrigo-{municipio_id}", clear_on_submit=True):
        st.markdown("**Cadastrar abrigo**")
        a, b = st.columns(2)
        nome = a.text_input("Nome do abrigo *")
        tipo_local = b.selectbox("Tipo de local", TIPOS_ABRIGO)
        endereco = st.text_input("Endereço")
        a, b, c = st.columns(3)
        capacidade = a.number_input("Capacidade (pessoas)", min_value=0, step=10)
        responsavel = b.text_input("Responsável")
        telefone = c.text_input("Telefone")
        a, b, c, d = st.columns(4)
        agua = a.checkbox("Água")
        energia = b.checkbox("Energia")
        banheiro = c.checkbox("Banheiro")
        acessivel = d.checkbox("Acessível")
        observacoes = st.text_input("Observações")
        lat, lon = _coordenadas(f"abr-{municipio_id}")
        if st.form_submit_button("Salvar abrigo"):
            if not nome.strip():
                st.error("Informe o nome do abrigo.")
            elif _executar(
                cliente.table("abrigos").insert({
                    "municipio_id": municipio_id, "nome": nome.strip(), "tipo_local": tipo_local,
                    "endereco": endereco.strip() or None, "capacidade": int(capacidade), "ocupacao": 0,
                    "responsavel": responsavel.strip() or None, "telefone": telefone.strip() or None,
                    "possui_agua": agua, "possui_energia": energia, "possui_banheiro": banheiro,
                    "acessivel": acessivel, "observacoes": observacoes.strip() or None, **_local(lat, lon),
                }),
                f"Abrigo {nome.strip()} cadastrado.",
            ):
                st.rerun()
    if dados:
        with c2, st.form(f"ocupacao-abrigo-{municipio_id}"):
            st.markdown("**Atualizar ocupação**")
            abrigo_id = st.selectbox("Abrigo", [d["id"] for d in dados],
                                     format_func=lambda i: next(d["nome"] for d in dados if d["id"] == i))
            atual = next(d for d in dados if d["id"] == abrigo_id)
            ocupacao = st.number_input("Pessoas abrigadas agora", min_value=0,
                                       max_value=int(atual["capacidade"]), step=1)
            if st.form_submit_button("Salvar ocupação") and _executar(
                cliente.table("abrigos").update({"ocupacao": int(ocupacao), "atualizado_em": _agora()}).eq("id", abrigo_id),
                "Ocupação atualizada.",
            ):
                st.rerun()
    return linhas


# ---------------------------------------------------------------- plano
def bloco_plano(cliente: Any, municipio_id: str, editavel: bool = True) -> list[dict]:
    dados = _ler(cliente, "planos_contingencia", municipio_id)
    plano = dados[0] if dados else {}
    linhas = []
    if plano:
        linhas = [{"Atualizado em": _data(plano.get("atualizado_em")), "Validade": _data(plano.get("validade")),
                   "Réguas instaladas": _sim_nao(plano.get("possui_reguas")), "Responsável": plano.get("responsavel"),
                   "Telefone": plano.get("telefone"), "Documento": plano.get("link_documento"),
                   "Rotas alternativas": "; ".join(plano.get("rotas_alternativas") or [])}]
        linhas = _tabela(linhas, mascarar=not editavel)
    else:
        st.info("Plano de contingência ainda não registrado.")
    if not editavel:
        return linhas
    with st.form(f"plano-{municipio_id}"):
        st.markdown("**Registrar / atualizar plano de contingência**")
        c1, c2, c3 = st.columns(3)
        responsavel = c1.text_input("Responsável", value=plano.get("responsavel") or "")
        telefone = c2.text_input("Telefone", value=plano.get("telefone") or "")
        validade = c3.date_input(
            "Validade do plano",
            value=date.fromisoformat(str(plano["validade"])[:10]) if plano.get("validade") else None,
            format="DD/MM/YYYY",
        )
        link = st.text_input("Link do documento (PDF/Drive)", value=plano.get("link_documento") or "")
        reguas = st.checkbox("Réguas linimétricas instaladas", value=bool(plano.get("possui_reguas")))
        rotas = st.text_area(
            "Rotas alternativas (uma por linha)",
            value="\n".join(plano.get("rotas_alternativas") or []),
            placeholder="Ex.: Rio Purus até Lábrea por balsa (seca: canal pelo paraná X)",
        )
        observacoes = st.text_input("Observações", value=plano.get("observacoes") or "")
        if st.form_submit_button("Salvar plano") and _executar(
            cliente.table("planos_contingencia").upsert(
                {
                    "municipio_id": municipio_id, "atualizado_em": _agora(), "possui_reguas": reguas,
                    "rotas_alternativas": [r.strip() for r in rotas.splitlines() if r.strip()],
                    "responsavel": responsavel.strip() or None, "telefone": telefone.strip() or None,
                    "link_documento": link.strip() or None,
                    "validade": validade.isoformat() if validade else None,
                    "observacoes": observacoes.strip() or None,
                },
                on_conflict="municipio_id",
            ),
            "Plano de contingência salvo.",
        ):
            st.rerun()
    return linhas


# ---------------------------------------------------------------- infraestrutura / saúde
def bloco_infraestrutura(cliente: Any, municipio_id: str, tipos: list[str] | None = None, editavel: bool = True) -> list[dict]:
    tipos = tipos or list(TIPOS_INFRA)
    dados = _ler(cliente, "infraestrutura", municipio_id, "nome", tipo=tipos)
    saude = tipos == ["ubs"]
    if saude and dados:
        tipos_unidade = sorted({d.get("tipo_unidade") or "Não informado" for d in dados})
        c1, c2 = st.columns([2, 3])
        filtro = c1.multiselect("Tipo de unidade", tipos_unidade, key=f"filtro-saude-{municipio_id}")
        busca = c2.text_input("Buscar por nome ou bairro", key=f"busca-saude-{municipio_id}")
        if filtro:
            dados = [d for d in dados if (d.get("tipo_unidade") or "Não informado") in filtro]
        if busca.strip():
            termo = busca.strip().lower()
            dados = [d for d in dados if termo in (d.get("nome") or "").lower() or termo in (d.get("bairro") or "").lower()]
        st.caption(
            f"{len(dados)} estabelecimento(s). Fonte principal: CNES/DATASUS (importação semanal); "
            "confirme por telefone antes de encaminhar pacientes."
        )
    linhas = _tabela([
        {"Nome": d["nome"],
         "Tipo": d.get("tipo_unidade") or TIPOS_INFRA.get(d["tipo"], d["tipo"]),
         "Endereço": d.get("endereco"), "Bairro": d.get("bairro"), "Telefone": d.get("telefone"),
         "Internação": _sim_nao(d.get("atendimento_hospitalar")),
         "Centro cirúrgico": _sim_nao(d.get("centro_cirurgico")),
         "Parto": _sim_nao(d.get("centro_obstetrico")), "Turno": d.get("turno"),
         "CNES": d.get("cnes_codigo"), "Fonte": d.get("fonte"),
         "Latitude": d.get("latitude"), "Longitude": d.get("longitude")}
        if saude else
        {"Tipo": TIPOS_INFRA.get(d["tipo"], d["tipo"]), "Nome": d["nome"], "Endereço": d.get("endereco"),
         "Telefone": d.get("telefone"), "Responsável": d.get("responsavel"),
         "Observações": d.get("observacoes"), "Fonte": d.get("fonte")}
        for d in dados
    ], mascarar=not editavel and not saude)
    if saude:
        _mapa_pontos([l for l in linhas if l.get("Latitude")], "Nome")
    if not editavel:
        return linhas
    with st.expander("Cadastrar manualmente" if saude else "Cadastrar infraestrutura crítica", expanded=not saude):
        with st.form(f"infra-{municipio_id}-{'-'.join(tipos)}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            tipo = c1.selectbox("Tipo", tipos, format_func=lambda t: TIPOS_INFRA[t])
            nome = c2.text_input("Nome *")
            c1, c2 = st.columns(2)
            endereco = c1.text_input("Endereço")
            telefone = c2.text_input("Telefone")
            c1, c2 = st.columns(2)
            responsavel = c1.text_input("Responsável")
            observacoes = c2.text_input("Observações")
            lat, lon = _coordenadas(f"inf-{municipio_id}-{tipos[0]}")
            if st.form_submit_button("Salvar"):
                if not nome.strip():
                    st.error("Informe o nome.")
                elif _executar(
                    cliente.table("infraestrutura").insert({
                        "municipio_id": municipio_id, "tipo": tipo, "nome": nome.strip(),
                        "endereco": endereco.strip() or None, "telefone": telefone.strip() or None,
                        "responsavel": responsavel.strip() or None, "observacoes": observacoes.strip() or None,
                        "fonte": "cadastro manual", **_local(lat, lon),
                    }),
                    f"{TIPOS_INFRA[tipo]} cadastrada.",
                ):
                    st.rerun()
    return linhas


def _mapa_pontos(linhas: list[dict], rotulo: str) -> None:
    if not linhas:
        return
    import pydeck as pdk

    pontos = [{"lat": l["Latitude"], "lon": l["Longitude"], "nome": l[rotulo],
               "detalhe": f"{l.get('Tipo') or ''} · {l.get('Telefone') or 'sem telefone'}",
               "cor": [215, 60, 40] if l.get("Internação") == "sim" else [47, 109, 181]} for l in linhas]
    st.pydeck_chart(
        pdk.Deck(
            layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]", get_fill_color="cor",
                              get_radius=300, radius_min_pixels=4, pickable=True)],
            initial_view_state=pdk.ViewState(
                latitude=sum(p["lat"] for p in pontos) / len(pontos),
                longitude=sum(p["lon"] for p in pontos) / len(pontos), zoom=8),
            map_provider="carto", map_style="light",
            tooltip={"html": "<b>{nome}</b><br/>{detalhe}"},
        ),
        height=320,
    )
    st.caption("Vermelho: faz internação. Azul: demais unidades. Mapa © OpenStreetMap / CARTO.")


# ---------------------------------------------------------------- situação oficial
def bloco_situacao(cliente: Any, municipio_id: str, editavel: bool = True) -> list[dict]:
    dados = (
        cliente.table("situacao_municipal").select("*")
        .eq("municipio_id", municipio_id).order("data", desc=True).limit(50).execute().data or []
    )
    linhas = _tabela([
        {"Data": _data(d["data"]), "Situação": SITUACOES.get(d["situacao"], d["situacao"]), "Fonte": d["fonte"],
         "Link": d.get("link"), "Observações": d.get("observacoes")}
        for d in dados
    ])
    if not editavel:
        return linhas
    with st.form(f"situacao-{municipio_id}", clear_on_submit=True):
        st.markdown("**Registrar situação oficial** (decreto/portaria — aparece na página pública)")
        c1, c2 = st.columns(2)
        situacao = c1.selectbox("Situação", list(SITUACOES), format_func=lambda s: SITUACOES[s])
        data_ato = c2.date_input("Data do ato", value=date.today(), format="DD/MM/YYYY")
        fonte = st.text_input("Fonte oficial *", placeholder="Ex.: Decreto municipal nº 123/2026, DOE-AM 14/10/2026")
        link = st.text_input("Link do ato (opcional)")
        observacoes = st.text_input("Observações")
        if st.form_submit_button("Registrar situação"):
            if not fonte.strip():
                st.error("Informe a fonte oficial (número do decreto, portaria ou boletim).")
            elif _executar(
                cliente.table("situacao_municipal").insert({
                    "municipio_id": municipio_id, "data": data_ato.isoformat(), "situacao": situacao,
                    "fonte": fonte.strip(), "link": link.strip() or None, "observacoes": observacoes.strip() or None,
                }),
                "Situação oficial registrada.",
            ):
                st.rerun()
    return linhas
