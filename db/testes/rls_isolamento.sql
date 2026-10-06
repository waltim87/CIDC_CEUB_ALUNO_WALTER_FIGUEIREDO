-- Teste de isolamento RLS (Fase 4), ampliado.
-- Cria usuários e dados fictícios dentro de uma transação e a desfaz ao final:
-- o bloco termina de propósito com um erro que contém o relatório e reverte tudo.
-- Cobre: recursos, alertas (visibilidade e transições), abrigos, afetados,
-- assinaturas, entregas, usuários/pesos, escopo estadual (UF) e acesso anônimo.
do $teste$
declare
  a char(7);
  b char(7);
  c char(7) := '9999999'; -- município fictício de outra UF (PA)
  u_a uuid := gen_random_uuid();
  u_b uuid := gen_random_uuid();
  u_p uuid := gen_random_uuid();
  u_g uuid := gen_random_uuid();
  u_f uuid := gen_random_uuid();
  u_o uuid := gen_random_uuid();
  u_m uuid := gen_random_uuid();
  id_a uuid;
  id_b uuid;
  al_rasc_a uuid;
  al_rasc_a2 uuid;
  al_env_a uuid;
  al_apr_a uuid;
  al_rasc_b uuid;
  al_rasc_c uuid;
  com_a uuid;
  com_b uuid;
  n int;
  m int;
  falhou boolean;
  r text := '';
begin
  create function pg_temp.entrar(u uuid, papel text) returns void
  language plpgsql as $f$
  begin
    perform set_config('request.jwt.claims',
      case when u is null then '' else jsonb_build_object('sub', u, 'role', papel)::text end, true);
    perform set_config('request.jwt.claim.sub', coalesce(u::text, ''), true);
    execute format('set local role %I', papel);
  end
  $f$;

  select id_ibge into a from public.municipios order by id_ibge limit 1;
  select id_ibge into b from public.municipios order by id_ibge offset 1 limit 1;
  insert into public.municipios (id_ibge, nome, uf) values (c, 'Teste Outra UF', 'PA');

  insert into auth.users (id, aud, role, email) values
    (u_a, 'authenticated', 'authenticated', 'teste_a@exemplo.invalid'),
    (u_b, 'authenticated', 'authenticated', 'teste_b@exemplo.invalid'),
    (u_p, 'authenticated', 'authenticated', 'teste_p@exemplo.invalid'),
    (u_g, 'authenticated', 'authenticated', 'teste_g@exemplo.invalid'),
    (u_f, 'authenticated', 'authenticated', 'teste_f@exemplo.invalid'),
    (u_o, 'authenticated', 'authenticated', 'teste_o@exemplo.invalid'),
    (u_m, 'authenticated', 'authenticated', 'teste_m@exemplo.invalid');

  insert into public.usuarios (nome, perfil, municipio_id, auth_id) values
    ('Coord A', 'coordenador_municipal', a, u_a),
    ('Coord B', 'coordenador_municipal', b, u_b),
    ('Pesquisador', 'pesquisador', null, u_p),
    ('Gestor estadual AM', 'gestor_estadual', a, u_g),
    ('Agente A', 'agente_campo', a, u_f),
    ('Operador', 'operador_monitoramento', null, u_o),
    ('Admin', 'administrador', null, u_m);
  select id into id_a from public.usuarios where auth_id = u_a;
  select id into id_b from public.usuarios where auth_id = u_b;

  insert into public.recursos (municipio_id, tipo, quantidade) values
    (a, 'agua', 10), (b, 'agua', 20), (c, 'agua', 30);
  insert into public.comunidades (municipio_id, nome) values (a, 'Com A') returning id into com_a;
  insert into public.comunidades (municipio_id, nome) values (b, 'Com B') returning id into com_b;

  insert into public.alertas (municipio_id, classe, texto, status) values (a, 'Alerta', 'rascunho A', 'rascunho') returning id into al_rasc_a;
  insert into public.alertas (municipio_id, classe, texto, status) values (a, 'Alerta', 'rascunho A2', 'rascunho') returning id into al_rasc_a2;
  insert into public.alertas (municipio_id, classe, texto, status, emitido_em) values (a, 'Alerta', 'enviado A', 'enviado', now()) returning id into al_env_a;
  insert into public.alertas (municipio_id, classe, texto, status) values (a, 'Alerta', 'aprovado A', 'aprovado') returning id into al_apr_a;
  insert into public.alertas (municipio_id, classe, texto, status) values (b, 'Alerta', 'rascunho B', 'rascunho') returning id into al_rasc_b;
  insert into public.alertas (municipio_id, classe, texto, status) values (c, 'Alerta', 'rascunho C', 'rascunho') returning id into al_rasc_c;

  ---------------------------------------------------------------- Coord A
  perform pg_temp.entrar(u_a, 'authenticated');

  select count(*) into n from public.recursos;
  select count(*) into m from public.recursos where municipio_id = a;
  r := r || format('1) Coord A ve %s recursos, %s do proprio municipio -> %s' || E'\n', n, m,
         case when n = m and n > 0 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    insert into public.recursos (municipio_id, tipo, quantidade) values (b, 'alimento', 1);
  exception when others then falhou := false;
  end;
  r := r || '2) Coord A inserir recurso em outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  update public.recursos set quantidade = 999 where municipio_id = b;
  get diagnostics n = row_count;
  r := r || format('3) Coord A alterou %s linhas de recursos de outro municipio -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);

  select count(*) into n from public.usuarios where municipio_id <> a;
  r := r || format('4) Coord A ve %s usuarios de outros municipios -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);

  select count(*) into n from public.alertas where id in (al_rasc_a, al_rasc_a2, al_env_a, al_apr_a);
  select count(*) into m from public.alertas where id in (al_rasc_b, al_rasc_c);
  r := r || format('9) Coord A ve %s alertas proprios (esperado 4) e %s de outros (esperado 0) -> %s' || E'\n', n, m,
         case when n = 4 and m = 0 then 'OK' else 'FALHA' end);

  update public.alertas set status = 'aprovado', aprovado_por = id_a where id = al_rasc_a;
  get diagnostics n = row_count;
  r := r || format('10) Coord A aprovou %s alerta proprio (esperado 1) -> %s' || E'\n', n,
         case when n = 1 then 'OK' else 'FALHA' end);

  update public.alertas set status = 'aprovado', aprovado_por = id_a where id = al_rasc_b;
  get diagnostics n = row_count;
  r := r || format('11) Coord A aprovou %s alerta de outro municipio (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    update public.alertas set status = 'enviado', emitido_em = now() where id = al_rasc_a2;
  exception when others then falhou := false;
  end;
  r := r || '12) Coord A pular rascunho->enviado bloqueado pelo gatilho -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    update public.alertas set status = 'aprovado', aprovado_por = id_b where id = al_rasc_a2;
  exception when others then falhou := false;
  end;
  r := r || '13) Coord A aprovar em nome de outro usuario bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  update public.alertas set status = 'enviado', emitido_em = now() where id = al_apr_a;
  get diagnostics n = row_count;
  r := r || format('14) Coord A enviou %s alerta aprovado (esperado 1) -> %s' || E'\n', n,
         case when n = 1 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    insert into public.abrigos (municipio_id, nome, capacidade) values (a, 'Abrigo A', 10);
    falhou := false;
  exception when others then falhou := true;
  end;
  r := r || '15) Coord A criou abrigo no proprio municipio -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.abrigos (municipio_id, nome, capacidade) values (b, 'Abrigo B', 10);
  exception when others then falhou := false;
  end;
  r := r || '16) Coord A criar abrigo em outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.assinaturas_alerta (municipio_id, canal, destino) values (a, 'email', 'a@exemplo.invalid');
    falhou := false;
  exception when others then falhou := true;
  end;
  r := r || '17) Coord A criou assinatura no proprio municipio -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.assinaturas_alerta (municipio_id, canal, destino) values (b, 'email', 'b@exemplo.invalid');
  exception when others then falhou := false;
  end;
  r := r || '18) Coord A criar assinatura em outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.entregas_alerta (alerta_id, canal, destino_mascarado, status) values (al_env_a, 'email', 'a***@exemplo', 'enviado');
    falhou := false;
  exception when others then falhou := true;
  end;
  r := r || '19) Coord A registrou entrega de alerta proprio -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.entregas_alerta (alerta_id, canal, destino_mascarado, status) values (al_rasc_b, 'email', 'b***@exemplo', 'enviado');
  exception when others then falhou := false;
  end;
  r := r || '20) Coord A registrar entrega de alerta de outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.pessoas_afetadas (comunidade_id, familias, pessoas, data) values (com_a, 2, 8, now());
    falhou := false;
  exception when others then falhou := true;
  end;
  r := r || '21) Coord A registrou afetados em comunidade propria -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.pessoas_afetadas (comunidade_id, familias, pessoas, data) values (com_b, 2, 8, now());
  exception when others then falhou := false;
  end;
  r := r || '22) Coord A registrar afetados em comunidade de outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := false;
  begin
    update public.usuarios set perfil = 'administrador' where auth_id = u_a;
    get diagnostics n = row_count;
    falhou := n > 0;
  exception when others then falhou := false;
  end;
  r := r || '23) Coord A promover o proprio perfil a administrador bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := false;
  begin
    update public.configuracao_pesos set validacao_oficial = true;
    get diagnostics n = row_count;
    falhou := n > 0;
  exception when others then falhou := false;
  end;
  r := r || '24) Coord A alterar pesos do indice bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := false;
  begin
    select count(*) into n from public.auditoria;
    falhou := n > 0;
  exception when others then falhou := false;
  end;
  r := r || '25) Coord A ler auditoria bloqueado ou vazio -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';
  reset role;

  ---------------------------------------------------------------- Coord B
  perform pg_temp.entrar(u_b, 'authenticated');
  select count(*) into n from public.recursos;
  select count(*) into m from public.recursos where municipio_id = b;
  r := r || format('5) Coord B ve %s recursos, %s do proprio municipio -> %s' || E'\n', n, m,
         case when n = m and n > 0 then 'OK' else 'FALHA' end);
  select count(*) into n from public.assinaturas_alerta where municipio_id = a;
  r := r || format('26) Coord B ve %s assinaturas de outro municipio -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  select count(*) into n from public.pessoas_afetadas where comunidade_id = com_a;
  r := r || format('27) Coord B ve %s afetados de outro municipio -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  reset role;

  ---------------------------------------------------------------- Agente de campo (A)
  perform pg_temp.entrar(u_f, 'authenticated');
  update public.alertas set status = 'aprovado', aprovado_por = (select id from public.usuarios where auth_id = u_f) where id = al_rasc_a2;
  get diagnostics n = row_count;
  r := r || format('28) Agente de campo aprovou %s alertas (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    insert into public.pessoas_afetadas (comunidade_id, familias, pessoas, data) values (com_a, 1, 4, now());
    falhou := false;
  exception when others then falhou := true;
  end;
  r := r || '29) Agente registrou afetados no proprio municipio -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.pessoas_afetadas (comunidade_id, familias, pessoas, data) values (com_b, 1, 4, now());
  exception when others then falhou := false;
  end;
  r := r || '30) Agente registrar afetados em outro municipio bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := true;
  begin
    insert into public.recursos (municipio_id, tipo, quantidade) values (a, 'agua', 1);
  exception when others then falhou := false;
  end;
  r := r || '31) Agente criar recurso bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';
  reset role;

  ---------------------------------------------------------------- Gestor estadual (AM)
  perform pg_temp.entrar(u_g, 'authenticated');
  select count(*) into n from public.recursos where municipio_id in (a, b);
  select count(*) into m from public.recursos where municipio_id = c;
  r := r || format('32) Gestor estadual ve %s recursos da propria UF (esperado 2) e %s de outra UF (esperado 0) -> %s' || E'\n', n, m,
         case when n = 2 and m = 0 then 'OK' else 'FALHA' end);

  update public.alertas set status = 'aprovado',
         aprovado_por = (select id from public.usuarios where auth_id = u_g) where id = al_rasc_b;
  get diagnostics n = row_count;
  r := r || format('33) Gestor estadual aprovou %s alerta de municipio da propria UF (esperado 1) -> %s' || E'\n', n,
         case when n = 1 then 'OK' else 'FALHA' end);

  update public.alertas set status = 'aprovado',
         aprovado_por = (select id from public.usuarios where auth_id = u_g) where id = al_rasc_c;
  get diagnostics n = row_count;
  r := r || format('34) Gestor estadual aprovou %s alerta de outra UF (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    insert into public.recursos (municipio_id, tipo, quantidade) values (b, 'alimento', 1);
  exception when others then falhou := false;
  end;
  r := r || '35) Gestor estadual criar recurso (somente leitura) bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';
  reset role;

  ---------------------------------------------------------------- Operador de monitoramento
  perform pg_temp.entrar(u_o, 'authenticated');
  select count(*) into n from public.alertas where id in (al_rasc_a2, al_rasc_c);
  r := r || format('36) Operador ve %s alertas para revisao (esperado 2) -> %s' || E'\n', n,
         case when n = 2 then 'OK' else 'FALHA' end);
  select count(*) into n from public.recursos;
  r := r || format('37) Operador ve %s recursos (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  reset role;

  ---------------------------------------------------------------- Pesquisador
  perform pg_temp.entrar(u_p, 'authenticated');
  select count(*) into n from public.recursos;
  r := r || format('6) Pesquisador ve %s recursos -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  select count(*) into n from public.alertas where status <> 'enviado';
  r := r || format('38) Pesquisador ve %s alertas nao publicados (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  reset role;

  ---------------------------------------------------------------- Anonimo
  perform pg_temp.entrar(null, 'anon');
  n := 0; m := 0;
  begin select count(*) into n from public.recursos; exception when insufficient_privilege then n := 0; end;
  begin select count(*) into m from public.usuarios; exception when insufficient_privilege then m := 0; end;
  r := r || format('7) Anonimo ve %s recursos e %s usuarios (0 ou permissao negada) -> %s' || E'\n', n, m,
         case when n = 0 and m = 0 then 'OK' else 'FALHA' end);
  select count(*) into n from public.municipios;
  r := r || format('8) Anonimo ve %s municipios (esperado > 0) -> %s' || E'\n', n,
         case when n > 0 then 'OK' else 'FALHA' end);

  select count(*) into n from public.alertas where id in (al_rasc_a, al_rasc_a2, al_env_a, al_apr_a, al_rasc_b, al_rasc_c) and status = 'enviado';
  select count(*) into m from public.alertas where id in (al_rasc_a, al_rasc_a2, al_env_a, al_apr_a, al_rasc_b, al_rasc_c) and status <> 'enviado';
  r := r || format('39) Anonimo ve %s alertas enviados (esperado 2) e %s nao enviados (esperado 0) -> %s' || E'\n', n, m,
         case when n = 2 and m = 0 then 'OK' else 'FALHA' end);

  falhou := true;
  begin
    insert into public.alertas (municipio_id, classe, texto) values (a, 'Alerta', 'falso');
  exception when others then falhou := false;
  end;
  r := r || '40) Anonimo criar alerta bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  falhou := false;
  begin
    update public.alertas set texto = 'adulterado' where id = al_env_a;
    get diagnostics n = row_count;
    falhou := n > 0;
  exception when others then falhou := false;
  end;
  r := r || '41) Anonimo alterar alerta enviado bloqueado -> ' || case when not falhou then 'OK' else 'FALHA' end || E'\n';

  n := 0;
  begin select count(*) into n from public.assinaturas_alerta; exception when insufficient_privilege then n := 0; end;
  r := r || format('42) Anonimo ve %s assinaturas (esperado 0) -> %s' || E'\n', n,
         case when n = 0 then 'OK' else 'FALHA' end);
  reset role;

  ---------------------------------------------------------------- Administrador
  perform pg_temp.entrar(u_m, 'authenticated');
  select count(*) into n from public.recursos where municipio_id in (a, b, c);
  r := r || format('43) Administrador ve %s recursos de 3 municipios (esperado 3) -> %s' || E'\n', n,
         case when n = 3 then 'OK' else 'FALHA' end);
  update public.configuracao_pesos set validacao_oficial = validacao_oficial;
  get diagnostics n = row_count;
  r := r || format('44) Administrador alterou %s linhas de pesos (esperado >= 1) -> %s' || E'\n', n,
         case when n >= 1 then 'OK' else 'FALHA' end);
  reset role;

  raise exception using message = E'RELATORIO (nada foi gravado)\n' || r;
end
$teste$;
