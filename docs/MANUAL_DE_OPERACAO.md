# CIDC — Manual de Operação

18/10/2026 · Walter Figueiredo · CEUB

> Cópia de preservação do documento online "CIDC — Manual de Operação" (Claude Docs). A versão online é a que se edita; esta fica no repositório para não se perder.

Como operar o Centro de Inteligência da Defesa Civil no dia a dia, num alerta e durante um desastre. Protótipo sem validação oficial: em emergência, ligue 199 (Defesa Civil) ou 193 (Bombeiros).

## 1. Visão geral

O CIDC junta dados oficiais de rios, chuva e queimadas dos municípios do Amazonas, indica o risco de cada município a cada 3 horas e organiza a resposta da Defesa Civil nos 5 eixos: prevenção, mitigação, preparação, resposta e recuperação.

- **Quem decide é sempre uma pessoa.** O robô e a IA só sugerem; nenhum alerta sai sem aprovação.
- **Só dado oficial.** ANA, IBGE, CNES/DATASUS, INMET, Open-Meteo, INPE, Cemaden e SGB/SACE.
- **Sem dado não é risco zero.** Estação sem leitura recente aparece como "Sem dados".
- **Protótipo.** Os limites do robô são hipóteses iniciais, sem validação oficial. O CIDC não substitui os canais oficiais.

Endereço do painel: [sistematizacao-defesa-civil-walter-ceub-eng-ia.streamlit.app](https://sistematizacao-defesa-civil-walter-ceub-eng-ia.streamlit.app)

## 2. Acesso ao sistema

Toda conta nova entra como **voluntário**; o perfil de equipe é liberado pelo administrador.

1. Abra o endereço do painel no navegador (computador ou celular).
2. Na aba **Entrar**, use e-mail e senha ou **Entrar com Google** (abre em nova aba).
3. No primeiro acesso, preencha **Complete seus dados**: nome completo, telefone com DDD, município onde atua, habilidades, e aceite o termo de responsabilidade.
4. Quem é da equipe da Defesa Civil ou da prefeitura pede ao administrador para mudar o perfil em **Usuários e permissões**. A mudança vale em até 5 minutos (ou ao clicar em **🔄 Atualizar dados**).
5. Para sair, use **Sair** na barra lateral.

**Site "dormindo".** No plano gratuito, o painel dorme sem uso. Clique em **Yes, get this app back up!** e aguarde até 1 minuto. Uma rotina automática abre o site a cada 4 horas para evitar isso.

**Voluntário sem conta Google.** Use a aba **Quero ser voluntário**: preencha os dados, crie uma senha de 8 caracteres ou mais e confirme o e-mail.

## 3. Perfis e permissões

Cada perfil só atua no próprio município; quem barra é o banco de dados, não a tela.

| Perfil | Vê | Faz |
| --- | --- | --- |
| Coordenação municipal | Todo o município, inclusive famílias | Aprova alertas, aciona o plano, define responsáveis, designa abrigos, gerencia obras e áreas de risco |
| Monitoramento | Estações, leituras, fontes | Revisa alertas, atualiza tarefas da função |
| Agente de campo | Município | Registro de campo, afetados (S2iD), ocorrências |
| Saúde e assistência | Município, inclusive famílias | Famílias abrigadas, retorno, tarefas e ocorrências de saúde |
| Logística | Município | Estoque e ajuda humanitária, embarcações, abrigos, assinaturas de alerta |
| Gestão estadual | Municípios da UF | Lê e aprova alertas |
| Gestão nacional | Todos os municípios | Lê e aprova alertas |
| Voluntário | Quase todo o painel, sem famílias | Relatos de campo, chat, assume ocorrências; o apoio designado num abrigo vê as famílias daquele abrigo |
| Pesquisador | Dados abertos e metodologia | Exporta dados públicos |
| Administrador | Tudo | Permissões, regras, fontes, migração de estoque |

**Coordenador de abrigo** não é um perfil: é uma designação feita pela coordenação em **Usuários e permissões** (função coordenador ou apoio). Quem é designado cadastra as famílias e atualiza a ocupação daquele abrigo.

## 4. Rotina diária (dias normais)

Uma consulta curta por equipe, de preferência no início do expediente.

| Quem | Onde | O que conferir |
| --- | --- | --- |
| Coordenação | Painel principal, Revisão de alertas, Responsáveis por área | Sinal dos municípios, rascunhos de alerta pendentes, áreas sem titular |
| Monitoramento | Sala de monitoramento, Calendário de risco | Saúde das fontes, estações com "leitura antiga", nível e posição entre seca e cheia recordes |
| Logística | Ajuda humanitária, Embarcações, Abrigo pronto | Saldo do estoque, barcos disponíveis, abrigos com vistoria vencida (mais de 90 dias) |
| Campo e saúde | Minhas tarefas, Ocorrências | Tarefas abertas e atrasadas da função, ocorrências da equipe |
| Voluntários | Relatos de campo, Chat interno | Registrar o que viram e confirmar relatos de outros |

O painel guarda os dados das coletas por até 10 minutos para abrir rápido. Para ver uma coleta que acabou de chegar, clique em **🔄 Atualizar dados** na barra lateral.

## 5. Procedimento de alerta

Quando o robô indica **Alerta** ou **Alto**, ele cria um rascunho; só uma pessoa transforma o rascunho em alerta.

| Sinal | Significado | O que fazer |
| --- | --- | --- |
| Sem dados | Sem leitura recente (mais de 12 h) ou fonte fora | Conferir a fonte e a régua no local; não é risco zero |
| Normal | Nenhuma regra acionada | Rotina normal |
| Atenção | Ex.: rio a 20% da seca ou cheia recorde, variação de 15 cm em 24 h, aviso "Perigo potencial" do INMET | Acompanhar mais de perto; avisar lideranças |
| Alerta | Ex.: a 10% do recorde, 30 cm em 24 h, aviso "Perigo", 100 mm de chuva | Rascunho criado; revisar e decidir |
| Alto | No recorde ou além, 50 cm em 24 h, "Grande perigo", SACE em inundação | Rascunho criado; decidir com urgência |

1. Abra **Revisão de alertas** e leia o rascunho, o sinal e as fontes citadas (estação, horário da leitura, aviso do INMET).
2. Confirme no território: régua do porto, relatos de campo confirmados, contato com lideranças.
3. Ajuste o texto se precisar e clique em **Aprovar** (ou **Rejeitar**, explicando o motivo).
4. Ao aprovar, o alerta vai para quem se inscreveu no Telegram (em até 15 minutos) e o **Plano de contingência** é acionado no nível do alerta.
5. Avise as lideranças no **Chat interno** e acompanhe as tarefas criadas.

O robô não repete o mesmo rascunho para o município em menos de 24 horas.

## 6. Plano de contingência e tarefas

O protocolo diz o que cada equipe faz em cada nível; o acionamento transforma o protocolo em tarefas com prazo e responsável.

**Montar o protocolo (coordenação, uma vez):**

1. Em **Plano de contingência → Protocolo**, clique em **Carregar modelo sugerido** (20 ações para cheia, seca e incêndio).
2. Edite na tabela: nível, ameaça, eixo, ação, função responsável e prazo em horas. Clique em **Salvar protocolo**.
3. Ajuste ao plano oficial do município: o modelo é só um ponto de partida.

**Acionar:**

- **Automático:** ao aprovar um alerta. A ameaça vem do robô: rio subindo = cheia; descendo = seca.
- **Manual:** em **Acionamento**, escolha nível e ameaça, escreva o motivo e clique em **Acionar plano**.
- No nível Alto entram também as ações de Atenção e Alerta ainda não feitas. Acionar de novo não duplica tarefas abertas.

**Executar:**

- Cada tarefa vai ao **titular da área** da função (ver seção 10). A equipe vê as suas em **Minhas tarefas**.
- Atualize a situação (em andamento, concluída, cancelada) com uma observação do que foi feito.
- Tarefas vencidas aparecem como **⚠️ ATRASADA**.
- Quando a situação normalizar, a coordenação clica em **Encerrar este acionamento**.

## 7. Ocorrências e embarcações

Cada chamado vira um caso com prioridade, equipe responsável e linha do tempo até ser resolvido.

**Abrir (equipes do município):** em **Ocorrências → Abrir ocorrência**, escolha o tipo e a prioridade (crítica, alta, média, baixa), descreva, informe o local e as pessoas envolvidas. Para aproveitar um relato de campo, escolha-o no topo do formulário. Voluntários não abrem ocorrências: registram **Relatos de campo**.

**Andamento:**

1. **Aberta** → a coordenação designa a equipe (ou alguém clica em **🙋 Assumir**). Ao designar uma equipe, o caso vai sozinho para o titular daquela área.
2. **Equipe designada** → a equipe clica em **🚤 Saímos / a caminho**.
3. **A caminho** → **🛠️ Chegamos / atendendo**.
4. **Em atendimento** → **Resolver**, escrevendo o resultado (obrigatório).

A fila mostra primeiro o mais grave e, na mesma prioridade, o mais antigo. Só a coordenação muda prioridade, cancela ou reabre.

**Embarcações:** a logística cadastra os barcos em **Embarcações** (tipo, capacidade, piloto, combustível). Para usar um barco numa ocorrência, a logística, a coordenação ou a equipe do caso o vincula; o barco passa a **em uso** e volta a **disponível** quando a ocorrência é resolvida ou cancelada.

## 8. Abrigos, famílias e ajuda humanitária

Abrigos são preparados antes do evento; famílias e ajuda são registradas durante, com proteção dos dados pessoais.

**Abrigo pronto:** a coordenação ou o coordenador do abrigo registra a vistoria (água, energia, banheiros, cozinha, acessibilidade, kits, colchões). Com todos os itens, o abrigo recebe o selo **pronto**. Vistoria com mais de 90 dias aparece como vencida.

**Famílias abrigadas** (coordenação, saúde/assistência e equipe do abrigo):

1. Em **Famílias abrigadas**, escolha o abrigo e cadastre o responsável: nome completo, CPF válido, telefone e situação da casa.
2. Inclua os membros com parentesco. Sem CPF, informe o motivo.
3. Pessoa desaparecida: marque e informe o último dia e o local em que foi vista.
4. Fotos da casa ficam numa pasta privada, vistas só por quem atende a família.
5. O consentimento da família é obrigatório (LGPD).

**Ajuda humanitária** (logística e coordenação registram estoque; quem atende famílias registra entregas):

- **Estoque:** registre entradas (doação, compra, envio do Estado), perdas e ajustes. O saldo nunca fica negativo.
- **Entrega à família:** a tela mostra o que ela já recebeu. Repetir o mesmo item em menos de 7 dias exige justificativa.
- **Entrega à comunidade ou ao abrigo:** informe o número de pessoas atendidas.
- Em **Entregas e cobertura**, veja as famílias sem cesta há mais de 7 dias.

## 9. Recuperação

Depois do evento, o CIDC ajuda a registrar danos, acompanhar o retorno das famílias e aprender para o próximo ano.

- **Ficha S2iD** (coordenação e agente de campo): por comunidade e data, informe famílias, pessoas, desalojados, desabrigados, óbitos informados, casas danificadas e fonte da informação. O PDF gerado é um **rascunho** para lançar no S2iD oficial (sistema federal).
- **Retorno das famílias** (coordenação, saúde/assistência e equipe do abrigo): para cada família, data de retorno, endereço atual, se tem para onde ir e o que precisa (reforma, documentos, benefícios). Ao informar a data de retorno, a família deixa de contar como abrigada.
- **Lições aprendidas:** relatório de um acionamento do plano, com a linha do tempo, tarefas concluídas e atrasadas, ocorrências e ajuda entregue.
- **Encerrar o acionamento** no Plano de contingência quando a situação normalizar.

## 10. Responsáveis, chat, relatos e relatórios

Essas ferramentas ligam as áreas entre si e servem a todos os eixos.

**Responsáveis por área** (a coordenação define; todos consultam):

- 14 áreas por município, cada uma com **titular** e **suplente**: coordenação geral, monitoramento, campo, saúde, assistência social, logística, abrigos, embarcações, comunicação, voluntários, obras, áreas de risco, recuperação e S2iD.
- Pode ser uma pessoa com conta no CIDC ou alguém de fora (ex.: uma secretaria), com contato **institucional**.
- Tarefas do plano e ocorrências passadas a uma equipe vão sozinhas para o titular da área. A página avisa as áreas sem titular.

**Chat interno:** canal geral do município, canais entre comunidades (inclusive de municípios diferentes) e conversas privadas com pessoas escolhidas. Não é canal oficial de alerta. CPF digitado é mascarado.

**Relatos de campo:** qualquer voluntário ou equipe registra o que vê (chuva forte, rio subindo ou baixando, alagamento, incêndio/fumaça, comunidade isolada) com o local. Outras pessoas confirmam ou negam; a equipe pode transformar o relato em ocorrência.

**Relatórios:** todo menu tem **📄 Gerar relatório deste menu**, com PDF completo e CSV por tabela (abre no Excel, separador ponto e vírgula).

## 11. Administração e manutenção

Três rotinas automáticas no GitHub Actions mantêm o sistema funcionando; o administrador só intervém em atualizações e falhas.

| Rotina | Frequência | O que faz |
| --- | --- | --- |
| Coleta e robô | A cada 3 h | Lê as fontes, calcula o sinal, cria rascunhos e o relatório do robô |
| Robô do Telegram | A cada 15 min | Processa inscrições e envia alertas aprovados |
| Manter o painel acordado | A cada 4 h | Abre o site e clica em acordar, se preciso |

**Depois de atualizar o código:** Streamlit → **Manage app → Reboot app**. Sem isso, aparece erro de módulo antigo.

**Mudança no banco (migration):**

1. Revise o SQL antes de aplicar: ordem dos parâmetros, permissão por município e uso de `coalesce` nas checagens.
2. Abra o SQL Editor do Supabase, cole numa consulta nova e clique em **Run**.
3. Faça o Reboot do app e rode o teste integrado.

**Teste integrado:** `scripts/teste_integrado.py` cria dados [TESTE] e tenta burlar as permissões com as contas de teste. Resultado esperado: todas as verificações OK.

**Dados de teste:** ficam marcados com [TESTE]. Para apagar, rode `db/testes/limpar_dados_teste.sql` e, para as contas, `db/testes/limpar_usuarios_teste.sql`.

**Novo integrante:** em **Usuários e permissões**, escolha o perfil e o município; depois, se for o caso, defina-o como titular em **Responsáveis por área**.

## 12. Solução de problemas

A maioria dos problemas se resolve com um reinício do app ou conferindo a saúde das fontes.

| Sintoma | Causa provável | O que fazer |
| --- | --- | --- |
| Site mostra "This app has gone to sleep" | Plano gratuito, sem uso | Clicar em acordar e aguardar até 1 min |
| Erro de importação (ImportError) após atualização | Módulo antigo na memória | Manage app → Reboot app |
| Estação com "leitura antiga" ou "Sem dados" | Estação da ANA transmitindo de forma irregular | Conferir na Sala de monitoramento e a régua no local |
| Fonte com erro na Sala de monitoramento | Site da fonte fora ou mudou | Ver a execução "coleta" no GitHub Actions; a fonte volta sozinha na próxima rodada |
| Botão não aparece | Perfil sem permissão | Pedir ao administrador o perfil correto |
| "Sem permissão" ao salvar | Registro de outro município ou de outra equipe | Confirmar o município do perfil e a equipe responsável |
| Mudança de perfil não aparece | Perfil guardado por até 5 min | Clicar em 🔄 Atualizar dados |
| Login com Google dá "redirect_uri_mismatch" | Endereço de retorno errado no Google Cloud | Usar o endereço "auth/v1/callback" do projeto Supabase |
| Alerta aprovado não chegou no Telegram | Envio a cada 15 min ou pessoa não inscrita | Aguardar a próxima rodada; conferir a inscrição (/start no robô) |

## 13. Regras de segurança e LGPD

Toda pessoa que opera o CIDC segue estas regras; o banco de dados reforça a maioria delas.

- **Senhas e chaves:** nunca envie por chat, e-mail ou mensagem. A chave mestra do banco fica só no GitHub Actions, nunca no site.
- **Dados das famílias:** nome, CPF e fotos só para coordenação, saúde/assistência e equipe do abrigo. Não copie para planilhas pessoais nem grupos de mensagem. O CPF sai mascarado nos relatórios.
- **Consentimento:** cadastre a família só com o consentimento dela.
- **Telegram:** só recebe quem se inscreveu. Nunca inclua números de terceiros.
- **Contatos de responsáveis:** use telefone ou e-mail institucional; telefone pessoal só com autorização da pessoa.
- **Chat e relatos:** não escreva CPF, documentos ou dados de saúde de terceiros.
- **Decisão humana:** não aprove um alerta sem conferir as fontes e o território.
- **Canais oficiais:** o CIDC é um protótipo. Em emergência: **199** (Defesa Civil) ou **193** (Bombeiros).
