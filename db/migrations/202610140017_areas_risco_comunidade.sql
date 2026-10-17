-- Áreas de risco por comunidade (prevenção).
-- Cadastro de pontos críticos com tipo, casas/pessoas expostas, nível, foto e coordenadas.
-- Fonte de referência para o planejamento municipal de prevenção e mitigação.
-- Dados inseridos pela coordenação municipal ou administração; leitura conforme município.

create table if not exists public.areas_risco_comunidade (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    comunidade_id uuid references public.comunidades(id) on delete set null,
    nome text not null check (length(trim(nome)) between 3 and 200),
    tipo text not null check (tipo in (
        'inundacao', 'terras_caidas', 'erosao', 'deslizamento', 'incendio', 'outro')),
    nivel text not null check (nivel in ('baixo', 'medio', 'alto', 'critico')),
    casas integer check (casas is null or casas >= 0),
    pessoas integer check (pessoas is null or pessoas >= 0),
    descricao text check (descricao is null or length(descricao) <= 1000),
    latitude double precision check (latitude is null or latitude between -90 and 90),
    longitude double precision check (longitude is null or longitude between -180 and 180),
    caminho_foto text check (caminho_foto is null or length(caminho_foto) <= 500),
    registrado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id) on delete set null,
    registrado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);
create index if not exists areas_risco_municipio_idx on public.areas_risco_comunidade (municipio_id);
create index if not exists areas_risco_comunidade_idx on public.areas_risco_comunidade (comunidade_id);

alter table public.areas_risco_comunidade enable row level security;

-- Leitura: quem vê o município vê as áreas de risco dele.
drop policy if exists areas_risco_select on public.areas_risco_comunidade;
create policy areas_risco_select on public.areas_risco_comunidade
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.areas_risco_comunidade to authenticated;

-- Escrita: coordenação e administração do município criam/atualizam/excluem.
create or replace function public.cidc_pode_gerenciar_area_risco(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'administrador')), false)
$$;
revoke all on function public.cidc_pode_gerenciar_area_risco(char) from public;
revoke all on function public.cidc_pode_gerenciar_area_risco(char) from authenticated, anon;
grant execute on function public.cidc_pode_gerenciar_area_risco(char) to authenticated;

drop policy if exists areas_risco_gestao on public.areas_risco_comunidade;
create policy areas_risco_gestao on public.areas_risco_comunidade
    for all to authenticated
    using (public.cidc_pode_gerenciar_area_risco(municipio_id))
    with check (public.cidc_pode_gerenciar_area_risco(municipio_id));
grant insert, update, delete on public.areas_risco_comunidade to authenticated;

-- Função para cadastrar/atualizar uma área de risco (usa registro_por automático).
create or replace function public.cidc_area_risco_cadastrar(
    p_id uuid default null,
    p_municipio_id char(7),
    p_comunidade_id uuid default null,
    p_nome text,
    p_tipo text,
    p_nivel text,
    p_casas integer default null,
    p_pessoas integer default null,
    p_descricao text default null,
    p_latitude double precision default null,
    p_longitude double precision default null,
    p_caminho_foto text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_id uuid := coalesce(p_id, gen_random_uuid());
begin
    if not public.cidc_pode_gerenciar_area_risco(p_municipio_id) then
        raise exception 'Só a coordenação municipal ou a administração gerencia áreas de risco';
    end if;
    if p_comunidade_id is not null then
        if not exists (select 1 from public.comunidades c
                        where c.id = p_comunidade_id and c.municipio_id = p_municipio_id) then
            raise exception 'Comunidade não encontrada neste município';
        end if;
    end if;
    insert into public.areas_risco_comunidade
        (id, municipio_id, comunidade_id, nome, tipo, nivel, casas, pessoas, descricao,
         latitude, longitude, caminho_foto, registrado_por, registrado_em, atualizado_em)
    values (v_id, p_municipio_id, p_comunidade_id, trim(p_nome), p_tipo, p_nivel,
            p_casas, p_pessoas, nullif(trim(coalesce(p_descricao, '')), ''),
            p_latitude, p_longitude, nullif(trim(coalesce(p_caminho_foto, '')), ''),
            public.cidc_usuario_id_atual(), now(), now())
    on conflict (id) do update set
        comunidade_id = excluded.comunidade_id,
        nome = excluded.nome,
        tipo = excluded.tipo,
        nivel = excluded.nivel,
        casas = excluded.casas,
        pessoas = excluded.pessoas,
        descricao = excluded.descricao,
        latitude = excluded.latitude,
        longitude = excluded.longitude,
        caminho_foto = excluded.caminho_foto,
        atualizado_em = now();
    return v_id;
end;
$$;
revoke all on function public.cidc_area_risco_cadastrar(uuid, char, uuid, text, text, text, integer, integer, text, double precision, double precision, text) from public;
revoke all on function public.cidc_area_risco_cadastrar(uuid, char, uuid, text, text, text, integer, integer, text, double precision, double precision, text) from authenticated, anon;
grant execute on function public.cidc_area_risco_cadastrar(uuid, char, uuid, text, text, text, integer, integer, text, double precision, double precision, text) to authenticated;
