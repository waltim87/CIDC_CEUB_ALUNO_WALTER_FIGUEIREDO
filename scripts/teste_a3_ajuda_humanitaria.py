"""Teste A3: ajuda humanitária - estoque e entregas.

Testa pelo REST, com as contas de teste:
- entrada de 50 cestas como logistica.labrea, com observação [TESTE];
- entrega de 1 cesta a uma família [TESTE];
- repetir sem justificativa: deve dar erro REPETIDA;
- entregar mais do que o saldo: deve dar erro;
- voluntario1 tentando entregar: deve ser bloqueado;
- conferir a view ajuda_cobertura_familias.

Le configuracoes do .env e senhas de OneDrive\Documentos\CIDC_contas_teste.txt.
Rode com: .\.venv\Scripts\python.exe scripts\teste_a3_ajuda_humanitaria.py
"""

from __future__ import annotations

from pathlib import Path

import requests


def carregar_env(caminho: Path) -> dict[str, str]:
    """Lê variaveis KEY=valor de um arquivo .env."""
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
    """Lê emails e senha comum do arquivo de contas de teste."""
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
    """Login Supabase Auth. Retorna (access_token, user_id)."""
    resp = requests.post(
        f"{url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": senha},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  ERRO no login de {email}: HTTP {resp.status_code} - {resp.text[:200]}")
        return None
    dados = resp.json()
    token = dados.get("access_token")
    user = dados.get("user", {}) if isinstance(dados.get("user"), dict) else {}
    user_id = user.get("id")
    if not token or not user_id:
        print(f"  ERRO: login de {email} nao retornou token ou id")
        return None
    return token, user_id


def rest_get(url: str, anon_key: str, token: str, tabela: str, params: dict) -> requests.Response:
    return requests.get(
        f"{url}/rest/v1/{tabela}",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )


def rest_post(url: str, anon_key: str, token: str, tabela: str, dados: dict) -> requests.Response:
    return requests.post(
        f"{url}/rest/v1/{tabela}",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json=dados,
        timeout=30,
    )


def rpc(url: str, anon_key: str, token: str, funcao: str, parametros: dict) -> requests.Response:
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
        print("ERRO: SUPABASE_URL ou SUPABASE_ANON_KEY nao encontrados no .env")
        return

    contas_caminho = Path.home() / "OneDrive" / "Documentos" / "CIDC_contas_teste.txt"
    if not contas_caminho.exists():
        contas_caminho = Path.home() / "Documentos" / "CIDC_contas_teste.txt"
    contas = ler_contas_teste(contas_caminho)
    if not contas:
        print(f"ERRO: nao li contas de {contas_caminho}")
        return

    emails_necessarios = [
        "coordenacao.labrea@cidc-teste.example",
        "logistica.labrea@cidc-teste.example",
        "voluntario1@cidc-teste.example",
    ]
    faltando = [e for e in emails_necessarios if e not in contas]
    if faltando:
        print(f"ERRO: contas nao encontradas no arquivo: {faltando}")
        return

    print("=== TESTE A3: ajuda humanitária ===\n")

    # ------------------------------------------------- 1. coordenacao.labrea cria abrigo e família
    print("1. Login como coordenacao.labrea (cria abrigo e família de teste)...")
    r = login(url, anon_key, emails_necessarios[0], contas[emails_necessarios[0]])
    if not r:
        return
    token_coord, user_id_coord = r
    print("   Login OK.\n")

    print("2. Consultando município do coordenador...")
    resp = rest_get(url, anon_key, token_coord, "usuarios", {
        "auth_id": f"eq.{user_id_coord}",
        "select": "id,municipio_id,nome,perfil",
    })
    if resp.status_code != 200 or not resp.json():
        print(f"   ERRO ao consultar usuario: HTTP {resp.status_code} - {resp.text[:200]}")
        return
    usuario = resp.json()[0]
    municipio_id = usuario["municipio_id"]
    print(f"   Municipio: {municipio_id} - {usuario['nome']} ({usuario['perfil']})\n")

    print("3. Criando abrigo de teste [TESTE]...")
    resp = rest_post(url, anon_key, token_coord, "abrigos", {
        "municipio_id": municipio_id,
        "nome": "[TESTE] Abrigo A2/A3",
        "capacidade": 50,
        "ocupacao": 0,
    })
    if resp.status_code not in (200, 201):
        print(f"   ERRO ao criar abrigo: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    abrigo_id = resp.json()[0]["id"]
    print(f"   Abrigo criado: id={abrigo_id}\n")

    print("4. Criando família de teste [TESTE]...")
    resp = rest_post(url, anon_key, token_coord, "familias_abrigadas", {
        "abrigo_id": abrigo_id,
        "municipio_id": municipio_id,
        "responsavel_nome": "Familia Teste A3",
        "responsavel_cpf": "11122233344",
        "situacao_imovel": "alagado",
        "observacoes": "[TESTE] família criada para teste A3",
        "consentimento_lgpd": True,
    })
    if resp.status_code not in (200, 201):
        print(f"   ERRO ao criar família: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    familia_id = resp.json()[0]["id"]
    print(f"   Familia criada: id={familia_id}\n")

    # ------------------------------------------------- 2. logistica.labrea faz entrada de 50 cestas
    print("5. Login como logistica.labrea...")
    r = login(url, anon_key, emails_necessarios[1], contas[emails_necessarios[1]])
    if not r:
        return
    token_log, _ = r
    print("   Login OK.\n")

    print("6. Entrada de 50 cestas basicas no estoque [TESTE]...")
    resp = rpc(url, anon_key, token_log, "cidc_estoque_movimentar", {
        "p_municipio_id": municipio_id,
        "p_item": "cesta_basica",
        "p_quantidade": 50,
        "p_motivo": "doacao",
        "p_observacao": "[TESTE] entrada para teste A3",
    })
    if resp.status_code not in (200, 201):
        print(f"   ERRO na entrada: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    print("   Entrada de 50 cestas OK.\n")

    print("7. Verificando saldo de cestas_basica...")
    resp = rpc(url, anon_key, token_log, "cidc_saldo_item", {
        "p_municipio_id": municipio_id,
        "p_item": "cesta_basica",
    })
    saldo = resp.json()
    print(f"   Saldo atual: {saldo}\n")

    # ------------------------------------------------- 3. Entrega de 1 cesta para a família
    print("8. Entrega de 1 cesta basica para a família [TESTE]...")
    resp = rpc(url, anon_key, token_log, "cidc_ajuda_entregar", {
        "p_municipio_id": municipio_id,
        "p_itens": {"cesta_basica": 1},
        "p_familia_id": familia_id,
        "p_pessoas": 3,
        "p_observacao": "[TESTE] primeira entrega",
    })
    if resp.status_code not in (200, 201):
        print(f"   ERRO na entrega: HTTP {resp.status_code} - {resp.text[:300]}")
        return
    print("   Entrega de 1 cesta OK.\n")

    print("9. Tentando repetir a entrega SEM justificativa (deve dar REPETIDA)...")
    resp = rpc(url, anon_key, token_log, "cidc_ajuda_entregar", {
        "p_municipio_id": municipio_id,
        "p_itens": {"cesta_basica": 1},
        "p_familia_id": familia_id,
        "p_pessoas": 3,
    })
    print(f"   HTTP {resp.status_code}")
    print(f"   Resposta: {resp.text[:300]}")
    if resp.status_code >= 400 and "REPETIDA" in resp.text:
        print("   >>> CORRETO: repetição sem justificativa foi barrada com REPETIDA <<<\n")
    else:
        print("   >>> ATENÇÃO: repetição não foi barrada <<<\n")

    print("10. Tentando entregar 60 cestas (mais que o saldo) - deve dar erro...")
    resp = rpc(url, anon_key, token_log, "cidc_ajuda_entregar", {
        "p_municipio_id": municipio_id,
        "p_itens": {"cesta_basica": 60},
        "p_familia_id": familia_id,
        "p_justificativa": "teste de saldo insuficiente",
        "p_observacao": "[TESTE] tentativa acima do saldo",
    })
    print(f"   HTTP {resp.status_code}")
    print(f"   Resposta: {resp.text[:300]}")
    if resp.status_code >= 400 and ("Saldo insuficiente" in resp.text or "saldo" in resp.text.lower()):
        print("   >>> CORRETO: entrega acima do saldo foi barrada <<<\n")
    else:
        print("   >>> ATENÇÃO: entrega acima do saldo não foi barrada <<<\n")

    # ------------------------------------------------- 4. voluntario1 tentando entregar -> bloqueado
    print("11. Login como voluntario1 (tentativa de entrega deve ser bloqueada)...")
    r = login(url, anon_key, emails_necessarios[2], contas[emails_necessarios[2]])
    if not r:
        return
    token_vol, _ = r
    print("   Login OK.\n")

    print("12. Tentando entrega como voluntario1 (deve ser bloqueado)...")
    resp = rpc(url, anon_key, token_vol, "cidc_ajuda_entregar", {
        "p_municipio_id": municipio_id,
        "p_itens": {"cesta_basica": 1},
        "p_familia_id": familia_id,
        "p_observacao": "[TESTE] tentativa de voluntario",
    })
    print(f"   HTTP {resp.status_code}")
    print(f"   Resposta: {resp.text[:300]}")
    if resp.status_code >= 400:
        print("   >>> CORRETO: voluntario foi bloqueado <<<\n")
    else:
        print("   >>> ATENÇÃO: voluntario conseguiu entregar <<<\n")

    # ------------------------------------------------- 5. Conferir view ajuda_cobertura_familias
    print("13. Consultando view ajuda_cobertura_familias...")
    resp = rest_get(url, anon_key, token_log, "ajuda_cobertura_familias", {
        "municipio_id": f"eq.{municipio_id}",
        "select": "*",
    })
    if resp.status_code != 200:
        print(f"   ERRO ao consultar view: HTTP {resp.status_code} - {resp.text[:200]}")
    else:
        rows = resp.json()
        print(f"   Linhas retornadas: {len(rows)}")
        for row in rows:
            if row.get("familia_id") == familia_id:
                print(f"   Familia [TESTE]: ultima_cesta={row.get('ultima_cesta')}, "
                      f"ultima_entrega={row.get('ultima_entrega')}, entregas={row.get('entregas')}")
        print("   View consultada com sucesso.\n")

    print("=== TESTE A3 CONCLUÍDO ===")
    print("Verifique acima se todos os casos deram o resultado esperado.")
    print("Se algo falhou, uma migration nova pode ser necessária.")


if __name__ == "__main__":
    main()
