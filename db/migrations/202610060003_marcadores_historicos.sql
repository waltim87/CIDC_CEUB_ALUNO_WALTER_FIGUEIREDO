-- Marcadores históricos de cheia e seca por estação.
-- Valores NÃO são preenchidos aqui: devem vir de série oficial (ANA/Hidroweb, SGB).
-- Preencha com update em public.estacoes e registre a fonte em historico_fonte.
alter table public.estacoes
    add column if not exists cheia_historica_cm numeric,
    add column if not exists cheia_historica_data date,
    add column if not exists seca_historica_cm numeric,
    add column if not exists seca_historica_data date,
    add column if not exists historico_fonte text;

alter table public.estacoes drop constraint if exists estacoes_historico_ck;
alter table public.estacoes add constraint estacoes_historico_ck check (
    cheia_historica_cm is null or seca_historica_cm is null
    or cheia_historica_cm >= seca_historica_cm
);
