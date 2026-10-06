alter table public.indices
    add column if not exists explicacao_json jsonb not null default '[]'::jsonb,
    add column if not exists data_hora_leitura_referencia timestamptz,
    add column if not exists fontes_json jsonb not null default '[]'::jsonb;

alter table public.alertas
    add column if not exists regra_id uuid references public.regras(id);

alter table public.alertas
    drop constraint if exists alertas_status_check;

alter table public.alertas
    add constraint alertas_status_check
    check (status in ('rascunho', 'aprovado', 'rejeitado', 'enviado', 'encerrado'));

create unique index if not exists alertas_indice_regra_unico
    on public.alertas (indice_id, regra_id)
    where indice_id is not null and regra_id is not null;
