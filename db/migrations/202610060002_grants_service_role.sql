-- O coletor usa a chave service_role; sem estes privilégios o PostgREST
-- responde 42501 (permission denied) ao gravar saúde e leituras.
grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
alter default privileges in schema public
    grant select, insert, update, delete on tables to service_role;
alter default privileges in schema public
    grant usage, select on sequences to service_role;
