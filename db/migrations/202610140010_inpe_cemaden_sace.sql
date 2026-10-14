-- Fontes ativadas: INPE Queimadas (focos de calor), Cemaden (pluviômetros) e SGB/SACE
-- (situação oficial dos pontos de alerta hidrológico da bacia do Amazonas).
-- Dados públicos: leitura liberada também na página pública.

-- INPE: focos de calor com risco de fogo e dias sem chuva.
alter table public.focos_calor
    add column if not exists id_inpe text,
    add column if not exists risco_fogo numeric,
    add column if not exists dias_sem_chuva integer,
    add column if not exists precipitacao numeric,
    add column if not exists frp numeric;
create unique index if not exists focos_id_inpe on public.focos_calor (id_inpe) where id_inpe is not null;
create index if not exists focos_municipio_data on public.focos_calor (municipio_id, data_hora desc);
drop policy if exists focos_select_publico on public.focos_calor;
create policy focos_select_publico on public.focos_calor for select to anon using (true);
grant select on public.focos_calor to anon;
grant select, insert, update, delete on public.focos_calor to service_role;

-- Cemaden: última leitura e acumulados de cada pluviômetro do AM.
create table if not exists public.chuva_cemaden (
    id_estacao integer primary key,
    municipio_id char(7) references public.municipios(id_ibge),
    nome text not null,
    ultimo_valor_mm numeric,
    medido_em timestamptz,
    acc1h_mm numeric,
    acc3h_mm numeric,
    acc6h_mm numeric,
    acc12h_mm numeric,
    acc24h_mm numeric,
    acc48h_mm numeric,
    acc72h_mm numeric,
    acc96h_mm numeric,
    fonte text not null default 'Cemaden - mapa interativo (resources.cemaden.gov.br)',
    atualizado_em timestamptz not null default now()
);

-- SGB/SACE: situação oficial de cada ponto de alerta da bacia do Amazonas.
create table if not exists public.sace_pontos (
    pm integer primary key,
    nome text not null,
    latitude double precision,
    longitude double precision,
    municipio_id char(7) references public.municipios(id_ibge),
    cota_cm numeric,
    medido_em timestamptz,
    situacao text,
    cor text,
    link text,
    fonte text not null default 'SGB/SACE - Sistema de Alerta Hidrológico da bacia do Amazonas',
    atualizado_em timestamptz not null default now()
);

alter table public.chuva_cemaden enable row level security;
alter table public.sace_pontos enable row level security;
drop policy if exists cemaden_leitura on public.chuva_cemaden;
create policy cemaden_leitura on public.chuva_cemaden for select to anon, authenticated using (true);
drop policy if exists sace_leitura on public.sace_pontos;
create policy sace_leitura on public.sace_pontos for select to anon, authenticated using (true);
grant select on public.chuva_cemaden, public.sace_pontos to anon, authenticated;
grant select, insert, update, delete on public.chuva_cemaden, public.sace_pontos to service_role;

update public.fontes set url = 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/'
where nome = 'INPE Queimadas';
update public.fontes set url = 'https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=AM'
where nome = 'Cemaden PED';
update public.fontes set url = 'https://sace.sgb.gov.br/estacoes_mapa.php?bacia=amazonas'
where nome = 'SGB SACE';
update public.fontes
set status = 'indisponivel',
    ultimo_erro = 'Servidor do INEP (inepdata/download.inep.gov.br) recusa conexões automatizadas; '
                  'escolas podem ser cadastradas manualmente em Gestão municipal > Infraestrutura.',
    ultima_verificacao = now()
where nome = 'INEP Dados Abertos';
