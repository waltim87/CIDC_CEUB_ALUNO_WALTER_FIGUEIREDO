"""Teste A2: saude.labrea NAO deve mudar situacao de ocorrencia sem ser responsavel.

Le as configuracoes do .env local e as senhas de OneDrive\Documentos\CIDC_contas_teste.txt.
Rode com: .\.venv\Scripts\python.exe scripts\teste_a2_ocorrencia_saude.py
"""

from __future__ import annotations

from pathlib import Path

import requests


def carregar_env(caminho: Path) -> dict[str, str]:
    """Lê variaveis de estilo KEY=valor de um arquivo .env (sem aspas)."""
    vars_: dict[str, str] = {}
    if not caminho.exists():
        return vars_
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        vars_[chave.strip()] = valor.strip().strip('"').strip("'")
    return vars_


def ler_contas_teste(caminho: Path) -> dict[str, str]:
    """Lê emails e senha do arquivo de contas de teste.

    Formato esperado do arquivo:
        Linha 1: cabecalho
        Linha 2: Senha de todas: XXX
        Linha 3: (em branco)
        Linha 4+: um email por linha

    Todas as contas usam a mesma senha.
    """
    contas: dict[str, str] = {}
    if not caminho.exists():
        return contas
    texto = caminho.read_text(encoding="utf-8-sig")
    senha_comum = ""
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.lower().startswith("senha de todas"):
            _, _, senha_comum = linha.partition(":")
            senha_comum = senha_comum.strip()
            continue
        if "@" in linha and senha_comum:
            contas[linha] = senha_comum
    return contas


def login(url: str, anon_key: str, email: str, senha: str) -> tuple[str, str] | None:
    """Faz login via Supabase Auth e retorna (access_token, user_id)."""
    resp = requests.post(
        f"{url}/auth/v1/token?grant_type=password",
        headers={
            "apikey": anon_key,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": senha},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  ERRO no login de {email}: HTTP {resp.status_code} - {resp.text[:200]}")
        return None
    dados = resp.json()
    token = dados.get("access_token")
    user_id = dados.get("user", {}).get("id") if isinstance(dados.get("user"), dict) else None
    if not token or not user_id:
        print(f"  ERRO: login de {email} nao retornou token ou id do usuario")
        return None
    return token, user_id


def rpc(url: str, anon_key: str, token: str, funcao: str, parametros: dict) -> requests.Response:
    """Chama uma funcao RPC do Supabase pelo REST."""
    return requests.post(
        f"{url}/rest/v1/rpc/{funcao}",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json=parametros,
        timeout=30,
    )


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    env = carregar_env(base / ".env")

    url = env.get("SUPABASE_URL")
    anon_key = env.get("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        print("ERRO: nao encontrei SUPABASE_URL ou SUPABASE_ANON_KEY no .env")
        print("  Verifique o arquivo .env na pasta do projeto.")
        return

    # Caminho do arquivo de senhas (tenta OneDrive/Documentos e depois Documents)
    contas_caminho = Path.home() / "OneDrive" / "Documentos" / "CIDC_contas_teste.txt"
    if not contas_caminho.exists():
        contas_caminho = Path.home() / "Documentos" / "CIDC_contas_teste.txt"
    contas = ler_contas_teste(contas_caminho)
    if not contas:
        print(f"ERRO: nao li contas de teste de {contas_caminho}")
        return

    email_campo = "campo.labrea@cidc-teste.example"
    email_saude = "saude.labrea@cidc-teste.example"

    if email_campo not in contas or email_saude not in contas:
        print("ERRO: contas campo.labrea ou saude.labrea nao estao no arquivo de senhas.")
        print(f"  Contas encontradas: {list(contas.keys())}")
        return

    print("=== TESTE A2: saude.labrea nao pode mudar situacao de ocorrencia ===\n")

    # 1. Login como campo.labrea
    print(f"1. Fazendo login como {email_campo}...")
    resultado = login(url, anon_key, email_campo, contas[email_campo])
    if not resultado:
        return
    token_campo, user_id_campo = resultado
    print("   Login OK.\n")

    # 2. Descobrir o municipio do campo.labrea pela tabela usuarios (auth_id)
    print("2. Consultando municipio do usuario...")
    resp = requests.get(
        f"{url}/rest/v1/usuarios",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token_campo}"},
        params={"auth_id": f"eq.{user_id_campo}", "select": "id,municipio_id,nome"},
        timeout=30,
    )
    if resp.status_code != 200 or not resp.json():
        print(f"   ERRO ao consultar usuario: HTTP {resp.status_code} - {resp.text[:200]}")
        return
    usuario = resp.json()[0]
    municipio_id = usuario.get("municipio_id")
    print(f"   Municipio: {municipio_id} - {usuario.get('nome')}\n")

    # 3. Criar um relato de campo (para contornar bug da funcao abrir que nao inicializa v_relato
    #    quando p_relato_id e null)
    print("3. Criando relato de campo como campo.labrea...")
    resp = requests.post(
        f"{url}/rest/v1/relatos",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {token_campo}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json={
            "municipio_id": municipio_id,
            "tipo": "cheia_alagamento",
            "intensidade": "moderada",
            "descricao": "[TESTE] Relato para abrir ocorrencia na A2",
            "latitude": -3.1,
            "longitude": -62.1,
        },
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"   ERRO ao criar relato: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    relato_id = resp.json()[0]["id"]
    print(f"   Relato criado: id={relato_id}\n")

    # 4. Abrir ocorrencia [TESTE] a partir do relato
    print("4. Abrindo ocorrencia [TESTE] como campo.labrea...")
    resp = rpc(
        url, anon_key, token_campo, "cidc_ocorrencia_abrir",
        {
            "p_municipio_id": municipio_id,
            "p_tipo": "saude",
            "p_prioridade": "media",
            "p_titulo": "[TESTE] A2 - teste de permissao saude",
            "p_descricao": "Ocorrencia de teste para a tarefa A2.",
            "p_relato_id": relato_id,
        },
    )
    if resp.status_code not in (200, 201):
        print(f"   ERRO ao abrir ocorrencia: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    dados = resp.json()
    ocorrencia_id = dados if isinstance(dados, str) else dados.get("id")
    print(f"   Ocorrencia aberta: id={ocorrencia_id}\n")

    # 4. Login como saude.labrea
    print(f"4. Fazendo login como {email_saude}...")
    resultado = login(url, anon_key, email_saude, contas[email_saude])
    if not resultado:
        return
    token_saude, _ = resultado
    print("   Login OK.\n")

    # 5. Tentar mudar a situacao como saude.labrea (nao e responsavel)
    print("5. Tentando mudar situacao da ocorrencia como saude.labrea...")
    resp = rpc(
        url, anon_key, token_saude, "cidc_ocorrencia_atualizar",
        {
            "p_ocorrencia": ocorrencia_id,
            "p_status": "atribuida",
            "p_texto": "Tentativa indevida de saude",
        },
    )
    print(f"   HTTP {resp.status_code}")
    print(f"   Resposta: {resp.text[:300]}")

    if resp.status_code >= 400:
        print("\n>>> RESULTADO: A tentativa foi RECUSADA. Tarefa A2 concluida com sucesso! <<<")
    else:
        print("\n>>> ATENCAO: a tentativa NAO foi recusada. Verifique as permissoes. <<<")


if __name__ == "__main__":
    main()
