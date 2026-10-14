"""Usuários e permissões: perfis, município e coordenadores de abrigo.

- Administrador: muda perfil e município de qualquer conta (inclusive promove
  voluntários a coordenador municipal, saúde, logística, campo...).
- Coordenação municipal: designa coordenadores de abrigo do seu município.
Contas novas são criadas pelo autocadastro (voluntário) ou no Supabase Auth.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

PERFIS = {
    "administrador": "Tudo: usuários, permissões, regras, pesos, fontes; todos os municípios.",
    "gestor_nacional": "Lê todos os municípios; revisa e aprova alertas; relatórios.",
    "gestor_estadual": "Lê os municípios da sua UF; revisa e aprova alertas.",
    "coordenador_municipal": "Opera o seu município: cadastros, abrigos, famílias, tarefas, alertas e envio.",
    "operador_monitoramento": "Sala de monitoramento (estações, leituras, fontes); revisa alertas.",
    "saude_assistencia": "Saúde e assistência do município, inclusive famílias abrigadas.",
    "logistica_abastecimento": "Estoques, abrigos, rotas e assinaturas do município.",
    "agente_campo": "Registro de campo (famílias afetadas) no município.",
    "voluntario": "Lê todo o painel (sem dados de famílias); registra e confirma relatos; não aprova alertas.",
    "pesquisador": "Dados abertos e metodologia.",
}


def _matriz() -> None:
    st.dataframe([{"Perfil": p, "O que pode fazer": d} for p, d in PERFIS.items()], hide_index=True, width="stretch")
    st.caption("Coordenador de abrigo não é um perfil: qualquer conta pode ser designada a um abrigo e passa a "
               "cadastrar as famílias e atualizar a ocupação daquele abrigo.")


def _designar_abrigos(cliente: Any, municipio_id: str, usuarios: list[dict], nomes_usuarios: dict[str, str]) -> list[dict]:
    abrigos = cliente.table("abrigos").select("id,nome,capacidade,ocupacao").eq("municipio_id", municipio_id).order("nome").execute().data or []
    if not abrigos:
        st.info("Nenhum abrigo cadastrado neste município (cadastre em Gestão municipal → Abrigos).")
        return []
    responsaveis = cliente.table("abrigo_responsaveis").select("*").in_("abrigo_id", [a["id"] for a in abrigos]).execute().data or []
    nomes_abrigos = {a["id"]: a["nome"] for a in abrigos}
    linhas = [{"Abrigo": nomes_abrigos.get(r["abrigo_id"]), "Pessoa": nomes_usuarios.get(r["usuario_id"], r["usuario_id"]),
               "Função": r["funcao"], "Desde": str(r["criado_em"])[:10]} for r in responsaveis]
    st.dataframe(linhas, hide_index=True, width="stretch")
    candidatos = [u for u in usuarios if str(u.get("municipio_id") or "").strip() == municipio_id]
    if not candidatos:
        st.info("Nenhuma conta deste município para designar (voluntários se cadastram na tela de login).")
        return linhas
    with st.form(f"designar-{municipio_id}", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        abrigo_id = c1.selectbox("Abrigo", list(nomes_abrigos), format_func=lambda i: nomes_abrigos[i])
        usuario_id = c2.selectbox("Pessoa", [u["id"] for u in candidatos],
                                  format_func=lambda i: f"{nomes_usuarios[i]} ({next(u['perfil'] for u in candidatos if u['id'] == i)})")
        funcao = c3.selectbox("Função", ["coordenador", "apoio"])
        if st.form_submit_button("Designar"):
            try:
                cliente.table("abrigo_responsaveis").upsert(
                    {"abrigo_id": abrigo_id, "usuario_id": usuario_id, "funcao": funcao}, on_conflict="abrigo_id,usuario_id"
                ).execute()
                st.success(f"{nomes_usuarios[usuario_id]} designado(a) para {nomes_abrigos[abrigo_id]}.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível designar: {erro}")
    if responsaveis:
        with st.form(f"remover-{municipio_id}"):
            chave = st.selectbox(
                "Remover designação", [f"{r['abrigo_id']}|{r['usuario_id']}" for r in responsaveis],
                format_func=lambda k: f"{nomes_abrigos.get(k.split('|')[0])} — {nomes_usuarios.get(k.split('|')[1], '')}",
            )
            if st.form_submit_button("Remover"):
                abrigo_id, usuario_id = chave.split("|")
                cliente.table("abrigo_responsaveis").delete().eq("abrigo_id", abrigo_id).eq("usuario_id", usuario_id).execute()
                st.success("Designação removida.")
                st.rerun()
    return linhas


def renderizar_permissoes() -> None:
    from app.comum import carregar_municipios, exigir_perfil, mostrar_aviso
    from app.relatorio_menu import painel_relatorio

    st.title("Usuários e permissões")
    mostrar_aviso()
    try:
        cliente, perfil = exigir_perfil({"administrador", "coordenador_municipal"})
        municipios = carregar_municipios(cliente)
        usuarios = cliente.table("usuarios").select("id,nome,perfil,municipio_id,auth_id").order("nome").execute().data or []
    except Exception as erro:
        st.error(f"Não foi possível carregar os usuários: {erro}")
        return
    admin = perfil["perfil"] == "administrador"
    nomes_usuarios = {u["id"]: u["nome"] for u in usuarios}
    nome_mun = lambda c: municipios.get(str(c or "").strip(), {}).get("nome", "—")  # noqa: E731

    aba_usuarios, aba_abrigos, aba_matriz = st.tabs(["👤 Contas e perfis", "🏠 Coordenadores de abrigo", "📋 O que cada perfil pode fazer"])
    with aba_usuarios:
        linhas_usuarios = [{"Nome": u["nome"], "Perfil": u["perfil"], "Município": nome_mun(u.get("municipio_id"))} for u in usuarios]
        st.dataframe(linhas_usuarios, hide_index=True, width="stretch")
        if admin and usuarios:
            with st.form("mudar-perfil"):
                st.markdown("**Atribuir perfil e município** (vale no próximo carregamento da pessoa)")
                c1, c2, c3 = st.columns(3)
                usuario_id = c1.selectbox("Conta", [u["id"] for u in usuarios], format_func=lambda i: nomes_usuarios[i])
                atual = next(u for u in usuarios if u["id"] == usuario_id)
                novo_perfil = c2.selectbox("Perfil", list(PERFIS), index=list(PERFIS).index(atual["perfil"]) if atual["perfil"] in PERFIS else 0)
                codigos = [""] + sorted(municipios, key=lambda c: municipios[c]["nome"])
                atual_mun = str(atual.get("municipio_id") or "").strip()
                novo_mun = c3.selectbox("Município", codigos, index=codigos.index(atual_mun) if atual_mun in codigos else 0,
                                        format_func=lambda c: "— (todos / nacional)" if not c else municipios[c]["nome"])
                st.caption(PERFIS.get(novo_perfil, ""))
                if st.form_submit_button("Salvar permissão"):
                    if novo_perfil in {"coordenador_municipal", "saude_assistencia", "logistica_abastecimento",
                                       "agente_campo", "gestor_estadual"} and not novo_mun:
                        st.error("Este perfil exige um município.")
                    else:
                        try:
                            cliente.table("usuarios").update({"perfil": novo_perfil, "municipio_id": novo_mun or None}).eq("id", usuario_id).execute()
                            st.success(f"{nomes_usuarios[usuario_id]}: perfil {novo_perfil}, município {nome_mun(novo_mun)}.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível salvar: {erro}")
        elif not admin:
            st.info("Somente o administrador muda perfis. Você pode designar coordenadores de abrigo na aba ao lado.")
    with aba_abrigos:
        if admin:
            codigos = sorted(municipios, key=lambda c: municipios[c]["nome"])
            municipio_id = st.selectbox("Município", codigos, format_func=lambda c: municipios[c]["nome"], key="perm-mun")
        else:
            municipio_id = perfil["municipio_id"]
            st.write(f"Município: **{nome_mun(municipio_id)}**")
        linhas_abrigos = _designar_abrigos(cliente, municipio_id, usuarios, nomes_usuarios)
    with aba_matriz:
        _matriz()
    painel_relatorio(
        "Relatório de usuários e permissões",
        [("Contas", linhas_usuarios), ("Coordenadores de abrigo", linhas_abrigos)],
        resumo={"Contas": len(usuarios), "Voluntários": sum(1 for u in usuarios if u["perfil"] == "voluntario")},
    )
