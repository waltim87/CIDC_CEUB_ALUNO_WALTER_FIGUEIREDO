"""Teste integrado no banco real: cria dados [TESTE], confere ligações entre áreas e tenta
burlar permissões com as contas de teste (@cidc-teste.example).

Uso: ./.venv/Scripts/python.exe scripts/teste_integrado.py
A senha das contas fica em Documentos/CIDC_contas_teste.txt (nunca é exibida).
Tudo o que é criado leva "[TESTE]" e sai com db/testes/limpar_dados_teste.sql.
Não aprova alertas nem envia Telegram.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")
U, K = os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"]
ARQUIVO_SENHA = Path(os.environ.get("CIDC_SENHAS_TESTE", Path.home() / "OneDrive/Documentos/CIDC_contas_teste.txt"))
if not ARQUIVO_SENHA.exists():
    ARQUIVO_SENHA = Path.home() / "Documents/CIDC_contas_teste.txt"
SENHA = ARQUIVO_SENHA.read_text(encoding="utf-8-sig").split("Senha de todas: ")[1].split()[0]
LABREA, BOCA = "1302405", "1300706"
RESULTADOS: list[tuple[str, bool, str]] = []
_tokens: dict[str, str] = {}
_ids: dict[str, str] = {}


def token(conta: str) -> str:
    if conta not in _tokens:
        r = requests.post(f"{U}/auth/v1/token?grant_type=password", headers={"apikey": K},
                          json={"email": f"{conta}@cidc-teste.example", "password": SENHA}, timeout=30).json()
        _tokens[conta], _ids[conta + ":auth"] = r["access_token"], r["user"]["id"]
    return _tokens[conta]


def h(conta: str | None) -> dict[str, str]:
    base = {"apikey": K, "Content-Type": "application/json", "Prefer": "return=representation"}
    if conta:
        base["Authorization"] = "Bearer " + token(conta)
    return base


def rpc(conta: str | None, funcao: str, **p):
    r = requests.post(f"{U}/rest/v1/rpc/{funcao}", headers=h(conta), json=p, timeout=60)
    corpo = r.json() if r.content else None
    return r.status_code < 300, (corpo if r.status_code < 300 else (corpo or {}).get("message", str(corpo)))


def ler(conta: str | None, consulta: str) -> list:
    r = requests.get(f"{U}/rest/v1/{consulta}", headers=h(conta), timeout=60)
    return r.json() if r.status_code == 200 and isinstance(r.json(), list) else []


def escrever(conta: str | None, metodo: str, consulta: str, carga: dict | None = None):
    r = requests.request(metodo, f"{U}/rest/v1/{consulta}", headers=h(conta), json=carga, timeout=60)
    return r.status_code, (r.json() if r.content else None)


def checar(nome: str, ok: bool, detalhe: object = "") -> bool:
    RESULTADOS.append((nome, bool(ok), str(detalhe)[:140]))
    return bool(ok)


def usuario_id(conta: str) -> str:
    token(conta)
    return ler(conta, f"usuarios?select=id&auth_id=eq.{_ids[conta + ':auth']}")[0]["id"]


def main() -> int:
    if not ler("coordenacao.labrea", "responsaveis_area?select=id&limit=1") and requests.get(
            f"{U}/rest/v1/responsaveis_area?select=id&limit=1", headers=h("coordenacao.labrea")).status_code != 200:
        print("Aplique antes as migrations 0026 e 0027 no Supabase.")
        return 2

    # ------------------------------------------------ 1. responsáveis por área (Lábrea)
    titulares = {"coordenacao_geral": "coordenacao.labrea", "monitoramento_alerta": "monitoramento.labrea",
                 "campo_vistorias": "campo.labrea", "saude": "saude.labrea", "logistica_estoque": "logistica.labrea",
                 "abrigos": "campo.labrea", "embarcacoes_transporte": "logistica.labrea", "voluntarios": "voluntario1"}
    for area, conta in titulares.items():
        ok, msg = rpc("coordenacao.labrea", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area=area,
                      p_papel="titular", p_usuario_id=usuario_id(conta), p_observacao="[TESTE]")
        checar(f"responsável {area} = {conta}", ok, msg)
    ok, msg = rpc("coordenacao.labrea", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area="assistencia_social",
                  p_nome_externo="[TESTE] Secretaria Municipal de Assistência Social", p_contato="(97) 3331-0000",
                  p_observacao="[TESTE]")
    checar("responsável externo (sem conta) para assistência social", ok, msg)
    ok, msg = rpc("coordenacao.labrea", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area="saude",
                  p_papel="suplente", p_usuario_id=usuario_id("coordenacao.labrea"), p_observacao="[TESTE]")
    checar("suplente da saúde", ok, msg)
    ok, msg = rpc("saude.labrea", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area="saude",
                  p_nome_externo="invasao invasao")
    checar("BLOQUEIO: saúde não define responsáveis", not ok, msg)
    ok, msg = rpc("coordenacao.boca", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area="saude",
                  p_nome_externo="invasao invasao")
    checar("BLOQUEIO: coordenação de outro município não define responsáveis de Lábrea", not ok, msg)
    ok, msg = rpc("coordenacao.labrea", "cidc_responsavel_area_definir", p_municipio_id=LABREA, p_area="saude",
                  p_usuario_id=usuario_id("coordenacao.boca"))
    checar("BLOQUEIO: pessoa de outro município não vira responsável em Lábrea", not ok, msg)
    ativos = ler("voluntario1", f"responsaveis_area?select=area,papel&municipio_id=eq.{LABREA}&ate=is.null")
    checar("voluntária lê a matriz de responsáveis", len(ativos) >= 10, f"{len(ativos)} atribuições ativas")

    # ------------------------------------------------ 2. tarefa vai para o titular da área
    st_, linhas = escrever("coordenacao.labrea", "POST", "acoes", {
        "municipio_id": LABREA, "eixo": "preparacao", "descricao": "[TESTE] Conferir estoque de medicamentos nos abrigos",
        "responsavel_funcao": "saude_assistencia", "origem": "manual"})
    tarefa = (linhas or [{}])[0] if isinstance(linhas, list) else {}
    checar("tarefa da função saúde vai para a titular da saúde",
           tarefa.get("responsavel_id") == usuario_id("saude.labrea") and "Saúde" in str(tarefa.get("responsavel_nome")),
           tarefa.get("responsavel_nome") or linhas)
    if tarefa.get("id"):
        st_, alt = escrever("saude.labrea", "PATCH", f"acoes?id=eq.{tarefa['id']}", {"status": "concluida",
                                                                                     "observacao": "[TESTE] feito"})
        checar("titular da saúde conclui a tarefa", st_ < 300 and alt and alt[0]["status"] == "concluida", st_)

    # ------------------------------------------------ 3. embarcações
    barcos = {}
    for nome, tipo, cap in [("[TESTE] Voadeira 01", "lancha", 8), ("[TESTE] Balsa da Prefeitura", "balsa", 40)]:
        ok, bid = rpc("logistica.labrea", "cidc_embarcacao_cadastrar", p_municipio_id=LABREA, p_nome=nome, p_tipo=tipo,
                      p_capacidade=cap, p_piloto="[TESTE] Piloto", p_observacoes="[TESTE]")
        checar(f"logística cadastra {nome}", ok, bid)
        if ok:
            barcos[nome] = bid
    voadeira = barcos.get("[TESTE] Voadeira 01")
    if voadeira:
        ok, msg = rpc("coordenacao.boca", "cidc_embarcacao_cadastrar", p_id=voadeira, p_municipio_id=BOCA,
                      p_nome="invasao", p_tipo="outro")
        checar("BLOQUEIO: outro município não sobrescreve barco de Lábrea", not ok, msg)
        st_, alt = escrever("voluntario1", "PATCH", f"embarcacoes?id=eq.{voadeira}", {"status": "manutencao"})
        checar("BLOQUEIO: voluntária não altera barco direto na tabela", st_ >= 400 or not alt, st_)

    # ------------------------------------------------ 4. ocorrência: equipe -> titular -> barco -> resolve
    ok, oid = rpc("campo.labrea", "cidc_ocorrencia_abrir", p_municipio_id=LABREA, p_tipo="resgate", p_prioridade="critica",
                  p_titulo="[TESTE] Família ilhada no telhado - Comunidade São Raimundo", p_pessoas=5)
    checar("agente de campo abre ocorrência", ok, oid)
    if ok:
        ok, msg = rpc("coordenacao.labrea", "cidc_ocorrencia_atualizar", p_ocorrencia=oid, p_equipe="logistica_abastecimento",
                      p_texto="[TESTE] logística com barco")
        o = ler("coordenacao.labrea", f"ocorrencias?id=eq.{oid}&select=responsavel_id,responsavel_nome,status")[0]
        checar("ocorrência passada à logística vai para o titular da logística",
               o["responsavel_id"] == usuario_id("logistica.labrea"), o["responsavel_nome"])
        if voadeira:
            ok, msg = rpc("voluntario1", "cidc_ocorrencia_atribuir_embarcacao", p_ocorrencia=oid, p_embarcacao_id=voadeira)
            checar("BLOQUEIO: voluntária não atribui barco", not ok, msg)
            ok, msg = rpc("logistica.labrea", "cidc_ocorrencia_atribuir_embarcacao", p_ocorrencia=oid, p_embarcacao_id=voadeira)
            barco = ler("logistica.labrea", f"embarcacoes?id=eq.{voadeira}&select=status")[0]["status"]
            checar("logística atribui a voadeira (fica em uso)", ok and barco == "em_uso", msg if not ok else barco)
        for situacao in ("em_deslocamento", "em_atendimento"):
            rpc("logistica.labrea", "cidc_ocorrencia_atualizar", p_ocorrencia=oid, p_status=situacao)
        ok, msg = rpc("logistica.labrea", "cidc_ocorrencia_atualizar", p_ocorrencia=oid, p_status="resolvida",
                      p_texto="[TESTE] 5 pessoas levadas ao abrigo")
        checar("logística resolve a ocorrência", ok, msg)
        if voadeira:
            barco = ler("logistica.labrea", f"embarcacoes?id=eq.{voadeira}&select=status")[0]["status"]
            checar("barco volta a ficar disponível ao resolver", barco == "disponível", barco)

    # ------------------------------------------------ 5. vistoria de abrigo
    abrigos = ler("coordenacao.labrea", f"abrigos?select=id,nome&municipio_id=eq.{LABREA}&nome=like.%5BTESTE%5D*&order=nome")
    # Primeiro o abrigo que o agente de campo coordena (designado em db/testes/usuarios_teste.sql).
    do_campo = {r["abrigo_id"] for r in ler("coordenacao.labrea", "abrigo_responsaveis?select=abrigo_id,usuario_id")
                if r["usuario_id"] == usuario_id("campo.labrea")}
    abrigos.sort(key=lambda a: a["id"] not in do_campo)
    if abrigos:
        ok, msg = rpc("campo.labrea", "cidc_abrigo_vistoria_registrar", p_abrigo_id=abrigos[0]["id"], p_agua=True,
                      p_energia=True, p_banheiros=True, p_cozinha=True, p_acessibilidade=True, p_kits=True,
                      p_colchoes=True, p_observacao="[TESTE] vistoria completa")
        checar("coordenador do abrigo registra vistoria completa (selo)", ok, msg)
        if len(abrigos) > 1:
            ok, msg = rpc("coordenacao.labrea", "cidc_abrigo_vistoria_registrar", p_abrigo_id=abrigos[1]["id"], p_agua=True,
                          p_energia=False, p_observacao="[TESTE] sem energia")
            checar("coordenação registra vistoria incompleta", ok, msg)
        st_, msg = escrever("coordenacao.boca", "POST", "abrigo_vistorias", {
            "abrigo_id": abrigos[0]["id"], "municipio_id": BOCA, "vistoriado_por": usuario_id("coordenacao.boca"),
            "selo_pronto": True, "observacoes": "[TESTE] invasao"})
        checar("BLOQUEIO: vistoria falsa de outro município direto na tabela", st_ >= 400, st_)
        ok, msg = rpc("voluntario1", "cidc_abrigo_vistoria_registrar", p_abrigo_id=abrigos[2 if len(abrigos) > 2 else 0]["id"],
                      p_agua=True, p_observacao="[TESTE] invasao")
        checar("BLOQUEIO: voluntária sem abrigo não vistoria", not ok, msg)
        recente = ler("voluntario1", f"abrigo_vistoria_recente?select=*&abrigo_id=eq.{abrigos[0]['id']}")
        checar("selo do abrigo aparece na última vistoria", recente and recente[0]["selo_pronto"] is True, recente)

    # ------------------------------------------------ 6. ficha S2iD
    comunidades = ler("campo.labrea", f"comunidades?select=id,nome&municipio_id=eq.{LABREA}&nome=like.%5BTESTE%5D*")
    for c in comunidades[:2]:
        ok, msg = rpc("campo.labrea", "cidc_pessoas_afetadas_cadastrar", p_comunidade_id=c["id"], p_data=date.today().isoformat(),
                      p_familias=12, p_pessoas=48, p_desalojados=20, p_desabrigados=15, p_danos_casas=9,
                      p_fonte_afetados="[TESTE] vistoria de campo", p_observacoes="[TESTE]")
        checar(f"ficha S2iD de {c['nome']} (primeiro registro)", ok, msg)
    if comunidades:
        ok, msg = rpc("saude.labrea", "cidc_pessoas_afetadas_cadastrar", p_comunidade_id=comunidades[0]["id"],
                      p_data=date.today().isoformat(), p_familias=1, p_observacoes="[TESTE] invasao")
        checar("BLOQUEIO: saúde não registra afetados", not ok, msg)

    # ------------------------------------------------ 7. ajuda humanitária
    ok, msg = rpc("logistica.labrea", "cidc_estoque_movimentar", p_municipio_id=LABREA, p_item="agua_potavel",
                  p_quantidade=2000, p_motivo="envio_estadual", p_origem_destino="[TESTE] Estado", p_observacao="[TESTE]")
    checar("logística registra entrada de água", ok, msg)
    if comunidades:
        ok, msg = rpc("logistica.labrea", "cidc_ajuda_entregar", p_municipio_id=LABREA, p_itens={"agua_potavel": 500},
                      p_comunidade_id=comunidades[0]["id"], p_pessoas=48, p_observacao="[TESTE] entrega de barco")
        checar("logística entrega água à comunidade", ok, msg)
        ok, msg = rpc("logistica.labrea", "cidc_ajuda_entregar", p_municipio_id=LABREA, p_itens={"agua_potavel": 999999},
                      p_comunidade_id=comunidades[0]["id"], p_observacao="[TESTE]")
        checar("BLOQUEIO: entregar mais do que o saldo", not ok, msg)

    # ------------------------------------------------ 8. privacidade e acesso indevido
    checar("logística acessa as assinaturas de alerta (restaurado)",
           requests.get(f"{U}/rest/v1/assinaturas_alerta?select=id&municipio_id=eq.{LABREA}&limit=1",
                        headers=h("logistica.labrea")).status_code == 200)
    checar("voluntária não lê mensagens do Telegram de outros", not ler("voluntario1", "notificacoes_telegram?select=id"))
    checar("voluntário sem designação não vê famílias abrigadas (CPF/nomes)",
           not ler("voluntario2", "familias_abrigadas?select=id&limit=5"))
    checar("voluntário sem designação não vê membros das famílias", not ler("voluntario2", "membros_familia?select=id&limit=5"))
    # voluntario1 é "apoio" do abrigo Escola Rio Purus: vê só as famílias DAQUELE abrigo.
    vistas = {f["abrigo_id"] for f in ler("voluntario1", "familias_abrigadas?select=abrigo_id&limit=500")}
    checar("voluntária de apoio vê só as famílias do próprio abrigo", vistas and vistas <= do_campo, vistas)
    checar("coordenador do abrigo vê famílias do abrigo", bool(ler("campo.labrea", "familias_abrigadas?select=id&limit=5")))
    checar("pesquisador não lê o chat", not ler("pesquisa", "chat_mensagens?select=id&limit=5"))
    checar("coordenação de outro município não vê famílias de Lábrea",
           not ler("coordenacao.boca", f"familias_abrigadas?select=id&municipio_id=eq.{LABREA}&limit=5"))
    for tabela in ("familias_abrigadas", "membros_familia", "usuarios", "voluntarios", "chat_mensagens", "notificacoes_telegram",
                   "responsaveis_area", "ocorrencias", "ajuda_movimentos", "embarcacoes", "acoes", "plano_protocolo"):
        checar(f"visitante sem login não lê {tabela}", not ler(None, f"{tabela}?select=*&limit=3"))
    ok, msg = rpc(None, "cidc_ocorrencia_abrir", p_municipio_id=LABREA, p_tipo="outro", p_prioridade="baixa", p_titulo="anonimo")
    checar("BLOQUEIO: visitante sem login não abre ocorrência", not ok, msg)

    falhas = [r for r in RESULTADOS if not r[1]]
    for nome, ok, detalhe in RESULTADOS:
        print(f"{'✅' if ok else '❌'} {nome}" + ("" if ok else f"  → {detalhe}"))
    print(f"\n{len(RESULTADOS) - len(falhas)} de {len(RESULTADOS)} verificações OK")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
