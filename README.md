# Centro de Inteligência da Defesa Civil

Plataforma Integrada de Triagem e Resiliência — protótipo do desafio PN-PDC
2025–2035.

> **Protótipo, sem validação oficial; confirme nos órgãos oficiais.**

## Fase 1 — banco inicial e coletor ANA

### Contas e segredos

- GitHub: repositório público do projeto.
- Supabase: projeto no plano Free, região South America (São Paulo).
- A ANA HidroWebService pode exigir cadastro e credenciais. Confirme o acesso,
  o endpoint, o método de autenticação e os campos no manual oficial antes de
  ativar o coletor. Consulte `config/fontes.yaml`; valores ainda não confirmados
  estão marcados como `CONFIRMAR`.
- Nunca publique `SUPABASE_SERVICE_ROLE_KEY`, a senha do banco ou credenciais ANA.
  Copie `.env.example` para `.env` e preencha os valores apenas localmente. `.env`
  é ignorado pelo Git.

### Preparar o ambiente local (Windows / PowerShell)

```powershell
Set-Location 'C:\Users\walte\source\CIDC_CEUB_ALUNO_WALTER_FIGUEIREDO'
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Para o coletor local, preencha `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` em `.env`; essa chave administrativa nunca deve ir
para o Streamlit ou para o GitHub. Para abrir o painel, preencha
`SUPABASE_ANON_KEY`, que respeita as políticas RLS, e entre com uma conta Auth.
Não envie esses valores por chat.

### Criar tabelas e dados de referência

No painel do Supabase, abra **SQL Editor** e execute, na ordem:

1. `db/migrations/202610050001_schema_inicial.sql`
2. `db/seeds/202610050001_amazonas.sql`

A migration habilita PostGIS, cria o esquema e liga RLS em todas as tabelas. As
políticas por perfil e município são adicionadas pela migration da Fase 4; até
aplicá-la no projeto remoto, não publique o Streamlit. O coletor local usa a
chave `service_role`, que ignora RLS. O seed inclui os 62 municípios do Amazonas
identificados pelo IBGE. As três linhas de
estação do Purus são **marcadores pendentes**, com código oficial nulo; não são
estações reais confirmadas e não geram leituras.

### Ativar a coleta ANA depois da confirmação oficial

1. Consulte o manual/API no endereço oficial registrado em `fontes.yaml` e
   solicite acesso à ANA pelos canais ali indicados.
2. Confirme de 3 a 5 estações da bacia do Purus no sistema oficial Hidro-Telemetria.
3. Atualize no YAML endpoint, autenticação, parâmetros, caminho/campos da resposta,
   códigos oficiais, nomes e municípios. Troque `status: CONFIRMAR` por
   `status: ativo` somente após validar tudo.
4. Coloque as credenciais exigidas em `.env` e execute:

```powershell
python -m collectors.ana
```

O coletor preserva `data_hora_leitura` da fonte, grava `coletado_em` em UTC e
faz upsert por estação e instante. Erros de uma estação são registrados sem
interromper as demais. A coleta e a gravação ficam bloqueadas enquanto os dados
oficiais estiverem pendentes.

### Testes da Fase 1

```powershell
python -m unittest discover -s tests -v
```

Os testes usam respostas simuladas e não fazem chamadas à ANA ou ao Supabase.
Validação manual do banco: depois de executar migration e seed no SQL Editor,
confira que há 62 linhas em `municipios`, 3 marcadores sem `codigo_oficial` em
`estacoes` e nenhuma linha de leitura fictícia em `leituras`.

## Escopo ainda não ativado

Esta entrega não insere leituras reais: os manuais, credenciais de acesso à ANA
e identificação oficial das estações precisam ser confirmados. A integração não
inventa endpoint, formato de resposta, códigos ou valores. Os demais coletores,
índice, painéis, perfis, notificações e API pública são implementados por fases.

## Fase 2 — demais fontes e saúde das coletas

Os módulos por fonte ficam em `collectors/` e expõem `coletar()`. O coletor do
IBGE usa a API de Localidades oficial para listar os municípios do Amazonas; os
outros seis adaptadores (INPE, INMET, SGB/SACE, Cemaden, CNES e INEP) só consultam
uma fonte quando endpoint, formato e campos forem confirmados em seus materiais
oficiais e substituídos no `config/fontes.yaml`. Enquanto isso, permanecem
bloqueados para evitar tráfego a endereços ou formatos presumidos.

Os adaptadores compartilham normalização de registros JSON/CSV e metadados de
fonte/horário de coleta em `collectors/comum.py`. `collectors/saude.py` tenta
cada fonte isoladamente, registra falhas e permite atualizar `status`,
`ultima_verificacao`, `ultimo_erro` e `ultima_coleta` no Supabase, sem apagar o
horário da última coleta bem-sucedida quando a fonte falha.

Para instalar a migration de saúde das fontes no projeto Supabase, execute no
SQL Editor:

1. `db/migrations/202610050002_saude_fontes.sql`
2. Execute novamente `db/seeds/202610050001_amazonas.sql` para registrar as fontes
   desta fase.

Verificação local com respostas simuladas:

```powershell
python -m unittest discover -s tests -v
python -m collectors.saude
```

O segundo comando consulta o endpoint público confirmado do IBGE e reporta como
pendentes as demais fontes até que sua configuração oficial seja completada.
Para persistir os municípios coletados pelo IBGE, use
`collectors.ibge.coletar()` e depois `collectors.ibge.persistir(registros)`.

## Fase 3 — índice, regras e painéis

Instale as dependências e aplique no SQL Editor do Supabase, nesta ordem:

1. `db/migrations/202610050003_indice_alertas.sql`
2. `db/seeds/202610050003_regras_iniciais.sql`

Os pesos vêm de `config/pesos.yaml` e da tabela `configuracao_pesos`; qualquer
alteração deve preservar a soma de 100. Os valores atuais são uma hipótese
inicial não validada oficialmente. Componentes sem valor são omitidos e seus
pesos são renormalizados entre os componentes disponíveis. Sem nenhum
componente observável, o índice é indisponível — nunca presumido como zero.

As regras de `config/regras.yaml` e os seeds SQL começam inativos para impedir
alertas operacionais baseados em limiares hipotéticos. Um responsável precisa
revisar e ativar regras no Supabase. O motor apenas registra rascunhos; não envia
alertas por Telegram ou e-mail nesta fase.

O ponto de integração `core.motor.calcular_e_gerar_rascunhos(...)` exige, para
cada fonte usada no índice, nome e `data_hora_leitura` com fuso horário. Esses
dados ficam no índice e acompanham o alerta para que valores e sugestões tenham
proveniência visível.

O processo coletor/backend pode usar `SUPABASE_SERVICE_ROLE_KEY` apenas no
ambiente local confiável (nunca no Streamlit Cloud). Os painéis usam somente
`SUPABASE_ANON_KEY`, autenticação de usuário e as políticas RLS da Fase 4.

Para abrir os painéis localmente, configure `SUPABASE_URL` e
`SUPABASE_ANON_KEY` em `.env` e rode:

```powershell
streamlit run app/Home.py
```

O painel secundário fica disponível no menu multipágina **Revisão de alertas**.
Na Streamlit Community Cloud, cadastre `SUPABASE_URL` e `SUPABASE_ANON_KEY` em
**App settings > Secrets**. Nunca configure `SUPABASE_SERVICE_ROLE_KEY` no app.

Teste do cálculo do índice, regras e geração de rascunhos (sem envio):

```powershell
python -m unittest discover -s tests -v
```

## Fase 4 — autenticação, escopo municipal e notificações

Antes de abrir a aplicação a usuários, aplique a migration
`db/migrations/202610050004_perfis_rls_assinaturas.sql` no SQL Editor do Supabase,
depois de executar as migrations das Fases 1 a 3. Revise o SQL e valide RLS em um
projeto de teste antes da implantação. Esta migration ainda não foi aplicada
automaticamente ao projeto remoto.

Crie usuários em **Supabase Dashboard > Authentication > Users** e associe cada
UUID de Auth a um perfil CIDC em `public.usuarios`. Exemplo para adaptar no SQL
Editor com valores confirmados pelo administrador:

```sql
insert into public.usuarios (nome, perfil, municipio_id, auth_id)
values ('NOME CONFIRMADO', 'coordenador_municipal', 'CODIGO_IBGE', 'UUID_AUTH');
```

Perfis aceitos: `gestor_nacional`, `gestor_estadual`,
`coordenador_municipal`, `operador_monitoramento`, `agente_campo`,
`saude_assistencia`, `logistica_abastecimento`, `pesquisador` e
`administrador`. Associe um código IBGE municipal aos perfis locais. Para
`gestor_estadual`, o município associado identifica a UF e as políticas limitam
o acesso aos municípios daquele estado. `gestor_nacional` e administração têm
escopo municipal global; monitoramento tem leitura global somente para estações,
leituras, índices e revisão de alertas. Pesquisador acessa apenas os dados
públicos disponibilizados sem login. O login usa senha do Supabase Auth; não
compartilhe credenciais pelo chat.

Para habilitar canais de notificação, configure somente os canais que tiver
credenciais gratuitas disponíveis:

- Telegram: `TELEGRAM_BOT_TOKEN` em **App settings > Secrets** (ou no ambiente
  local). O bot deve ter autorização para enviar ao destinatário cadastrado.
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` e, opcionalmente,
  `SMTP_FROM`. Use servidor e conta autorizados; não há provedor pago incluído.

O painel permite cadastrar contatos inativos. A coordenação/logística deve
verificar consentimento e controle do e-mail/conta antes de ativar a assinatura.
Somente coordenador municipal ou administrador pode disparar mensagens, e apenas
depois da aprovação humana. Falhas são registradas por destino com contato mascarado;
entregas concluídas não são repetidas num reenvio parcial. Sem configuração de
um canal, a entrega falha explicitamente e o alerta permanece aprovado.

Verificação local da Fase 4:

```powershell
python -m unittest discover -s tests -v
```

Os testes unitários simulam os transportes. O envio real por **Telegram** foi
validado manualmente (alerta aprovado, enviado pelo painel e recebido no chat);
o envio por e-mail (SMTP) ainda não foi testado. A migration RLS
precisa também ser verificada no Supabase com contas de perfis distintos: usuário
municipal não deve ler ou alterar outro município, perfil sem associação deve
ser negado, dados públicos devem limitar-se a municípios, situação e alertas
emitidos, e só administradores devem gerenciar perfis/regras/pesos.

Teste de isolamento RLS: cole [db/testes/rls_isolamento.sql](db/testes/rls_isolamento.sql)
no SQL Editor do Supabase e execute. Ele cria usuários fictícios, verifica
isolamento entre municípios, negação ao pesquisador e acesso anônimo restrito,
e termina com um erro proposital (`RELATORIO ...`) que reverte tudo. Resultado
verificado: 44 de 44 verificações OK (recursos, alertas e suas transições,
abrigos, afetados, assinaturas, entregas, escopo estadual por UF, perfis de
campo/operador/pesquisador/administrador e acesso anônimo). Os dois testes
de escopo estadual usam um município fictício de outra UF, desfeito no rollback.

Limitações ainda abertas: a página pública não cadastra assinaturas diretamente;
contatos são registrados pela coordenação, permanecem inativos até verificação
manual de consentimento e controle, e só então podem receber alertas. O
formulário de campo registra contagens e necessidades, mas ainda não captura
fotos/localização nem oferece gravação offline. Esses fluxos exigem validação
operacional antes de uso em campo.

## Fase 5 — eixos, relatórios, API pública e indicador

- **Tarefas por eixo** (prevenção, mitigação, preparação, resposta, recuperação):
  em *Gestão municipal*, vinculadas a um alerta do município (tabela `acoes`, com RLS).
- **Relatórios**: em *Visão estadual/nacional*, botões para baixar o ranking em CSV
  (UTF-8, `;`, protegido contra injeção de fórmulas) e PDF (`core/relatorios.py`).
- **Indicador de resultado** (`core/indicador.py`): média de `emitido_em − data_hora_leitura`
  dos alertas emitidos. Linha de base 30 min, meta 10 min (hipótese, sem validação oficial).
  Só entram alertas com leitura de referência verificável; sem dados, mostra "sem dados".
- **API pública somente leitura** (FastAPI, chave anon; o RLS limita a resposta):

```powershell
python -m uvicorn api.main:app --port 8010
# http://localhost:8010/docs  ·  /saude  /municipios?uf=AM  /alertas  /indicador
```

- Migration `202610060001_indicador_publico.sql`: função que expõe apenas horários de
  alertas já enviados, sem abrir a tabela `indices` ao público. Aplicar no SQL Editor.
- Dependências novas: `fpdf2`, `fastapi`, `uvicorn` (`pip install -r requirements.txt`).
