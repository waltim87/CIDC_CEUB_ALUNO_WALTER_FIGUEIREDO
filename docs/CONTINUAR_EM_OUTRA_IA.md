# Comando para continuar o CIDC em outra IA

Copie tudo abaixo da linha e cole como primeira mensagem na outra IA (de preferência uma que
consiga ler arquivos e rodar comandos, como Claude Code, Cursor ou Copilot no VS Code, aberta na
pasta do projeto).

---

Você vai continuar o desenvolvimento do **CIDC — Centro de Inteligência da Defesa Civil**, um
protótipo SaaS de Defesa Civil para municípios do Amazonas, alinhado ao PN-PDC 2025-2035 e aos
5 eixos da Lei 12.608/2012: prevenção, mitigação, preparação, resposta e recuperação. Leia este
comando inteiro antes de agir.

## Quem é o usuário
- Walter, estudante do CEUB. Fala português e **não é técnico**. Responda sempre em português
  simples, com passos curtos e numerados.
- Quando ele precisar fazer algo no Supabase, no GitHub ou no Streamlit, **abra a página para
  ele** e **copie o SQL para a área de transferência**. Depois diga exatamente onde colar e em
  que botão clicar. Confira o conteúdo da área de transferência antes de pedir para colar: já
  aconteceu de ele colar o arquivo de senhas no lugar do SQL.
- Ele autorizou commit e push direto na branch `main`.

## Onde está tudo
- **Pasta local:** `C:\Users\walte\source\CIDC_CEUB_ALUNO_WALTER_FIGUEIREDO`, no Windows. Use o
  Python do ambiente `.venv` (Python 3.14): `./.venv/Scripts/python.exe`.
- **GitHub:** `waltim87/CIDC_CEUB_ALUNO_WALTER_FIGUEIREDO`. O repositório é **público**.
- **Site (Streamlit Community Cloud):** https://sistematizacao-defesa-civil-walter-ceub-eng-ia.streamlit.app
- **Banco:** Supabase (Postgres + PostGIS + Auth + Storage). As migrations são aplicadas **à mão**
  pelo usuário no SQL Editor (não existe CLI configurada).
- **Automação (GitHub Actions):**
  - `coleta.yml`: coleta das fontes + robô de risco a cada 3 h.
  - `telegram.yml`: inscrições e alertas aprovados, a cada 15 min.
  - `acordar.yml`: abre o site a cada 4 h com Playwright e clica em "acordar", porque o plano
    gratuito põe o app para dormir.
- Existe também um projeto antigo no Cloudflare. Ele está **pausado a pedido do usuário**. Não
  reative.

## Regras que não podem ser quebradas
1. **Segredos:**
   - Nunca peça token, senha ou chave no chat, e nunca os imprima em logs.
   - A `SUPABASE_SERVICE_ROLE_KEY` existe **só** nos secrets do GitHub Actions. Ela nunca vai
     para o Streamlit, cujos secrets são `SUPABASE_URL`, `SUPABASE_ANON_KEY` e
     `TELEGRAM_BOT_TOKEN`.
   - O `.env` local tem as chaves. Leia o arquivo só pelo código, sem mostrar os valores.
2. **Não inventar dados:**
   - Os dados vêm de fontes abertas oficiais: ANA, IBGE, CNES/DATASUS, INMET, Open-Meteo,
     INPE, Cemaden e SGB/SACE.
   - A IA (Gemini, camada gratuita) só redige texto, e o texto é rejeitado se citar números
     que não estão nos fatos.
   - Dado de teste é fictício e sempre marcado com `[TESTE]`.
3. **Decisão humana:** o robô só cria **rascunho** de alerta. Quem aprova é sempre uma pessoa.
   A aprovação dispara o Plano de Contingência e o envio pelo Telegram.
4. **LGPD:**
   - CPF, nomes completos e fotos das famílias abrigadas só podem ser vistos por: coordenação
     municipal, saúde/assistência do município, coordenador do abrigo e administrador.
     **Voluntários não veem.**
   - O CPF sai mascarado nos relatórios e é mascarado no chat.
   - O Telegram funciona só por adesão (opt-in). Não há banco de dados pessoais de terceiros.
5. **Custo zero:** use só camadas gratuitas.
6. **Permissões no banco:**
   - Toda regra de acesso fica no Postgres: RLS mais funções `security definer` (padrão
     `cidc_*`). O app só esconde botões; quem barra é o banco.
   - Escrita sensível passa por RPC que confere a permissão e grava o histórico.
7. **Lição aprendida (bug real):** em plpgsql, comparar com NULL dá NULL, e `if not NULL` **não
   barra**. Sempre use `coalesce(..., false)` em checagens de permissão. As funções
   `cidc_pode_*` foram corrigidas para devolver sempre true ou false (migration 0015).

## Estrutura do código
- `collectors/`: coletores (`ana.py`, `cnes.py`, `inmet.py`, `inpe.py`, `cemaden.py`, `sgb.py`,
  `marcadores.py`, `comum.py`, `saude.py`).
- `core/`:
  - `robo.py`: risco por município e rascunho de alerta;
  - `llm.py`: Gemini;
  - `relatorios.py`: PDF com fpdf2 e CSV. A fonte é Latin-1, e `_latin1` converte símbolos e
    remove emoji;
  - `relatorio_robo.py`, `telegram_robo.py`, `cpf.py`, `notificacoes.py`, `alertas.py`.
- `app/` (Streamlit; a entrada é `app/Home.py`, com navegação por perfil):
  - `auth.py`: login por e-mail/senha e **Google (OAuth PKCE)**, mais a tela "Complete seus
    dados";
  - `comum.py`: cache, `exigir_perfil`, `carregar_municipios`;
  - `paineis.py`: painéis principais;
  - `cadastros.py`, `visual.py`, `relatorio_menu.py`: `painel_relatorio` gera PDF e CSV em
    todo menu;
  - `voluntarios.py`: autocadastro, termo e relatos tipo Waze;
  - `meteorologia.py`, `familias.py`, `permissoes.py`, `chat.py`;
  - `plano.py`: Plano de Contingência e "Minhas tarefas";
  - `ocorrencias.py`, `ajuda.py`.
- `config/`: `fontes.yaml`, `robo.yaml` (limites do robô), `regras.yaml`.
- `db/migrations/`: arquivos `AAAAMMDDNNNN_nome.sql`, em ordem.
- `db/testes/`: dados de teste e scripts de limpeza.
- `tests/`: testes unitários. Rode com `./.venv/Scripts/python.exe -m unittest discover -s tests`.
  Hoje são 139 testes, todos passando.
- `scripts/`: utilitários, como `acordar_site.py`.

## Perfis
`administrador`, `gestor_nacional`, `gestor_estadual`, `coordenador_municipal`,
`operador_monitoramento`, `agente_campo`, `saude_assistencia`, `logistica_abastecimento`,
`voluntario` (lê quase tudo e não aprova alertas) e `pesquisador`.

"Coordenador de abrigo" não é um perfil: é uma designação na tabela `abrigo_responsaveis`.

## O que já está pronto
- **Coleta e robô:**
  - Coleta automática de 7 fontes, com saúde das fontes monitorada. O INEP está indisponível.
  - Robô de risco a cada 3 h, com marcadores históricos (cheia e seca recordes da ANA) e
    texto pela IA.
  - Rascunho de alerta, aprovação humana e envio pelo Telegram (`@cidc_walter_teste_bot`).
- **Painéis e cadastros:**
  - Painéis por perfil, com mapa, gráficos e relatório PDF/CSV em todos os menus. Os
    relatórios foram testados visualmente.
  - Cadastros ampliados, com unidades de saúde do CNES.
  - Famílias abrigadas, com CPF, parentesco, fotos e desaparecidos (último dia e local em que
    foram vistos), e menu de permissões.
  - Meteorologia (INMET e Open-Meteo), queimadas (INPE), Cemaden e SACE.
- **Pessoas e comunicação:**
  - Voluntários com termo de responsabilidade e relatos de campo confirmados pela comunidade.
  - Login com Google e tela "Complete seus dados".
  - **Chat interno**: canal do município, canais entre comunidades e conversas privadas.
- **Ações dos 5 eixos:**
  - **Plano de Contingência**: protocolo por nível × ameaça, com modelo de 20 ações. Alerta
    aprovado aciona o plano e cria tarefas com prazo e função. Página "Minhas tarefas".
  - **Ocorrências com atendimento**: o relato vira caso. Fluxo: aberta → equipe → a caminho →
    em atendimento → resolvida, com linha do tempo.
  - **Ajuda humanitária**: estoque por movimentos, entregas a famílias, comunidades e abrigos
    com baixa automática, saldo nunca negativo e justificativa para repetir item em menos de 7
    dias. Lista de "famílias sem cesta".
- **Desempenho:** o cliente e o perfil ficam guardados na sessão. Dados de coleta ficam em
  cache de 10 min (por usuário quando há RLS). Há o botão "Atualizar dados".

## Migrations
- **Aplicadas:** 0001 a 0014.
- **Pendentes** (o usuário vai colar no SQL Editor):
  - `202610140015_corrige_permissao_ocorrencia.sql`;
  - `202610140016_ajuda_humanitaria.sql`.

## Tarefas imediatas, nesta ordem
1. Confirmar com o usuário que as migrations 0015 e 0016 rodaram. Se não rodaram, copie as
   duas juntas para a área de transferência, confira o início do texto e abra o SQL Editor.
2. Lembrar o usuário de **apagar no SQL Editor a aba em que ele colou, por engano, o arquivo de
   senhas das contas de teste**.
3. Pedir **Reboot app** no Streamlit depois de cada push grande. Sem isso, aparece ImportError
   de módulo antigo.
4. Testar pelo REST, com as contas de teste:
   - **Ocorrências:** a saúde **não pode** mudar a situação de uma ocorrência sem responsável.
     Antes de 0015, ela conseguia.
   - **Ajuda humanitária:** entrada no estoque; entrega a uma família `[TESTE]`; repetir o item
     sem justificativa (deve dar erro "REPETIDA"); entregar mais do que o saldo (deve dar erro);
     voluntário tentando entregar (deve ser bloqueado).
5. Pedir ao usuário para rodar uma vez a rotina "Manter o painel acordado" (Actions → Run
   workflow) e confirmar ✅.
6. Login com Google:
   - o provedor está ativo no Supabase;
   - o erro anterior era `redirect_uri_mismatch` no Google Cloud;
   - o URI correto é `https://<ref-do-projeto>.supabase.co/auth/v1/callback`;
   - **confirme se o usuário corrigiu e se o login funciona.**
7. Ainda não testado: o acionamento automático do plano **ao aprovar um alerta**. Aprovar um
   alerta real envia Telegram para os inscritos, então combine com o usuário antes.

## Contas de teste
- 10 contas `@cidc-teste.example`:
  - coordenacao.labrea, monitoramento.labrea, campo.labrea (coordena um abrigo de teste),
    saude.labrea, logistica.labrea;
  - coordenacao.boca, estadual.am, pesquisa, voluntario1, voluntario2.
- A senha está **só** no arquivo `Documentos\CIDC_contas_teste.txt` do usuário. Leia pelo
  código; nunca mostre nem peça a senha.
- **Dados de teste ficam no banco até o usuário pedir "zera os testes".** Então rode:
  - `db/testes/limpar_dados_teste.sql`: abrigos, famílias, relatos, chat, acionamentos;
  - `db/testes/limpar_usuarios_teste.sql`: as contas.

## Próximas funcionalidades (ideias aprovadas, ainda não feitas)
- **Prevenção:**
  - cadastro de **áreas de risco por comunidade** (tipo, casas, pessoas, nível, foto), usando a
    setorização do SGB como ponto de partida;
  - **calendário anual de risco** com os marcadores históricos ("faltam X dias para o pico da
    cheia");
  - **vistorias preventivas**.
- **Mitigação:** carteira de obras e intervenções (status, valor, fonte do recurso, comunidades
  beneficiadas) e indicador de pessoas retiradas de área de risco.
- **Preparação:** simulados, capacitação e validade dos cursos dos voluntários, e **checklist
  de abrigo pronto**.
- **Resposta:**
  - rastreio de embarcações e equipes;
  - **fichas para o S2iD** (afetados, desalojados, desabrigados e danos) em rascunho PDF;
  - aviso no Telegram para quem recebe uma tarefa ou ocorrência.
- **Recuperação:** retorno das famílias (quem voltou, quem não tem para onde ir, o que falta),
  levantamento de danos e reconstrução, e **relatório de lições aprendidas** do evento, que
  fecha o ciclo.
- **Arrumação:** a tabela antiga `recursos` (aba "Pré-posicionamento" da Logística) convive com
  o novo estoque `ajuda_movimentos`. O ideal é migrar a Logística para o novo estoque.

## Como trabalhar neste projeto
- **Migration nova:**
  - próximo número: `202610140017_...`;
  - use `create ... if not exists`, `drop policy if exists`, RLS ligada e `grant` explícito;
  - funções `security definer set search_path = pg_catalog, public, pg_temp`;
  - `revoke` de funções internas, inclusive `from authenticated, anon`, porque o Supabase
    concede execução por padrão.
- **Página nova:** registre em `app/Home.py` conforme o perfil e inclua `painel_relatorio(...)`.
  Datas são mostradas no horário de Manaus (UTC−4).
- **Textos digitados por usuários** devem ser exibidos com `app.chat.texto_seguro`, sem
  markdown nem links.
- **Cache:**
  - tabela pública: `st.cache_data` com `_cliente`;
  - tabela com RLS: inclua o `chave_usuario()` na chave do cache;
  - nunca guarde em cache o que o usuário acabou de cadastrar.
- **Antes de cada commit:**
  - rode os testes unitários;
  - abra a página com `streamlit.testing.v1.AppTest` e um cliente falso, em vários perfis,
    para pegar erro de tela;
  - depois da migration aplicada, teste as permissões pelo REST com as contas de teste
    (login em `/auth/v1/token?grant_type=password` com a anon key).
- **Mensagens de commit** em português, curtas, explicando o porquê.
- **No Windows/Git Bash**, heredoc com aspas costuma quebrar. Escreva scripts de edição em
  arquivo temporário.

Comece confirmando com o usuário as tarefas imediatas 1 a 7 e depois pergunte qual
funcionalidade da lista ele quer em seguida.
