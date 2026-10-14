"""Voluntários (autocadastro com termo), relatos colaborativos e convite do Telegram."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import streamlit as st

TERMO_VERSAO = "v1-2026-10-14"
TERMO = """**Termo de responsabilidade do voluntário — CIDC (protótipo)**

1. Informarei apenas o que eu mesmo observei ou confirmei, com local e horário corretos,
   sem exageros e sem repassar boatos.
2. Entendo que meus relatos são informações colaborativas, **não oficiais**, que serão
   qualificadas por outros voluntários e pela Defesa Civil antes de qualquer decisão.
3. Usarei as informações do painel (inclusive contatos e dados de comunidades) apenas para
   apoiar a proteção da população, sem divulgá-las fora desse fim (LGPD — Lei 13.709/2018).
4. Não me exporei a risco para registrar uma ocorrência. Em emergência, ligo 199.
5. Sei que o acesso pode ser suspenso em caso de uso indevido ou informação falsa, e que
   meus registros ficam associados ao meu cadastro.
6. Autorizo o uso do meu nome, telefone e Telegram pela Defesa Civil para envio de alertas e
   contato operacional, podendo cancelar a qualquer momento.
"""
HABILIDADES = [
    "primeiros socorros", "condução de barco", "motorista", "saúde", "assistência social",
    "logística", "comunicação/rádio", "conhecimento local de rios", "drone/fotografia", "outra",
]
TIPOS_RELATO = {
    "chuva_forte": ("🌧️ Chuva forte", [47, 109, 181]),
    "rio_subindo": ("⬆️ Rio subindo rápido", [28, 63, 170]),
    "rio_baixando": ("⬇️ Rio baixando / seca", [217, 72, 15]),
    "cheia_alagamento": ("🌊 Cheia / alagamento", [21, 101, 192]),
    "incendio_fumaca": ("🔥 Incêndio / fumaça", [200, 30, 30]),
    "isolamento_comunidade": ("🚫 Comunidade isolada", [120, 60, 160]),
    "outro": ("❓ Outro", [120, 120, 120]),
}
STATUS_RELATO = {"novo": "aguardando confirmação", "confirmado": "confirmado", "descartado": "descartado"}


# ---------------------------------------------------------------- Telegram
@st.cache_data(ttl=86400, show_spinner=False)
def usuario_robo(token: str) -> str | None:
    try:
        corpo = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
        return (corpo.get("result") or {}).get("username")
    except Exception:
        return None


def link_robo(codigo: str | None = None) -> str | None:
    from app.auth import _segredo

    token = _segredo("TELEGRAM_BOT_TOKEN")
    nome = _segredo("TELEGRAM_BOT_USERNAME") or (usuario_robo(token) if token else None)
    if not nome:
        return None
    return f"https://t.me/{nome}" + (f"?start={codigo}" if codigo else "")


def convite_telegram() -> None:
    link = link_robo()
    if not link:
        return
    st.subheader("📲 Receba os alertas no Telegram")
    st.markdown(
        f"1. Abra **[{link.replace('https://', '')}]({link})** no celular.\n"
        "2. Toque em **Iniciar** (ou envie `/start`).\n"
        "3. Envie o **nome da sua cidade** (ex.: Lábrea).\n\n"
        "Você recebe só os alertas aprovados pela Defesa Civil. Para cancelar, envie `/sair`. "
        "As inscrições são processadas a cada 15 minutos."
    )


# ---------------------------------------------------------------- cadastro
def formulario_cadastro_voluntario(municipios: dict[str, dict[str, str]]) -> None:
    """Cria a conta no Supabase Auth guardando os dados do voluntário no cadastro da conta.

    O perfil "voluntario" é criado no primeiro login (app.auth.obter_perfil), pela função
    segura cidc_cadastrar_voluntario, que exige o aceite do termo.
    """
    from app.auth import cliente_publico

    st.markdown(TERMO)
    with st.form("cadastro-voluntario", clear_on_submit=False):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome completo *")
        telefone = c2.text_input("Telefone / WhatsApp *")
        c1, c2 = st.columns(2)
        email = c1.text_input("E-mail (será seu login) *", autocomplete="email")
        senha = c2.text_input("Senha (mínimo 8 caracteres) *", type="password")
        codigos = sorted(municipios, key=lambda c: municipios[c]["nome"])
        municipio_id = st.selectbox("Município onde atua *", codigos, format_func=lambda c: municipios[c]["nome"])
        habilidades = st.multiselect("Habilidades", HABILIDADES)
        c1, c2 = st.columns(2)
        embarcacao = c1.checkbox("Tenho embarcação disponível")
        disponibilidade = c2.selectbox("Disponibilidade", ["fins de semana", "noites", "integral", "emergências"])
        aceite = st.checkbox("Li e aceito o termo de responsabilidade acima *")
        enviar = st.form_submit_button("Quero ser voluntário", type="primary")
    if not enviar:
        return
    if not aceite:
        st.error("É preciso aceitar o termo de responsabilidade.")
        return
    if len(nome.strip()) < 3 or not telefone.strip() or "@" not in email or len(senha) < 8:
        st.error("Preencha nome, telefone, e-mail válido e senha com pelo menos 8 caracteres.")
        return
    try:
        resposta = cliente_publico().auth.sign_up({
            "email": email.strip(),
            "password": senha,
            "options": {"data": {"cidc_voluntario": {
                "nome": nome.strip(), "telefone": telefone.strip(), "municipio_id": municipio_id,
                "habilidades": habilidades, "possui_embarcacao": embarcacao,
                "disponibilidade": disponibilidade, "termo_versao": TERMO_VERSAO, "aceite": True,
            }}},
        })
    except Exception as erro:
        st.error(f"Não foi possível criar a conta: {erro}")
        return
    if resposta.session:
        st.success("Cadastro criado! Entre com seu e-mail e senha na aba **Entrar**.")
    else:
        st.success(
            "Cadastro criado! Enviamos um e-mail de confirmação para "
            f"{email.strip()}. Confirme e depois entre com seu e-mail e senha na aba **Entrar**."
        )


def concluir_cadastro_pendente(cliente: Any, metadados: dict[str, Any]) -> bool:
    """Cria o perfil voluntário no primeiro login, a partir dos dados do autocadastro."""
    dados = (metadados or {}).get("cidc_voluntario")
    if not dados or not dados.get("aceite"):
        return False
    cliente.rpc("cidc_cadastrar_voluntario", {
        "p_nome": dados["nome"], "p_telefone": dados.get("telefone"),
        "p_municipio_id": dados["municipio_id"], "p_habilidades": dados.get("habilidades") or [],
        "p_possui_embarcacao": bool(dados.get("possui_embarcacao")),
        "p_disponibilidade": dados.get("disponibilidade"),
        "p_termo_versao": dados.get("termo_versao") or TERMO_VERSAO, "p_aceite": True,
    }).execute()
    return True


def renderizar_meu_cadastro() -> None:
    from app.comum import cliente_supabase, exigir_perfil

    st.title("Meu cadastro de voluntário")
    try:
        cliente, perfil = exigir_perfil({"voluntario"})
        dados = cliente.table("voluntarios").select("*").eq("usuario_id", perfil["id"]).limit(1).execute().data
    except Exception as erro:
        st.error(f"Não foi possível carregar seu cadastro: {erro}")
        return
    if not dados:
        st.warning("Cadastro de voluntário não encontrado. Saia e entre novamente.")
        return
    v = dados[0]
    st.write(f"**{v['nome']}** · telefone {v.get('telefone') or 'n/d'} · termo {v['termo_versao']} "
             f"aceito em {str(v['termo_aceito_em'])[:10]}")
    st.write("Habilidades: " + (", ".join(v.get("habilidades") or []) or "não informadas"))
    if v.get("telegram_chat_id"):
        st.success("✅ Seu Telegram está vinculado: você recebe os alertas aprovados do seu município.")
    else:
        link = link_robo(v["telegram_codigo"])
        if link:
            st.info("Vincule seu Telegram para receber os alertas aprovados:")
            st.link_button("📲 Abrir o robô no Telegram e vincular", link, type="primary")
            st.caption("Toque em Iniciar no Telegram. A vinculação é processada em até 15 minutos.")
    st.caption("Você pode ler todos os painéis e registrar relatos; a aprovação de alertas é da Defesa Civil.")


def bloco_voluntarios(cliente: Any, municipio_id: str) -> list[dict]:
    """Lista de voluntários do município (coordenação/administração)."""
    dados = (
        cliente.table("voluntarios").select("*").eq("municipio_id", municipio_id)
        .order("nome").limit(500).execute().data or []
    )
    linhas = [
        {"Voluntário": d["nome"], "Telefone": d.get("telefone"),
         "Habilidades": ", ".join(d.get("habilidades") or []),
         "Embarcação": "sim" if d.get("possui_embarcacao") else "não",
         "Disponibilidade": d.get("disponibilidade"),
         "Telegram vinculado": "sim" if d.get("telegram_chat_id") else "não",
         "Termo aceito em": str(d.get("termo_aceito_em") or "")[:10], "Ativo": "sim" if d.get("ativo") else "não"}
        for d in dados
    ]
    if not linhas:
        st.info("Nenhum voluntário cadastrado neste município. O autocadastro fica na tela de login "
                "(aba \"Quero ser voluntário\").")
    st.dataframe(linhas, hide_index=True, width="stretch")
    return linhas


# ---------------------------------------------------------------- relatos
def _carregar_relatos(cliente: Any, horas: int = 72, somente_confirmados: bool = False) -> list[dict]:
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    consulta = cliente.table("relatos").select("*").gte("criado_em", desde).order("criado_em", desc=True)
    if somente_confirmados:
        consulta = consulta.eq("status", "confirmado")
    return consulta.limit(1000).execute().data or []


def mapa_relatos(relatos: list[dict], nomes: dict[str, str], altura: int = 420) -> None:
    import pydeck as pdk

    pontos = [
        {"lat": r["latitude"], "lon": r["longitude"],
         "cor": TIPOS_RELATO.get(r["tipo"], TIPOS_RELATO["outro"])[1] + ([230] if r["status"] == "confirmado" else [120]),
         "raio": {"fraca": 1500, "moderada": 2500, "forte": 4000}.get(r["intensidade"], 2500),
         "titulo": TIPOS_RELATO.get(r["tipo"], ("",))[0],
         "detalhe": f"{nomes.get(str(r['municipio_id']).strip(), '')} · {r['intensidade']} · "
                    f"{STATUS_RELATO[r['status']]} ({r['confirmacoes']}✔ {r['negacoes']}✖) · "
                    f"{str(r['criado_em'])[:16].replace('T', ' ')} UTC<br/>{(r.get('descricao') or '')[:160]}"}
        for r in relatos
    ]
    if not pontos:
        st.info("Nenhum relato nas últimas 72 horas.")
        return
    st.pydeck_chart(
        pdk.Deck(
            layers=[pdk.Layer("ScatterplotLayer", data=pontos, get_position="[lon, lat]", get_fill_color="cor",
                              get_radius="raio", radius_min_pixels=6, stroked=True,
                              get_line_color=[255, 255, 255], line_width_min_pixels=1, pickable=True)],
            initial_view_state=pdk.ViewState(latitude=-4.6, longitude=-63.5, zoom=4.7),
            map_provider="carto", map_style="light",
            tooltip={"html": "<b>{titulo}</b><br/>{detalhe}"},
        ),
        height=altura,
    )
    st.caption("Relatos colaborativos de voluntários — NÃO são informação oficial. Cores mais fortes: "
               "confirmados por 3 ou mais pessoas. Mapa © OpenStreetMap / CARTO.")


def renderizar_relatos() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.relatorio_menu import painel_relatorio
    from app.visual import grafico_barras

    st.title("Relatos de campo (colaborativo)")
    st.caption("Como no Waze: quem está no local informa; outras pessoas confirmam ou negam.")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil({
            "voluntario", "gestor_nacional", "gestor_estadual", "coordenador_municipal",
            "operador_monitoramento", "agente_campo", "saude_assistencia", "logistica_abastecimento",
            "administrador",
        })
        municipios = carregar_municipios(cliente)
        nomes = {c: m["nome"] for c, m in municipios.items()}
        coordenadas = {
            str(m["id_ibge"]).strip(): (m.get("latitude"), m.get("longitude"))
            for m in cliente.table("municipios").select("id_ibge,latitude,longitude").execute().data or []
        }
        relatos = _carregar_relatos(cliente)
    except Exception as erro:
        st.error(f"Não foi possível carregar os relatos: {erro}")
        return

    with st.expander("➕ Registrar uma ocorrência", expanded=not relatos):
        codigos = sorted(municipios, key=lambda c: nomes[c])
        padrao = perfil.get("municipio_id")
        municipio_id = st.selectbox("Município", codigos, format_func=lambda c: nomes[c],
                                    index=codigos.index(padrao) if padrao in codigos else 0, key="relato-municipio")
        lat0, lon0 = coordenadas.get(municipio_id, (None, None))
        with st.form("novo-relato", clear_on_submit=True):
            c1, c2 = st.columns(2)
            tipo = c1.selectbox("O que você está vendo?", list(TIPOS_RELATO), format_func=lambda t: TIPOS_RELATO[t][0])
            intensidade = c2.select_slider("Intensidade", ["fraca", "moderada", "forte"], value="moderada")
            descricao = st.text_area("Descreva (local, o que mudou, desde quando)", max_chars=500)
            st.caption("Local: comece pela sede do município e ajuste. No celular, toque e segure no "
                       "Google Maps para copiar suas coordenadas.")
            c1, c2 = st.columns(2)
            lat = c1.number_input("Latitude", value=float(lat0 or -3.1), format="%.5f", min_value=-90.0, max_value=90.0)
            lon = c2.number_input("Longitude", value=float(lon0 or -60.0), format="%.5f", min_value=-180.0, max_value=180.0)
            enviar = st.form_submit_button("Enviar relato", type="primary")
        if enviar:
            try:
                cliente.table("relatos").insert({
                    "municipio_id": municipio_id, "tipo": tipo, "intensidade": intensidade,
                    "descricao": descricao.strip() or None, "latitude": lat, "longitude": lon,
                    "usuario_id": perfil["id"],
                }).execute()
                st.success("Relato registrado. Ele aparece para outras pessoas confirmarem.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível registrar: {erro}")

    mapa_relatos(relatos, nomes)
    if relatos:
        contagem: dict[str, int] = {}
        for r in relatos:
            rotulo = TIPOS_RELATO.get(r["tipo"], ("Outro",))[0]
            contagem[rotulo] = contagem.get(rotulo, 0) + 1
        grafico_barras(dict(sorted(contagem.items(), key=lambda i: -i[1])), "Relatos nas últimas 72 h por tipo")

    meus_votos = {
        v["relato_id"]
        for v in cliente.table("relato_votos").select("relato_id").eq("usuario_id", perfil["id"]).execute().data or []
    }
    pode_moderar = perfil["perfil"] in {"coordenador_municipal", "administrador"}
    st.subheader("Relatos recentes")
    for r in relatos[:40]:
        cols = st.columns([6, 1, 1])
        cols[0].markdown(
            f"**{TIPOS_RELATO.get(r['tipo'], ('Outro',))[0]}** · {nomes.get(str(r['municipio_id']).strip(), '')} · "
            f"{r['intensidade']} · _{STATUS_RELATO[r['status']]}_ ({r['confirmacoes']}✔ {r['negacoes']}✖) · "
            f"{str(r['criado_em'])[:16].replace('T', ' ')} UTC  \n{r.get('descricao') or ''}"
        )
        proprio = r["usuario_id"] == perfil["id"]
        if r["status"] == "novo" and not proprio and r["id"] not in meus_votos:
            for coluna, confirma, rotulo in ((cols[1], True, "✔ Confirmo"), (cols[2], False, "✖ Não vi")):
                if coluna.button(rotulo, key=f"voto-{r['id']}-{confirma}"):
                    try:
                        cliente.table("relato_votos").insert(
                            {"relato_id": r["id"], "confirma": confirma, "usuario_id": perfil["id"]}
                        ).execute()
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Voto não registrado: {erro}")
        elif pode_moderar and r["status"] == "novo":
            for coluna, status, rotulo in ((cols[1], "confirmado", "Validar"), (cols[2], "descartado", "Descartar")):
                if coluna.button(rotulo, key=f"mod-{r['id']}-{status}"):
                    cliente.table("relatos").update({"status": status}).eq("id", r["id"]).execute()
                    st.rerun()

    painel_relatorio(
        "Relatório de relatos colaborativos (72 h)",
        [("Relatos", [
            {"Tipo": TIPOS_RELATO.get(r["tipo"], ("Outro",))[0], "Município": nomes.get(str(r["municipio_id"]).strip()),
             "Intensidade": r["intensidade"], "Status": STATUS_RELATO[r["status"]],
             "Confirmações": r["confirmacoes"], "Negações": r["negacoes"],
             "Data (UTC)": str(r["criado_em"])[:16].replace("T", " "),
             "Latitude": r["latitude"], "Longitude": r["longitude"], "Descrição": r.get("descricao")}
            for r in relatos
        ])],
        resumo={"Relatos (72 h)": len(relatos),
                "Confirmados": sum(1 for r in relatos if r["status"] == "confirmado"),
                "Natureza": "informação colaborativa, não oficial"},
    )


def relatos_publicos(cliente: Any, nomes: dict[str, str]) -> None:
    """Relatos confirmados para a página pública (marcados como não oficiais)."""
    try:
        relatos = _carregar_relatos(cliente, somente_confirmados=True)
    except Exception:
        return
    st.subheader("🗺️ Relatos confirmados de voluntários (72 h)")
    st.caption("Informação colaborativa confirmada por voluntários — não é comunicado oficial.")
    mapa_relatos(relatos, nomes, altura=360)
