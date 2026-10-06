-- Permissões mínimas da role service_role para a coleta automática (GitHub Actions).
-- A service_role ignora RLS, mas precisa de privilégio de tabela.
grant usage on schema public to service_role;
grant select, update on public.fontes to service_role;
grant select on public.estacoes to service_role;
grant select, insert, update on public.leituras to service_role;
grant select on public.municipios to service_role;
grant select on public.regras to service_role;
grant select on public.configuracao_pesos to service_role;
grant select, insert on public.indices to service_role;
grant select, insert on public.alertas to service_role;
