-- Permissões mínimas da role service_role para a coleta automática (GitHub Actions).
-- A service_role ignora RLS, mas precisa de privilégio de tabela.
grant usage on schema public to service_role;
grant select, update on public.fontes to service_role;
grant select on public.estacoes to service_role;
grant select, insert, update on public.leituras to service_role;
