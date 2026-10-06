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

Preencha `.env` com o Project URL e a chave `service_role` disponíveis nas
configurações do projeto Supabase. Não use a chave `anon` para a gravação pelo
coletor. Não envie esses valores por chat.

### Criar tabelas e dados de referência

No painel do Supabase, abra **SQL Editor** e execute, na ordem:

1. `db/migrations/202610050001_schema_inicial.sql`
2. `db/seeds/202610050001_amazonas.sql`

A migration habilita PostGIS, cria o esquema e liga RLS em todas as tabelas.
Até a Fase 4, não existem políticas para usuários autenticados; o acesso de
gravação pelo coletor usa a chave `service_role` local, que ignora RLS. O seed
inclui os 62 municípios do Amazonas identificados pelo IBGE. As três linhas de
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

Para abrir os painéis localmente, configure `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` apenas em `.env` e rode:

```powershell
streamlit run app/Home.py
```

O painel secundário fica disponível no menu multipágina **Revisão de alertas**.
Na Streamlit Community Cloud, cadastre os mesmos nomes em **App settings >
Secrets**. A chave `service_role` dá acesso administrativo e ignora RLS; até a
Fase 4 implementar login e políticas por perfil/município, mantenha os painéis
privados e não publique esse app.

Teste do cálculo do índice, regras e geração de rascunhos (sem envio):

```powershell
python -m unittest discover -s tests -v
```
