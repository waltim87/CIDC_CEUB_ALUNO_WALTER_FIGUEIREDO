"""Famílias abrigadas: cadastro com membros (nome completo, CPF, parentesco) e fotos do imóvel.

Dados pessoais sensíveis (LGPD). O banco só libera a quem atende a família:
coordenador do abrigo, coordenação municipal, assistência social do município e
administração. Fotos ficam no bucket privado "fotos-familias" do Supabase Storage.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import streamlit as st

from core import cpf as cpf_util

PARENTESCOS = [
    "cônjuge/companheiro(a)", "filho(a)", "enteado(a)", "pai/mãe", "avô/avó", "neto(a)",
    "irmão/irmã", "sogro(a)", "genro/nora", "tio(a)", "sobrinho(a)", "primo(a)", "outro parente", "agregado",
]
SITUACOES_IMOVEL = {
    "destruido": "Destruído (demolido)",
    "parcialmente_destruido": "Parcialmente destruído",
    "danificado": "Danificado",
    "interditado": "Interditado pela Defesa Civil",
    "alagado": "Alagado",
    "sem_dano": "Sem dano (deslocamento preventivo)",
}
NECESSIDADES = ["água", "alimento", "roupas", "medicamento", "atendimento médico", "kit higiene",
                "colchão/rede", "documentos", "apoio psicológico", "transporte"]
BUCKET = "fotos-familias"
TERMO_LGPD = (
    "Declaro que a família foi informada e autorizou o registro dos dados pessoais (nomes, CPF, "
    "parentesco, fotos do imóvel) exclusivamente para assistência humanitária e políticas públicas "
    "de resposta e recuperação, conforme a LGPD (Lei 13.709/2018)."
)


def _abrigos_acessiveis(cliente: Any, perfil: dict[str, Any], municipio_id: str | None) -> list[dict]:
    """Abrigos do município (coordenação/assistência/admin) + abrigos designados ao usuário."""
    abrigos: dict[str, dict] = {}
    if municipio_id and perfil["perfil"] in {"administrador", "coordenador_municipal", "saude_assistencia"}:
        for a in cliente.table("abrigos").select("*").eq("municipio_id", municipio_id).order("nome").execute().data or []:
            abrigos[a["id"]] = a
    designados = [
        r["abrigo_id"]
        for r in cliente.table("abrigo_responsaveis").select("abrigo_id").eq("usuario_id", perfil["id"]).execute().data or []
    ]
    if designados:
        for a in cliente.table("abrigos").select("*").in_("id", designados).execute().data or []:
            abrigos[a["id"]] = a
    return sorted(abrigos.values(), key=lambda a: a["nome"])


def usuario_coordena_abrigo(cliente: Any, usuario_id: str) -> bool:
    import time

    guardado = st.session_state.get("_coordena_abrigo")
    if guardado and guardado[0] == usuario_id and time.time() - guardado[2] < 300:
        return guardado[1]
    try:
        resposta = bool(cliente.table("abrigo_responsaveis").select("abrigo_id").eq("usuario_id", usuario_id).limit(1).execute().data)
    except Exception:
        return False
    st.session_state["_coordena_abrigo"] = (usuario_id, resposta, time.time())
    return resposta


def validar_membros(membros: list[dict[str, Any]]) -> list[str]:
    """Erros de preenchimento dos membros (nome completo, CPF válido ou motivo, parentesco)."""
    erros = []
    for posicao, m in enumerate(membros, start=1):
        nome = str(m.get("Nome completo") or "").strip()
        if not nome and not m.get("CPF") and not m.get("Parentesco"):
            continue
        if len(nome.split()) < 2:
            erros.append(f"Membro {posicao}: informe o nome completo (nome e sobrenome).")
        numero = cpf_util.limpar(str(m.get("CPF") or ""))
        if numero and not cpf_util.valido(numero):
            erros.append(f"Membro {posicao} ({nome or 'sem nome'}): CPF inválido.")
        if not numero and not str(m.get("Sem CPF — motivo") or "").strip():
            erros.append(f"Membro {posicao} ({nome or 'sem nome'}): informe o CPF ou o motivo de não ter (ex.: recém-nascido).")
        if m.get("Parentesco") not in PARENTESCOS:
            erros.append(f"Membro {posicao} ({nome or 'sem nome'}): escolha o grau de parentesco.")
        if m.get("Desaparecido"):
            if not _data_iso(m.get("Visto por último em (dd/mm/aaaa)")):
                erros.append(f"Membro {posicao} ({nome or 'sem nome'}): desaparecido — informe o último dia visto (dd/mm/aaaa).")
            if not str(m.get("Último local visto") or "").strip():
                erros.append(f"Membro {posicao} ({nome or 'sem nome'}): desaparecido — informe o último local visto.")
    return erros


def _desaparecido(m: dict[str, Any]) -> bool:
    return bool(m.get("Desaparecido"))


def _formulario_familia(cliente: Any, abrigo: dict[str, Any]) -> None:
    comunidades = cliente.table("comunidades").select("id,nome").eq("municipio_id", abrigo["municipio_id"]).order("nome").execute().data or []
    st.markdown("**Cadastrar família no abrigo**")
    with st.form(f"familia-{abrigo['id']}", clear_on_submit=False):
        c1, c2 = st.columns(2)
        responsavel = c1.text_input("Nome completo do responsável *")
        cpf_resp = c2.text_input("CPF do responsável *", placeholder="000.000.000-00")
        c1, c2 = st.columns(2)
        telefone = c1.text_input("Telefone de contato")
        situacao = c2.selectbox("Situação do imóvel *", list(SITUACOES_IMOVEL), format_func=lambda s: SITUACOES_IMOVEL[s])
        endereco = st.text_input("Endereço de origem (onde morava)")
        c1, c2 = st.columns(2)
        comunidade_id = c1.selectbox(
            "Comunidade de origem", [None] + [c["id"] for c in comunidades],
            format_func=lambda i: "não informada" if i is None else next(c["nome"] for c in comunidades if c["id"] == i),
        )
        entrada = c2.date_input("Data de entrada no abrigo", value=date.today(), format="DD/MM/YYYY")
        necessidades = st.multiselect("Necessidades", NECESSIDADES)
        st.markdown("**Membros da família** (além do responsável) — nome completo, CPF e parentesco. "
                    "Pessoa desaparecida: marque e informe o último dia e local em que foi vista.")
        membros = st.data_editor(
            [{"Nome completo": "", "CPF": "", "Sem CPF — motivo": "", "Parentesco": None,
              "Nascimento (dd/mm/aaaa)": "", "Necessidades especiais": "", "Desaparecido": False,
              "Visto por último em (dd/mm/aaaa)": "", "Último local visto": ""}],
            num_rows="dynamic",
            column_config={
                "Parentesco": st.column_config.SelectboxColumn("Parentesco", options=PARENTESCOS, required=False),
                "Desaparecido": st.column_config.CheckboxColumn("Desaparecido", default=False),
            },
            key=f"membros-{abrigo['id']}", width="stretch",
        )
        fotos = st.file_uploader("Fotos do imóvel (até 5 MB cada; JPG/PNG/WEBP)", type=["jpg", "jpeg", "png", "webp"],
                                 accept_multiple_files=True)
        observacoes = st.text_area("Observações")
        consentimento = st.checkbox(TERMO_LGPD)
        salvar = st.form_submit_button("Salvar família", type="primary")
    if not salvar:
        return
    erros = []
    if len(responsavel.strip().split()) < 2:
        erros.append("Informe o nome completo do responsável.")
    if not cpf_util.valido(cpf_resp):
        erros.append("CPF do responsável inválido.")
    membros = [m for m in (membros or []) if any(str(v or "").strip() for v in m.values())]
    erros += validar_membros(membros)
    if not consentimento:
        erros.append("É preciso registrar o consentimento da família (LGPD).")
    pessoas = 1 + sum(1 for m in membros if not _desaparecido(m))
    desaparecidos = sum(1 for m in membros if _desaparecido(m))
    vagas = int(abrigo["capacidade"]) - int(abrigo["ocupacao"])
    if pessoas > vagas:
        erros.append(f"O abrigo tem {vagas} vaga(s) e a família tem {pessoas} pessoa(s).")
    if erros:
        for erro in erros:
            st.error(erro)
        return
    try:
        familia = cliente.table("familias_abrigadas").insert({
            "abrigo_id": abrigo["id"], "municipio_id": abrigo["municipio_id"],
            "responsavel_nome": responsavel.strip(), "responsavel_cpf": cpf_util.limpar(cpf_resp),
            "telefone": telefone.strip() or None, "endereco_origem": endereco.strip() or None,
            "comunidade_id": comunidade_id, "situacao_imovel": situacao, "data_entrada": entrada.isoformat(),
            "necessidades": necessidades, "observacoes": observacoes.strip() or None, "consentimento_lgpd": True,
        }).execute().data[0]
        if membros:
            cliente.table("membros_familia").insert([
                {"familia_id": familia["id"], "nome_completo": str(m["Nome completo"]).strip(),
                 "cpf": cpf_util.limpar(str(m.get("CPF") or "")) or None,
                 "sem_cpf_motivo": str(m.get("Sem CPF — motivo") or "").strip() or None,
                 "parentesco": m["Parentesco"],
                 "data_nascimento": _data_iso(m.get("Nascimento (dd/mm/aaaa)")),
                 "necessidades_especiais": str(m.get("Necessidades especiais") or "").strip() or None,
                 "desaparecido": _desaparecido(m),
                 "visto_por_ultimo_em": _data_iso(m.get("Visto por último em (dd/mm/aaaa)")) if _desaparecido(m) else None,
                 "ultimo_local_visto": str(m.get("Último local visto") or "").strip() or None if _desaparecido(m) else None}
                for m in membros
            ]).execute()
        enviadas = _enviar_fotos(cliente, familia, fotos or [])
        cliente.table("abrigos").update({"ocupacao": int(abrigo["ocupacao"]) + pessoas}).eq("id", abrigo["id"]).execute()
    except Exception as erro:
        texto = str(erro)
        if "familias_cpf_ativo" in texto or "duplicate" in texto:
            st.error("Já existe família ativa com este CPF de responsável (registre a saída antes de recadastrar).")
        elif "row-level security" in texto or "42501" in texto:
            st.error("Seu perfil não tem permissão para cadastrar famílias neste abrigo.")
        else:
            st.error(f"Não foi possível salvar a família: {texto}")
        return
    st.success(f"Família de {responsavel.strip()} cadastrada ({pessoas} pessoa(s) no abrigo, {enviadas} foto(s)"
               + (f", {desaparecidos} desaparecida(s) registrada(s)" if desaparecidos else "") + "). Ocupação atualizada.")
    st.rerun()


def _data_iso(texto: Any) -> str | None:
    partes = str(texto or "").strip().split("/")
    if len(partes) == 3 and all(p.isdigit() for p in partes):
        try:
            return date(int(partes[2]), int(partes[1]), int(partes[0])).isoformat()
        except ValueError:
            return None
    return None


def _enviar_fotos(cliente: Any, familia: dict[str, Any], fotos: list[Any]) -> int:
    enviadas = 0
    for foto in fotos:
        extensao = (foto.name.rsplit(".", 1)[-1] or "jpg").lower()
        caminho = f"{str(familia['municipio_id']).strip()}/{familia['id']}/{uuid.uuid4().hex}.{extensao}"
        cliente.storage.from_(BUCKET).upload(caminho, foto.getvalue(), {"content-type": foto.type or "image/jpeg"})
        cliente.table("fotos_familia").insert({"familia_id": familia["id"], "caminho": caminho, "descricao": foto.name}).execute()
        enviadas += 1
    return enviadas


def _detalhe_familia(cliente: Any, familia: dict[str, Any], abrigo: dict[str, Any]) -> None:
    membros = cliente.table("membros_familia").select("*").eq("familia_id", familia["id"]).execute().data or []
    st.markdown(
        f"**{familia['responsavel_nome']}** · CPF {cpf_util.formatar(familia['responsavel_cpf'])} · "
        f"tel. {familia.get('telefone') or 'n/d'}  \nImóvel: {SITUACOES_IMOVEL.get(familia['situacao_imovel'])} · "
        f"origem: {familia.get('endereco_origem') or 'n/d'} · entrada {familia['data_entrada']}"
        + (f" · saída {familia['data_saida']}" if familia.get("data_saida") else "")
    )
    st.dataframe(
        [{"Nome completo": m["nome_completo"], "Parentesco": m["parentesco"],
          "CPF": cpf_util.formatar(m["cpf"]) if m.get("cpf") else f"sem CPF ({m.get('sem_cpf_motivo')})",
          "Nascimento": m.get("data_nascimento"), "Necessidades especiais": m.get("necessidades_especiais"),
          "Situação": _situacao_membro(m)}
         for m in membros],
        hide_index=True, width="stretch",
    )
    for m in membros:
        if m.get("desaparecido") and not m.get("encontrado_em"):
            if st.button(f"✅ Marcar {m['nome_completo']} como encontrado(a)", key=f"encontrado-{m['id']}"):
                cliente.table("membros_familia").update({"encontrado_em": date.today().isoformat()}).eq("id", m["id"]).execute()
                st.success("Registrado como encontrado(a).")
                st.rerun()
    fotos = cliente.table("fotos_familia").select("*").eq("familia_id", familia["id"]).execute().data or []
    if fotos:
        colunas = st.columns(min(len(fotos), 4))
        for posicao, foto in enumerate(fotos):
            try:
                assinado = cliente.storage.from_(BUCKET).create_signed_url(foto["caminho"], 600)
                url = assinado.get("signedURL") or assinado.get("signedUrl") if isinstance(assinado, dict) else None
                if url:
                    colunas[posicao % len(colunas)].image(url, caption=foto.get("descricao"))
            except Exception as erro:
                colunas[posicao % len(colunas)].warning(f"Foto indisponível: {type(erro).__name__}")
    if not familia.get("data_saida") and st.button("Registrar saída da família do abrigo", key=f"saida-{familia['id']}"):
        pessoas = 1 + sum(1 for m in membros if not m.get("desaparecido") or m.get("encontrado_em"))
        cliente.table("familias_abrigadas").update({"data_saida": date.today().isoformat()}).eq("id", familia["id"]).execute()
        cliente.table("abrigos").update({"ocupacao": max(int(abrigo["ocupacao"]) - pessoas, 0)}).eq("id", abrigo["id"]).execute()
        st.success("Saída registrada e ocupação atualizada.")
        st.rerun()


def _situacao_membro(m: dict[str, Any]) -> str:
    if m.get("desaparecido") and not m.get("encontrado_em"):
        return f"DESAPARECIDO(A) — visto(a) em {m.get('visto_por_ultimo_em')} em {m.get('ultimo_local_visto')}"
    if m.get("desaparecido"):
        return f"encontrado(a) em {m.get('encontrado_em')}"
    return "no abrigo"


def renderizar_familias() -> None:
    from app.comum import carregar_municipios, cliente_supabase, mostrar_aviso
    from app.auth import obter_perfil
    from app.relatorio_menu import painel_relatorio

    st.title("Famílias abrigadas")
    st.caption("Dados pessoais sensíveis (LGPD): acesso restrito a quem atende a família.")
    mostrar_aviso()
    try:
        cliente = cliente_supabase()
        perfil = obter_perfil(cliente)
        if not perfil:
            raise PermissionError("Entre na plataforma.")
        municipio_id = perfil.get("municipio_id")
        if perfil["perfil"] == "administrador":
            municipios = carregar_municipios(cliente)
            # Só municípios com abrigo cadastrado, com a contagem (evita abrir num município vazio).
            contagem_abrigos: dict[str, int] = {}
            for a in cliente.table("abrigos").select("municipio_id").execute().data or []:
                codigo = str(a["municipio_id"]).strip()
                contagem_abrigos[codigo] = contagem_abrigos.get(codigo, 0) + 1
            if not contagem_abrigos:
                st.info("Nenhum abrigo cadastrado em nenhum município. Cadastre em Gestão municipal → Abrigos "
                        "ou rode os dados de teste (db/testes/dados_teste_abrigos_familias_relatos.sql).")
                return
            codigos = sorted(contagem_abrigos, key=lambda c: municipios.get(c, {}).get("nome", c))
            municipio_id = st.selectbox(
                "Município (somente os que têm abrigo)", codigos,
                format_func=lambda c: f"{municipios.get(c, {}).get('nome', c)} — {contagem_abrigos[c]} abrigo(s)",
                index=codigos.index(municipio_id) if municipio_id in codigos else 0, key="fam-mun",
            )
        abrigos = _abrigos_acessiveis(cliente, perfil, municipio_id)
    except Exception as erro:
        st.error(f"Não foi possível carregar: {erro}")
        return
    if not abrigos:
        st.info("Nenhum abrigo disponível para você neste município. Cadastre um abrigo em Gestão municipal → "
                "Abrigos, ou peça à coordenação municipal para designá-lo como coordenador de um abrigo "
                "(menu Usuários e permissões).")
        return
    abrigo_id = st.selectbox("Abrigo", [a["id"] for a in abrigos],
                             format_func=lambda i: next(f"{a['nome']} ({a['ocupacao']}/{a['capacidade']})" for a in abrigos if a["id"] == i))
    abrigo = next(a for a in abrigos if a["id"] == abrigo_id)
    c1, c2, c3 = st.columns(3)
    c1.metric("Capacidade", abrigo["capacidade"])
    c2.metric("Abrigados", abrigo["ocupacao"])
    c3.metric("Vagas", int(abrigo["capacidade"]) - int(abrigo["ocupacao"]))

    familias = cliente.table("familias_abrigadas").select("*").eq("abrigo_id", abrigo_id).order("criado_em", desc=True).execute().data or []
    ids = [f["id"] for f in familias]
    membros = (cliente.table("membros_familia").select("*").in_("familia_id", ids).execute().data or []) if ids else []
    contagem = {i: 1 for i in ids}
    for m in membros:
        if not m.get("desaparecido") or m.get("encontrado_em"):
            contagem[m["familia_id"]] = contagem.get(m["familia_id"], 1) + 1
    por_familia = {f["id"]: f for f in familias}
    desaparecidos = [
        {"Nome completo": m["nome_completo"], "Parentesco": m["parentesco"],
         "Família (responsável)": por_familia[m["familia_id"]]["responsavel_nome"],
         "Telefone da família": por_familia[m["familia_id"]].get("telefone"),
         "Visto por último em": m.get("visto_por_ultimo_em"), "Último local visto": m.get("ultimo_local_visto"),
         "Situação": "encontrado(a) em " + str(m["encontrado_em"]) if m.get("encontrado_em") else "DESAPARECIDO(A)"}
        for m in membros if m.get("desaparecido")
    ]
    linhas_membros = [
        {"Família (responsável)": por_familia[m["familia_id"]]["responsavel_nome"], "Nome completo": m["nome_completo"],
         "Parentesco": m["parentesco"], "CPF": cpf_util.mascarar(m["cpf"]) if m.get("cpf") else "sem CPF",
         "Situação": _situacao_membro(m)}
        for m in membros
    ]
    ativas = [f for f in familias if not f.get("data_saida")]
    linhas = [
        {"Responsável": f["responsavel_nome"], "CPF": cpf_util.mascarar(f["responsavel_cpf"]),
         "Pessoas": contagem.get(f["id"], 1), "Imóvel": SITUACOES_IMOVEL.get(f["situacao_imovel"]),
         "Entrada": f["data_entrada"], "Saída": f.get("data_saida") or "",
         "Necessidades": ", ".join(f.get("necessidades") or [])}
        for f in familias
    ]
    em_aberto = [d for d in desaparecidos if d["Situação"] == "DESAPARECIDO(A)"]
    aba_lista, aba_desap, aba_nova = st.tabs(
        [f"👪 Famílias ({len(ativas)} ativas)", f"🔎 Desaparecidos ({len(em_aberto)})", "➕ Cadastrar família"]
    )
    with aba_desap:
        if desaparecidos:
            st.warning(f"{len(em_aberto)} pessoa(s) desaparecida(s) em aberto neste abrigo. Compartilhe só com "
                       "equipes de busca e autoridades.")
            st.dataframe(desaparecidos, hide_index=True, width="stretch")
        else:
            st.success("Nenhuma pessoa desaparecida registrada neste abrigo.")
    with aba_lista:
        st.dataframe(linhas, hide_index=True, width="stretch")
        if familias:
            escolhida = st.selectbox(
                "Ver detalhes", ids, key="fam-detalhe",
                format_func=lambda i: next(f"{f['responsavel_nome']} — {cpf_util.mascarar(f['responsavel_cpf'])}" for f in familias if f["id"] == i),
            )
            _detalhe_familia(cliente, next(f for f in familias if f["id"] == escolhida), abrigo)
    with aba_nova:
        _formulario_familia(cliente, abrigo)
    painel_relatorio(
        "Relatório de famílias abrigadas",
        [("Famílias", linhas), ("Membros", linhas_membros), ("Pessoas desaparecidas", desaparecidos)],
        subtitulo=abrigo["nome"],
        resumo={"Famílias ativas": len(ativas), "Pessoas abrigadas": abrigo["ocupacao"],
                "Desaparecidos em aberto": len(em_aberto),
                "Imóveis destruídos": sum(1 for f in ativas if f["situacao_imovel"] == "destruido"),
                "Aviso": "CPF mascarado no relatório; documento com dados pessoais (LGPD)"},
    )
