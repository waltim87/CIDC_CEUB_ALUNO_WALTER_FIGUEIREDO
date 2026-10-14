-- Remove as 10 contas de teste de usuarios_teste.sql (e-mails @cidc-teste.example).
-- O que elas registraram é tratado assim: campos opcionais que apontam para a conta
-- ficam vazios (ex.: "aprovado por"); registros que exigem autor (relatos, votos) são apagados.
begin;

do $$
declare
    fk record;
    ids uuid[];
begin
    select array_agg(u.id) into ids
      from public.usuarios u join auth.users a on a.id = u.auth_id
     where a.email like '%@cidc-teste.example';
    if ids is null then
        raise notice 'Nenhuma conta de teste encontrada';
        return;
    end if;

    for fk in
        select c.conrelid::regclass as tabela, att.attname as coluna, att.attnotnull as obrigatoria
          from pg_constraint c
          join pg_attribute att on att.attrelid = c.conrelid and att.attnum = c.conkey[1]
         where c.contype = 'f' and c.confrelid = 'public.usuarios'::regclass and c.confdeltype <> 'c'
    loop
        if fk.obrigatoria then
            execute format('delete from %s where %I = any($1)', fk.tabela, fk.coluna) using ids;
        else
            execute format('update %s set %I = null where %I = any($1)', fk.tabela, fk.coluna, fk.coluna) using ids;
        end if;
    end loop;

    delete from public.usuarios where id = any(ids);   -- voluntários e designações em cascata
end $$;

delete from auth.users where email like '%@cidc-teste.example';   -- identidades e sessões em cascata
commit;

select count(*) as contas_teste_restantes from auth.users where email like '%@cidc-teste.example';
