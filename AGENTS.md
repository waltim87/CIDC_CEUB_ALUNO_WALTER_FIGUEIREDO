# AGENTS.md — regras para agentes de IA neste repositório (OpenCode, Claude Code, Copilot…)

Projeto **CIDC — Centro de Inteligência da Defesa Civil**: protótipo de Defesa Civil para os
municípios do Amazonas, com PN-PDC 2025-2035 e os 5 eixos da Lei 12.608/2012. A stack é
Streamlit (app), Supabase (Postgres, PostGIS, Auth, RLS e Storage) e GitHub Actions (coletas e
robôs).

- **Contexto completo e estado atual:** [docs/CONTINUAR_EM_OUTRA_IA.md](docs/CONTINUAR_EM_OUTRA_IA.md).
- **Tarefas atribuídas:** [docs/TAREFAS.md](docs/TAREFAS.md). Faça uma por vez, na ordem, e
  marque `[x]` quando terminar.

## Usuário
- Walter: fala português e **não é técnico**. Responda em português simples, com passos curtos e
  numerados.
- Ele aplica SQL **à mão** no SQL Editor do Supabase. Quando for preciso:
  - copie o SQL para a área de transferência (`Set-Clipboard` no PowerShell);
  - confira o início do texto copiado;
  - abra a página do editor;
  - diga onde colar e em qual botão clicar.
- Depois de push grande, peça **Reboot app** no Streamlit Cloud. Sem isso, aparece ImportError
  de módulo antigo.
- Commit e push direto na `main` estão autorizados. Mensagens em português, explicando o porquê.

## Regras invioláveis
1. **Segredos:**
   - Nunca peça nem mostre token, senha ou chave, nem no chat nem em log.
   - `SUPABASE_SERVICE_ROLE_KEY` existe **só** nos secrets do GitHub Actions, nunca no Streamlit.
   - O `.env` local é lido só pelo código.
   - A senha das contas de teste fica em `Documentos\CIDC_contas_teste.txt` do usuário: leia
     pelo código, nunca exiba.
2. **Não inventar dados:**
   - Só fontes abertas oficiais (ANA, IBGE, CNES, INMET, Open-Meteo, INPE, Cemaden, SGB/SACE).
   - Dado de teste é fictício e marcado `[TESTE]`. Ele **fica no banco** até o usuário pedir
     "zera os testes".
3. **Decisão humana:** robô e IA só criam **rascunho** de alerta. Quem aprova é uma pessoa.
4. **LGPD:**
   - CPF, nomes e fotos de famílias abrigadas só para coordenação municipal, saúde/assistência
     do município, coordenador do abrigo e administrador. Voluntário não vê.
   - CPF sempre mascarado em relatório.
   - Telegram só por adesão (opt-in).
5. **Custo zero:** apenas camadas gratuitas.
6. **Permissão é do banco:**
   - RLS mais funções `security definer` (`cidc_*`). O app só esconde botões.
   - Toda checagem em plpgsql usa `coalesce(..., false)`: `if not NULL` não barra, e já houve
     bug por isso.
7. **Não reative o projeto antigo no Cloudflare:** está pausado a pedido do usuário.

## Comandos
- **Python:** `./.venv/Scripts/python.exe` (Windows, Python 3.14).
- **Testes:** `./.venv/Scripts/python.exe -m unittest discover -s tests`. Todos devem passar
  antes de cada commit.
- **Tela:** teste com `streamlit.testing.v1.AppTest`, um cliente Supabase falso e vários perfis
  (sem exceção na tela).
- **Permissões:** depois de a migration ser aplicada, teste pelo REST do Supabase com as contas
  `@cidc-teste.example`. O login é `/auth/v1/token?grant_type=password` com a anon key do `.env`.
- **Git Bash no Windows:** heredoc com aspas costuma quebrar. Escreva scripts de edição em
  arquivo.

## Padrões do código
- **Migration nova:**
  - `db/migrations/AAAAMMDDNNNN_nome.sql`, e a próxima é `202610140017_...`;
  - idempotente (`if not exists`, `drop policy if exists`), com RLS ligada e `grant` explícito;
  - funções com `set search_path = pg_catalog, public, pg_temp`;
  - `revoke` das funções internas `from public, authenticated, anon`.
- **Página nova:**
  - registrar em `app/Home.py` conforme o perfil;
  - incluir `painel_relatorio(...)` de `app/relatorio_menu.py`, que gera PDF e CSV;
  - datas no horário de Manaus (UTC−4);
  - texto digitado por usuário exibido com `app.chat.texto_seguro`.
- **Cache:**
  - tabela pública: `st.cache_data` com `_cliente`;
  - tabela com RLS: inclua `app.comum.chave_usuario()` na chave;
  - nunca guarde em cache o que o usuário acabou de cadastrar.
- **PDF:** fpdf2 com fonte Latin-1. Use `core.relatorios._latin1`, que converte símbolos e
  remove emoji.
