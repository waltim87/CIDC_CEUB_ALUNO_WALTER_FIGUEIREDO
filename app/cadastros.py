"""Formulários de cadastro dos painéis (comunidades, recursos, abrigos, plano,
infraestrutura e situação oficial).

Cada bloco mostra os dados atuais e um formulário para incluir/atualizar. As
permissões são do banco (RLS por perfil e município): se o perfil não puder
gravar, o Supabase recusa e a mensagem aparece na tela. Toda gravação passa
pela auditoria do banco.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import streamlit as st

TIPOS_RECURSO = {
    "agua": "Água (litros)",
    "alimento": "Alimento (cestas)",
    "medicamento": "Medicamento (kits)",
    "oxigenio": "Oxigênio (cilindros)",
    "combustivel": "Combustível (litros)",
    "purificador": "Purificador de água (unidades)",
}
TIPOS_INFRA = {
    "ubs": "Unidade de saúde (UBS/hospital)",
    "escola": "Escola",
    "porto": "Porto / atracadouro",
    "captacao": "Captação de água",
    "energia": "Energia (usina/subestação)",
}
ACESSOS = ["fluvial", "terrestre", "aéreo", "fluvial e terrestre", "outro"]
SITUACOES = {"normal": "Normal", "atencao": "Atenção", "alerta": "Alerta", "emergencia": "Emergência"}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ponto(lat: float | None, lon: float | None) -> str | None:
    """EWKT aceito pela coluna geometry(Point, 4326); vazio quando sem coordenada."""
    if not lat or not lon:
        return None
    return f"SRID=4326;POINT({lon} {lat})"


def _executar(acao: Any, sucesso: str) -> bool:
    try:
        resposta = acao.execute()
    except Exception as erro:
        texto = str(erro)
        if "row-level security" in texto or "42501" in texto:
            st.error("Seu perfil não tem permissão para gravar este dado neste município.")
        else:
            st.error(f"Não foi possível salvar: {texto}")
        return False
    if getattr(resposta, "data", None) == []:
        st.error("O banco não confirmou a gravação (verifique a permissão do seu perfil).")
        return False
    st.success(sucesso)
    return True


def _ler(cliente: Any, tabela: str, colunas: str, municipio_id: str, **filtros: Any) -> list[dict]:
    consulta = cliente.table(tabela).select(colunas).eq("municipio_id", municipio_id)
    for coluna, valores in filtros.items():
        consulta = consulta.in_(coluna, valores)
    return consulta.limit(500).execute().data or []


def _coordenadas(prefixo: str) -> tuple[float | None, float | None]:
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude (opcional)", value=None, format="%.5f", key=f"{prefixo}-lat",
                          min_value=-90.0, max_value=90.0, placeholder="-3.10000")
    lon = c2.number_input("Longitude (opcional)", value=None, format="%.5f", key=f"{prefixo}-lon",
                          min_value=-180.0, max_value=180.0, placeholder="-60.00000")
    return lat, lon


# ---------------------------------------------------------------- comunidades
def bloco_comunidades(cliente: Any, municipio_id: str) -> None:
    dados = _ler(cliente, "comunidades", "id,nome,populacao_estimada,acesso_principal", municipio_id)
    st.dataframe(
        [{"Comunidade": d["nome"], "População estimada": d["populacao_estimada"],
          "Acesso principal": d["acesso_principal"]} for d in dados],
        hide_index=True, width="stretch",
    )
    with st.form(f"nova-comunidade-{municipio_id}", clear_on_submit=True):
        st.markdown("**Cadastrar comunidade**")
        nome = st.text_input("Nome da comunidade")
        populacao = st.number_input("População estimada", min_value=0, step=10)
        acesso = st.selectbox("Acesso principal", ACESSOS)
        lat, lon = _coordenadas(f"com-{municipio_id}")
        if st.form_submit_button("Salvar comunidade"):
            if not nome.strip():
                st.error("Informe o nome da comunidade.")
            elif _executar(
                cliente.table("comunidades").insert({
                    "municipio_id": municipio_id, "nome": nome.strip(),
                    "populacao_estimada": int(populacao) or None,
                    "acesso_principal": acesso, "geom": _ponto(lat, lon),
                }),
                f"Comunidade {nome.strip()} cadastrada.",
            ):
                st.rerun()


# ---------------------------------------------------------------- recursos
def bloco_recursos(cliente: Any, municipio_id: str, tipos: list[str] | None = None) -> None:
    tipos = tipos or list(TIPOS_RECURSO)
    dados = _ler(cliente, "recursos", "id,tipo,quantidade,atualizado_em", municipio_id, tipo=tipos)
    st.dataframe(
        [{"Recurso": TIPOS_RECURSO.get(d["tipo"], d["tipo"]), "Quantidade": d["quantidade"],
          "Atualizado em (UTC)": str(d["atualizado_em"])[:16].replace("T", " ")} for d in dados],
        hide_index=True, width="stretch",
    )
    with st.form(f"recurso-{municipio_id}-{'-'.join(tipos)}", clear_on_submit=True):
        st.markdown("**Atualizar estoque** (substitui a quantidade atual do item)")
        tipo = st.selectbox("Item", tipos, format_func=lambda t: TIPOS_RECURSO[t])
        quantidade = st.number_input("Quantidade disponível agora", min_value=0.0, step=1.0)
        if st.form_submit_button("Salvar estoque"):
            existente = next((d for d in dados if d["tipo"] == tipo), None)
            valores = {"quantidade": quantidade, "atualizado_em": _agora()}
            acao = (
                cliente.table("recursos").update(valores).eq("id", existente["id"])
                if existente
                else cliente.table("recursos").insert({"municipio_id": municipio_id, "tipo": tipo, **valores})
            )
            if _executar(acao, f"Estoque de {TIPOS_RECURSO[tipo].split(' (')[0].lower()} atualizado."):
                st.rerun()


# ---------------------------------------------------------------- abrigos
def bloco_abrigos(cliente: Any, municipio_id: str) -> None:
    dados = _ler(cliente, "abrigos", "id,nome,capacidade,ocupacao", municipio_id)
    st.dataframe(
        [{"Abrigo": d["nome"], "Capacidade": d["capacidade"], "Ocupação": d["ocupacao"],
          "Vagas": d["capacidade"] - d["ocupacao"],
          "Ocupação (%)": round(d["ocupacao"] / d["capacidade"] * 100) if d["capacidade"] else None}
         for d in dados],
        hide_index=True, width="stretch",
    )
    c1, c2 = st.columns(2)
    with c1, st.form(f"novo-abrigo-{municipio_id}", clear_on_submit=True):
        st.markdown("**Cadastrar abrigo**")
        nome = st.text_input("Nome do abrigo")
        capacidade = st.number_input("Capacidade (pessoas)", min_value=0, step=10)
        lat, lon = _coordenadas(f"abr-{municipio_id}")
        if st.form_submit_button("Salvar abrigo"):
            if not nome.strip():
                st.error("Informe o nome do abrigo.")
            elif _executar(
                cliente.table("abrigos").insert({
                    "municipio_id": municipio_id, "nome": nome.strip(),
                    "capacidade": int(capacidade), "ocupacao": 0, "geom": _ponto(lat, lon),
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
                cliente.table("abrigos").update({"ocupacao": int(ocupacao)}).eq("id", abrigo_id),
                "Ocupação atualizada.",
            ):
                st.rerun()


# ---------------------------------------------------------------- plano
def bloco_plano(cliente: Any, municipio_id: str) -> None:
    dados = _ler(cliente, "planos_contingencia", "id,atualizado_em,possui_reguas,rotas_alternativas", municipio_id)
    plano = dados[0] if dados else {}
    if plano:
        st.write(
            f"Atualizado em **{str(plano.get('atualizado_em') or 'n/d')[:10]}** · "
            f"Réguas instaladas: **{'sim' if plano.get('possui_reguas') else 'não'}**"
        )
        for rota in plano.get("rotas_alternativas") or []:
            st.markdown(f"- {rota}")
    else:
        st.info("Plano de contingência ainda não registrado.")
    with st.form(f"plano-{municipio_id}"):
        st.markdown("**Registrar / atualizar plano de contingência**")
        reguas = st.checkbox("Réguas linimétricas instaladas", value=bool(plano.get("possui_reguas")))
        rotas = st.text_area(
            "Rotas alternativas (uma por linha)",
            value="\n".join(plano.get("rotas_alternativas") or []),
            placeholder="Ex.: Rio Purus até Lábrea por balsa (seca: canal pelo paraná X)",
        )
        if st.form_submit_button("Salvar plano") and _executar(
            cliente.table("planos_contingencia").upsert(
                {
                    "municipio_id": municipio_id,
                    "atualizado_em": _agora(),
                    "possui_reguas": reguas,
                    "rotas_alternativas": [r.strip() for r in rotas.splitlines() if r.strip()],
                },
                on_conflict="municipio_id",
            ),
            "Plano de contingência salvo.",
        ):
            st.rerun()


# ---------------------------------------------------------------- infraestrutura
def bloco_infraestrutura(cliente: Any, municipio_id: str, tipos: list[str] | None = None) -> None:
    tipos = tipos or list(TIPOS_INFRA)
    dados = _ler(cliente, "infraestrutura", "id,tipo,nome", municipio_id, tipo=tipos)
    st.dataframe(
        [{"Tipo": TIPOS_INFRA.get(d["tipo"], d["tipo"]), "Nome": d["nome"]} for d in dados],
        hide_index=True, width="stretch",
    )
    with st.form(f"infra-{municipio_id}-{'-'.join(tipos)}", clear_on_submit=True):
        st.markdown("**Cadastrar infraestrutura crítica**")
        tipo = st.selectbox("Tipo", tipos, format_func=lambda t: TIPOS_INFRA[t])
        nome = st.text_input("Nome")
        lat, lon = _coordenadas(f"inf-{municipio_id}-{tipos[0]}")
        if st.form_submit_button("Salvar"):
            if not nome.strip():
                st.error("Informe o nome.")
            elif _executar(
                cliente.table("infraestrutura").insert({
                    "municipio_id": municipio_id, "tipo": tipo, "nome": nome.strip(),
                    "geom": _ponto(lat, lon),
                }),
                f"{TIPOS_INFRA[tipo]} cadastrada.",
            ):
                st.rerun()


# ---------------------------------------------------------------- situação oficial
def bloco_situacao(cliente: Any, municipio_id: str) -> None:
    dados = (
        cliente.table("situacao_municipal").select("data,situacao,fonte")
        .eq("municipio_id", municipio_id).order("data", desc=True).limit(20).execute().data or []
    )
    st.dataframe(
        [{"Data": d["data"], "Situação": SITUACOES.get(d["situacao"], d["situacao"]), "Fonte": d["fonte"]}
         for d in dados],
        hide_index=True, width="stretch",
    )
    with st.form(f"situacao-{municipio_id}", clear_on_submit=True):
        st.markdown("**Registrar situação oficial** (decreto/portaria — aparece na página pública)")
        situacao = st.selectbox("Situação", list(SITUACOES), format_func=lambda s: SITUACOES[s])
        data_ato = st.date_input("Data do ato", value=date.today(), format="DD/MM/YYYY")
        fonte = st.text_input("Fonte oficial", placeholder="Ex.: Decreto municipal nº 123/2026, DOE-AM 14/10/2026")
        if st.form_submit_button("Registrar situação"):
            if not fonte.strip():
                st.error("Informe a fonte oficial (número do decreto, portaria ou boletim).")
            elif _executar(
                cliente.table("situacao_municipal").insert({
                    "municipio_id": municipio_id, "data": data_ato.isoformat(),
                    "situacao": situacao, "fonte": fonte.strip(),
                }),
                "Situação oficial registrada.",
            ):
                st.rerun()
