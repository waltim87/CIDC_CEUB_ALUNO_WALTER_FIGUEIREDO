"""Painel secundário de revisão e aprovação humana dos alertas."""

from __future__ import annotations

import streamlit as st

from app.comum import cliente_supabase, mostrar_aviso
from core.alertas import atualizar_alerta, formatar_fontes, listar_alertas

st.set_page_config(page_title="Revisão de alertas | CIDC", page_icon="🚨", layout="wide")
st.title("Painel secundário de alertas")
st.caption("Revise, edite, aprove ou rejeite as sugestões do motor")
mostrar_aviso()
st.error(
    "Nenhuma notificação externa é enviada nesta fase. Aprovar registra a decisão "
    "humana; integração de canais é posterior."
)

try:
    cliente = cliente_supabase()
    alertas = listar_alertas(cliente, limite=200)
except Exception as erro:
    st.error(f"Não foi possível carregar os alertas: {erro}")
    st.stop()

pendentes = [alerta for alerta in alertas if alerta["status"] == "rascunho"]
if not alertas:
    st.info("Não há alertas registrados. Sem regras ativas e dados confirmados, isso é esperado.")
else:
    st.metric("Rascunhos aguardando revisão", len(pendentes))
    for alerta in alertas:
        municipio = alerta.get("municipio") or {}
        nome_municipio = municipio.get("nome", alerta["municipio_id"])
        uf = municipio.get("uf", "")
        with st.expander(
            f"{alerta['classe']} — {nome_municipio}/{uf} — {alerta['status']} — "
            f"{alerta['criado_em']}"
        ):
            indice = alerta.get("indice") or {}
            st.caption(
                f"Fontes e leituras: {formatar_fontes(indice.get('fontes_json'))} · "
                f"Leitura de referência: "
                f"{indice.get('data_hora_leitura_referencia') or 'não informada'} · "
                f"Índice calculado: {indice.get('data_hora') or 'não informado'} · "
                f"Alerta emitido: {alerta.get('emitido_em') or 'ainda não emitido'}"
            )
            if alerta["status"] == "rascunho":
                with st.form(f"revisao-{alerta['id']}"):
                    texto = st.text_area("Texto sugerido (edite antes de aprovar)", alerta["texto"])
                    aprovar = st.form_submit_button("Aprovar versão revisada")
                    rejeitar = st.form_submit_button("Rejeitar rascunho")
                    if aprovar:
                        try:
                            atualizar_alerta(
                                cliente,
                                alerta["id"],
                                acao="aprovar",
                                texto=texto,
                            )
                            st.success("Alerta aprovado. Nenhuma mensagem foi enviada.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível aprovar: {erro}")
                    if rejeitar:
                        try:
                            atualizar_alerta(
                                cliente,
                                alerta["id"],
                                acao="rejeitar",
                            )
                            st.success("Rascunho rejeitado.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"Não foi possível rejeitar: {erro}")
            else:
                st.text(alerta["texto"])
