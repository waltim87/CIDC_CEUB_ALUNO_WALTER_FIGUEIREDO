-- Checklist de abrigo pronto (preparação).
-- Vistoria periódica dos abrigos: água, energia, banheiros, cozinha,
-- acessibilidade, kits e colchões. Gera selo "pronto" e avisa quando
-- a vistoria tem mais de 90 dias.

create table if not exists public.abrigo_vistorias (
    id uuid primary key default gen_random_uuid(),
    abrigo_id uuid not null references public.abrigos(id) on delete cascade,
    municipio_id char(7) not null references public.municipios(id_ibge),
    vistoriado_por uuid not null references public.usuarios(id) on delete set null,
    data_vistoria date not null default current_date,
    agua boolean not null default false,
    energia boolean not null default false,
    banheiros boolean not null default false,
    cozinha boolean not null default false,
    acessibilidade boolean not null default false,
    kits boolean not null default false,
    colchoes boolean not null default false,
    selo_pronto boolean not null default false,
    observacoes text check (observacoes is null or length(observacoes) <= 1000),
    criado_em timestamptz not null default now()
);
create index if not exists abrigo_vistorias_abrigo_idx on public.abrigo_vistorias (abrigo_id, data_vistoria desc);
create index if not exists abrigo_vistorias_municipio_idx on public.abrigo_vistorias (municipio_id, data_vistoria desc);

alter table public.abrigo_vistorias enable row level security;

-- Leitura: quem vê o município vê as vistorias dos abrigos dele.
drop policy if exists abrigo_vistorias_select on public.abrigo_vistorias;
create policy abrigo_vistorias_select on public.abrigo_vistorias
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.abrigo_vistorias to authenticated;

-- Escrita: coordenação municipal e administração do município (e coordenador do abrigo).
create or replace function public.cidc_pode_vistoriar_abrigo(p_municipio_id char(7), p_abrigo_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'administrador')), false)
        or (p_abrigo_id is not null and public.cidc_coordena_abrigo(p_abrigo_id))
$$;
revoke all on function public.cidc_pode_vistoriar_abrigo(char, uuid) from public;
revoke all on function public.cidc_pode_vistoriar_abrigo(char, uuid) from authenticated, anon;
grant execute on function public.cidc_pode_vistoriar_abrigo(char, uuid) to authenticated;

drop policy if exists abrigo_vistorias_gestao on public.abrigo_vistorias;
create policy abrigo_vistorias_gestao on public.abrigo_vistorias
    for all to authenticated
    using (public.cidc_pode_vistoriar_abrigo(municipio_id, abrigo_id))
    with check (public.cidc_pode_vistoriar_abrigo(municipio_id, abrigo_id));
grant insert, update, delete on public.abrigo_vistorias to authenticated;

-- Função para registrar uma vistoria (calcula selo_pronto: todos os itens verdadeiros).
create or replace function public.cidc_abrigo_vistoria_registrar(
    p_abrigo_id uuid,
    p_agua boolean default false,
    p_energia boolean default false,
    p_banheiros boolean default false,
    p_cozinha boolean default false,
    p_acessibilidade boolean default false,
    p_kits boolean default false,
    p_colchoes boolean default false,
    p_observacao text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_abrigo record;
    v_selo boolean;
    v_id uuid := gen_random_uuid();
begin
    select a.id, a.municipio_id into v_abrigo
      from public.abrigos a where a.id = p_abrigo_id;
    if v_abrigo.id is null then
        raise exception 'Abrigo não encontrado';
    end if;
    if not public.cidc_pode_vistoriar_abrigo(v_abrigo.municipio_id, p_abrigo_id) then
        raise exception 'Só a coordenação, a administração ou o coordenador do abrigo vistoria';
    end if;
    v_selo := p_agua and p_energia and p_banheiros and p_cozinha
        and p_acessibilidade and p_kits and p_colchoes;
    insert into public.abrigo_vistorias
        (id, abrigo_id, municipio_id, vistoriado_por, data_vistoria,
         agua, energia, banheiros, cozinha, acessibilidade, kits, colchoes,
         selo_pronto, observacoes)
    values (v_id, p_abrigo_id, v_abrigo.municipio_id, public.cidc_usuario_id_atual(),
            current_date, p_agua, p_energia, p_banheiros, p_cozinha,
            p_acessibilidade, p_kits, p_colchoes, v_selo,
            nullif(trim(coalesce(p_observacao, '')), ''))
    returning id into v_id;
    return v_id;
end;
$$;
revoke all on function public.cidc_abrigo_vistoria_registrar(uuid, boolean, boolean, boolean, boolean, boolean, boolean, boolean, text) from public;
revoke all on function public.cidc_abrigo_vistoria_registrar(uuid, boolean, boolean, boolean, boolean, boolean, boolean, boolean, text) from authenticated, anon;
grant execute on function public.cidc_abrigo_vistoria_registrar(uuid, boolean, boolean, boolean, boolean, boolean, boolean, boolean, text) to authenticated;

-- View: vistoria mais recente de cada abrigo e se está vencida (> 90 dias).
create or replace view public.abrigo_vistoria_recente
with (security_invoker = true) as
select abrigo_id, max(data_vistoria) as ultima_vistoria,
       max(selo_pronto) filter (where data_vistoria = max(data_vistoria)) as selo_pronto,
       case when max(data_vistoria) is null then null
            when max(data_vistoria) < current_date - interval '90 days' then true
            else false end as vistoria_vencida
  from public.abrigo_vistorias
 group by abrigo_id;
grant select on public.abrigo_vistoria_recente to authenticated;
