alter table public.fontes
    add column if not exists ultima_verificacao timestamptz,
    add column if not exists ultimo_erro text;
