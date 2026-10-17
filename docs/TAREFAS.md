# Tarefas atribuídas

Siga a ordem. Cada tarefa tem um critério de pronto. Ao terminar uma tarefa:
1. rode os testes;
2. faça o commit;
3. marque `[x]` aqui;
4. explique ao usuário, em português simples, o que mudou e o que ele precisa fazer.

Regras e padrões: [AGENTS.md](../AGENTS.md). Contexto: [CONTINUAR_EM_OUTRA_IA.md](CONTINUAR_EM_OUTRA_IA.md).

## A. Pendências (fazer primeiro)
- [ ] **A1 — Migrations 0015 e 0016.**
  - Pergunte ao usuário se rodou `202610140015_corrige_permissao_ocorrencia.sql` e
    `202610140016_ajuda_humanitaria.sql`.
  - Se não rodou: copie as duas juntas, confira o início do texto e abra o SQL Editor.
  - Lembre-o de **apagar a aba do SQL Editor em que ele colou, por engano, o arquivo de senhas**.
  - *Pronto quando:* a tabela `ajuda_movimentos` responder 200 pelo REST.
- [x] **A2 — Teste da correção das ocorrências.**
  - Pelo REST: abra uma ocorrência `[TESTE]` como `campo.labrea`. Como `saude.labrea`, sem estar
    na equipe, tente mudar a situação.
  - *Pronto quando:* a tentativa da saúde for **recusada**. Antes de 0015, ela passava.
- [x] **A3 — Teste da ajuda humanitária.** Pelo REST, com as contas de teste:
  - entrada de 50 cestas como `logistica.labrea`, com observação `[TESTE]`;
  - entrega de 1 cesta a uma família `[TESTE]`;
  - repetir sem justificativa: deve dar erro `REPETIDA`;
  - entregar mais do que o saldo: deve dar erro;
  - `voluntario1` tentando entregar: deve ser bloqueado;
  - conferir a view `ajuda_cobertura_familias`.
  - *Pronto quando:* todos os casos derem o resultado esperado. Se algo falhar, corrija com uma
    migration nova.
- [x] **A4 — Limpeza dos testes da ajuda.** Inclua em `db/testes/limpar_dados_teste.sql` a
  remoção dos movimentos `[TESTE]` de `ajuda_movimentos`, pela observação ou pelo destino de
  teste.
- [ ] **A5 — Rotina de acordar.** Peça ao usuário para rodar Actions → "Manter o painel
  acordado" → Run workflow.
  - *Pronto quando:* aparecer ✅.
- [ ] **A6 — Login com Google.** Confirme com o usuário que o URI de redirecionamento no Google
  Cloud é `https://<ref>.supabase.co/auth/v1/callback`. O ref está em `SUPABASE_URL`.
  - *Pronto quando:* ele entrar com Google e ver a tela "Complete seus dados" no primeiro acesso.
- [ ] **A7 — Plano acionado pela aprovação de um alerta.** Combine com o usuário antes, porque
  aprovar um alerta real envia Telegram.
  - *Pronto quando:* aprovar um rascunho de Lábrea criar um registro em `plano_acionamentos`
    com origem `alerta_aprovado` e as tarefas correspondentes.

## B. Próximas funcionalidades (uma por vez; pergunte ao usuário qual vem primeiro)
Cada uma deve ter:
- migration com RLS, testada pelo REST;
- página ou aba registrada no `Home.py` por perfil;
- relatório (`painel_relatorio`);
- dados de teste `[TESTE]` e entrada correspondente no script de limpeza;
- testes unitários;
- teste de tela com AppTest.

- [x] **B1 — Áreas de risco por comunidade (prevenção).** Tipo (inundação, terras caídas,
  erosão, deslizamento, incêndio), número de casas e pessoas, nível, foto e coordenadas, com
  mapa. Vincular ao relatório municipal.
- [x] **B2 — Checklist de abrigo pronto (preparação).** Água, energia, banheiros, cozinha,
  acessibilidade, kits e colchões. Selo "pronto" e data da vistoria. Aviso quando a vistoria tiver
  mais de 90 dias.
- [x] **B3 — Aviso no Telegram para responsáveis.** Quando alguém receber uma tarefa do plano ou
  uma ocorrência, avisar quem tem Telegram vinculado, sempre opt-in. Reaproveite
  `core/telegram_robo.py` e o `telegram.yml`. Nunca use dados de quem não aderiu.
- [x] **B4 — Ficha para o S2iD (resposta).** Rascunho em PDF com afetados, desalojados,
  desabrigados, óbitos informados, danos a casas e instalações e ajuda entregue, montado com os
  dados do app. Deixe claro que é **rascunho** para lançar no S2iD oficial.
- [x] **B5 — Calendário anual de risco (prevenção).** Pelos marcadores históricos da ANA, o mês
  típico da cheia e da seca por estação, com aviso "faltam X dias para o período crítico".
  Não presuma: só onde houver série oficial.
- [ ] **B6 — Retorno das famílias (recuperação).** Quem voltou para casa, quem não tem para onde
  ir e o que falta (reforma, documentos, benefícios). Respeite a LGPD das famílias.
- [ ] **B7 — Lições aprendidas (recuperação).** Relatório automático de um acionamento do plano:
  linha do tempo, alertas, tarefas concluídas e atrasadas, ocorrências e ajuda entregue.
- [ ] **B8 — Logística no estoque novo.** A aba "Pré-posicionamento" usa a tabela antiga
  `recursos`. Passe a usar `ajuda_movimentos` e `ajuda_saldo`, sem perder os dados antigos:
  migre-os como entrada do tipo "ajuste" com observação.
- [ ] **B9 — Embarcações e equipes (resposta).** Cadastro de barcos (capacidade, piloto,
  combustível) e vínculo com as ocorrências.
- [ ] **B10 — Obras e intervenções (mitigação).** Status, valor, fonte do recurso e comunidades
  beneficiadas.
