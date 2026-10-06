-- Teste de isolamento RLS (Fase 4).
-- Cria usuários fictícios dentro de uma transação e a desfaz ao final:
-- o bloco termina de propósito com um erro que contém o relatório e reverte tudo.
do $teste$
declare
  a char(7);
  b char(7);
  ua uuid := gen_random_uuid();
  ub uuid := gen_random_uuid();
  up uuid := gen_random_uuid();
  n int;
  m int;
  r text := '';
begin
  select id_ibge into a from public.municipios order by id_ibge limit 1;
  select id_ibge into b from public.municipios order by id_ibge offset 1 limit 1;

  insert into auth.users (id, aud, role, email) values
    (ua, $$authenticated$$, $$authenticated$$, $$teste_a@exemplo.invalid$$),
    (ub, $$authenticated$$, $$authenticated$$, $$teste_b@exemplo.invalid$$),
    (up, $$authenticated$$, $$authenticated$$, $$teste_p@exemplo.invalid$$);

  insert into public.usuarios (nome, perfil, municipio_id, auth_id) values
    ($$Coord A$$, $$coordenador_municipal$$, a, ua),
    ($$Coord B$$, $$coordenador_municipal$$, b, ub),
    ($$Pesquisador$$, $$pesquisador$$, null, up);

  insert into public.recursos (municipio_id, tipo, quantidade) values
    (a, $$agua$$, 10), (b, $$agua$$, 20);

  -- Coordenador do município A
  perform set_config($$request.jwt.claims$$, jsonb_build_object($$sub$$, ua, $$role$$, $$authenticated$$)::text, true);
  perform set_config($$request.jwt.claim.sub$$, ua::text, true);
  set local role authenticated;

  select count(*) into n from public.recursos;
  select count(*) into m from public.recursos where municipio_id = a;
  r := r || format($$1) Coord A ve %s recursos, %s do proprio municipio -> %s$$ || E'\n', n, m,
         case when n = m and n > 0 then $$OK$$ else $$FALHA$$ end);

  begin
    insert into public.recursos (municipio_id, tipo, quantidade) values (b, $$alimento$$, 1);
    r := r || $$2) Coord A inseriu recurso em outro municipio -> FALHA$$ || E'\n';
  exception when others then
    r := r || $$2) Coord A inserir em outro municipio bloqueado -> OK$$ || E'\n';
  end;

  update public.recursos set quantidade = 999 where municipio_id = b;
  get diagnostics n = row_count;
  r := r || format($$3) Coord A alterou %s linhas de outro municipio -> %s$$ || E'\n', n,
         case when n = 0 then $$OK$$ else $$FALHA$$ end);

  select count(*) into n from public.usuarios where municipio_id <> a;
  r := r || format($$4) Coord A ve %s usuarios de outros municipios -> %s$$ || E'\n', n,
         case when n = 0 then $$OK$$ else $$FALHA$$ end);
  reset role;

  -- Coordenador do município B
  perform set_config($$request.jwt.claims$$, jsonb_build_object($$sub$$, ub, $$role$$, $$authenticated$$)::text, true);
  perform set_config($$request.jwt.claim.sub$$, ub::text, true);
  set local role authenticated;
  select count(*) into n from public.recursos;
  select count(*) into m from public.recursos where municipio_id = b;
  r := r || format($$5) Coord B ve %s recursos, %s do proprio municipio -> %s$$ || E'\n', n, m,
         case when n = m and n > 0 then $$OK$$ else $$FALHA$$ end);
  reset role;

  -- Pesquisador (sem municipio): nao deve ver dados operacionais
  perform set_config($$request.jwt.claims$$, jsonb_build_object($$sub$$, up, $$role$$, $$authenticated$$)::text, true);
  perform set_config($$request.jwt.claim.sub$$, up::text, true);
  set local role authenticated;
  select count(*) into n from public.recursos;
  r := r || format($$6) Pesquisador ve %s recursos -> %s$$ || E'\n', n,
         case when n = 0 then $$OK$$ else $$FALHA$$ end);
  reset role;

  -- Visitante anonimo (pagina publica)
  perform set_config($$request.jwt.claims$$, $$$$, true);
  perform set_config($$request.jwt.claim.sub$$, $$$$, true);
  set local role anon;
  begin
    select count(*) into n from public.recursos;
  exception when insufficient_privilege then
    n := 0;
  end;
  begin
    select count(*) into m from public.usuarios;
  exception when insufficient_privilege then
    m := 0;
  end;
  r := r || format($$7) Anonimo ve %s recursos e %s usuarios (0 ou permissao negada) -> %s$$ || E'\n', n, m,
         case when n = 0 and m = 0 then $$OK$$ else $$FALHA$$ end);
  select count(*) into n from public.municipios;
  r := r || format($$8) Anonimo ve %s municipios (esperado > 0) -> %s$$ || E'\n', n,
         case when n > 0 then $$OK$$ else $$FALHA$$ end);
  reset role;

  raise exception using message = E'RELATORIO (nada foi gravado)\n' || r;
end
$teste$;
