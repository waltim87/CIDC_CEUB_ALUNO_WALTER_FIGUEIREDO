-- Marcadores históricos de cheia e seca das estações ANA (fonte oficial) e
-- vínculo dos alertas gerados pelo robô com a análise de origem.
-- Valores gerados por scripts/extremos_historicos.py a partir da série oficial
-- ANA HidroSerieHistorica (1990 em diante, picos isolados descartados, régua
-- conferida com a telemetria). Reexecute o script para atualizar.

-- Garante as colunas (idempotente; repete a migration 202610060003).
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

update public.estacoes e
set cheia_historica_cm = v.cheia_cm,
    cheia_historica_data = v.cheia_data,
    seca_historica_cm = v.seca_cm,
    seca_historica_data = v.seca_data,
    historico_fonte = v.fonte
from (
values
    ('13410000', 1950, date '1997-03-14', 256, date '1998-10-06', 'ANA HidroSerieHistorica 1990-2026, cotas diárias (cheia consistida, seca consistida; picos isolados > 150 cm descartados; régua conferida com telemetria em 30/06/2026: 444.5 x 446.6 cm)'),
    ('13870000', 2179, date '1997-04-13', 331.5, date '2024-10-02', 'ANA HidroSerieHistorica 1990-2026, cotas diárias (cheia consistida, seca bruta; picos isolados > 150 cm descartados; régua conferida com telemetria em 31/05/2026: 1773.5 x 1775.2 cm)'),
    ('13962000', 2288, date '2015-05-26', 391, date '2024-10-12', 'ANA HidroSerieHistorica 1990-2026, cotas diárias (cheia bruta, seca bruta; picos isolados > 150 cm descartados; régua conferida com telemetria em 30/04/2026: 2025.5 x 2025.5 cm)'),
    ('13990000', 2235.5, date '2015-06-24', 254, date '2024-10-11', 'ANA HidroSerieHistorica 1990-2026, cotas diárias (cheia bruta, seca bruta; picos isolados > 150 cm descartados; régua conferida com telemetria em 30/04/2026: 1926 x 1926.5 cm)')

) as v(codigo, cheia_cm, cheia_data, seca_cm, seca_data, fonte)
where e.codigo_oficial = v.codigo;

-- Alertas criados pelo robô apontam para a análise que os originou.
alter table public.alertas
    add column if not exists analise_id uuid references public.analises_risco(id);
create index if not exists alertas_analise on public.alertas (analise_id)
    where analise_id is not null;

grant select, insert on public.alertas to service_role;
grant select on public.analises_risco to service_role;
