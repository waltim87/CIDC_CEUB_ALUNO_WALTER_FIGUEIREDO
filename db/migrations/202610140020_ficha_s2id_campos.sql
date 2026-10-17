-- Ficha S2iD (resposta): campos adicionais em pessoas_afetadas para o rascunho
-- oficial do S2iD (sistema federal): óbitos informados, danos a casas e
-- instalações. Cada registro fica vinculado a uma comunidade e a uma data.

alter table public.pessoas_afetadas
    add column if not exists obitos integer check (obitos is null or obitos >= 0),
    add column if not exists danos_casas integer check (danos_casas is null or danos_casas >= 0),
    add column if not exists danos_instalacoes text check (danos_instalacoes is null or length(danos_instalacoes) <= 500),
    add column if not exists fonte_afetados text check (fonte_afetados is null or length(fonte_afetados) <= 200),
    add column if not exists atualizado_em timestamptz not null default now();

-- Índice para consultas por comunidade e data.
create index if not exists pessoas_afetadas_comunidade_data_idx
    on public.pessoas_afetadas (comunidade_id, data desc);

-- Função para cadastrar/atualizar a ficha de afetados de uma comunidade.
create or replace function public.cidc_pessoas_afetadas_cadastrar(
    p_comunidade_id uuid,
    p_data date,
    p_familias integer default null,
    p_pessoas integer default null,
    p_desalojados integer default null,
    p_desabrigados integer default null,
    p_obitos integer default null,
    p_danos_casas integer default null,
    p_danos_instalacoes text default null,
    p_necessidades jsonb default null,
    p_fonte_afetados text default null,
    p_observacoes text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_comunidade record;
    v_id uuid := gen_random_uuid();
    v_existente uuid;
begin
    select c.id, c.municipio_id into v_comunidade
      from public.comunidades c where c.id = p_comunidade_id;
    if v_comunidade.id is null then
        raise exception 'Comunidade não encontrada';
    end if;
    if not public.cidc_pode_registrar_afetados(v_comunidade.municipio_id) then
        raise exception 'Só quem pode registrar afetados do município pode editar esta ficha';
    end if;

    -- Se já existe registro para esta comunidade e data, atualiza em vez de duplicar.
    select id into v_existente
      from public.pessoas_afetadas
     where comunidade_id = p_comunidade_id and data = p_data
     limit 1;

    if v_existente is not null then
        update public.pessoas_afetadas
           set familias = coalesce(p_familias, familias),
               pessoas = coalesce(p_pessoas, pessoas),
               desalojados = coalesce(p_desalojados, desalojados),
               desabrigados = coalesce(p_desabrigados, desabrigados),
               obitos = coalesce(p_obitos, obitos),
               danos_casas = coalesce(p_danos_casas, danos_casas),
               danos_instalacoes = coalesce(nullif(trim(coalesce(p_danos_instalacoes, '')), ''), danos_instalacoes),
               necessidades = coalesce(p_necessidades, necessidades),
               fonte_afetados = coalesce(nullif(trim(coalesce(p_fonte_afetados, '')), ''), fonte_afetados),
               observacoes = coalesce(nullif(trim(coalesce(p_observacoes, '')), ''), observacoes),
               atualizado_em = now()
         where id = v_existente;
        return v_existente;
    end if;

    insert into public.pessoas_afetadas
        (comunidade_id, data, familias, pessoas, desalojados, desabrigados,
         obitos, danos_casas, danos_instalacoes, necessidades, fonte_afetados,
         observacoes, criado_em, atualizado_em)
    values (p_comunidade_id, p_data, p_familias, p_pessoas, p_desalojados,
            p_desabrigados, p_obitos, p_danos_casas,
            nullif(trim(coalesce(p_danos_instalacoes, '')), ''),
            p_necessidades, nullif(trim(coalesce(p_fonte_afetados, '')), ''),
            nullif(trim(coalesce(p_observacoes, '')), ''), now(), now())
    returning id into v_id;
    return v_id;
end;
$$;
revoke all on function public.cidc_pessoas_afetadas_cadastrar(uuid, date, integer, integer, integer, integer, integer, integer, text, jsonb, text, text) from public;
revoke all on function public.cidc_pessoas_afetadas_cadastrar(uuid, date, integer, integer, integer, integer, integer, integer, text, jsonb, text, text) from authenticated, anon;
grant execute on function public.cidc_pessoas_afetadas_cadastrar(uuid, date, integer, integer, integer, integer, integer, integer, text, jsonb, text, text) to authenticated;
