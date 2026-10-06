-- O coletor usa a chave service_role, que ignora RLS mas precisa de privilégios
-- de tabela. Sem eles o PostgREST responde 42501 (permission denied).
grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
