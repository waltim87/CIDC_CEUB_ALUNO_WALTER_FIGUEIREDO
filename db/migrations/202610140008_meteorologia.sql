-- Meteorologia: avisos e previsão oficiais do INMET (sem chave) e chuva prevista em mm
-- do Open-Meteo (modelo numérico, gratuito). Coletados por collectors/inmet.py.
-- Dados oficiais/públicos: leitura liberada também para a página pública.

create table if not exists public.avisos_meteorologicos (
    id uuid primary key default gen_random_uuid(),
    codigo text not null,                 -- identificador CAP do INMET
    municipio_id char(7) not null references public.municipios(id_ibge),
    descricao text not null,              -- ex.: Tempestade, Chuvas Intensas, Baixa Umidade
    severidade text not null,             -- Perigo Potencial, Perigo, Grande Perigo
    cor text,
    inicio timestamptz,
    fim timestamptz,
    riscos text,
    instrucoes text,
    fonte text not null default 'INMET - avisos meteorológicos (apiprevmet3)',
    atualizado_em timestamptz not null default now(),
    unique (codigo, municipio_id)
);
create index if not exists avisos_vigencia on public.avisos_meteorologicos (municipio_id, fim desc);

create table if not exists public.previsao_tempo (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    data date not null,
    periodo text not null check (periodo in ('manha', 'tarde', 'noite', 'dia')),
    resumo text,
    temp_max numeric,
    temp_min numeric,
    umidade_max numeric,
    umidade_min numeric,
    vento text,
    chuva_prevista_mm numeric,            -- Open-Meteo (somente no período 'dia')
    fonte text not null,
    atualizado_em timestamptz not null default now(),
    unique (municipio_id, data, periodo)
);

alter table public.avisos_meteorologicos enable row level security;
alter table public.previsao_tempo enable row level security;

drop policy if exists avisos_leitura on public.avisos_meteorologicos;
create policy avisos_leitura on public.avisos_meteorologicos for select to anon, authenticated using (true);
drop policy if exists previsao_leitura on public.previsao_tempo;
create policy previsao_leitura on public.previsao_tempo for select to anon, authenticated using (true);

grant select on public.avisos_meteorologicos, public.previsao_tempo to anon, authenticated;
grant select, insert, update, delete on public.avisos_meteorologicos, public.previsao_tempo to service_role;

update public.fontes
set url = 'https://apiprevmet3.inmet.gov.br/avisos/ativos'
where nome = 'INMET';
