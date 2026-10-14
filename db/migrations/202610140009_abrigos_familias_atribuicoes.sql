-- Atribuição de coordenadores de abrigo e cadastro de famílias abrigadas
-- (nomes completos, CPF, parentesco, situação do imóvel e fotos).
-- DADOS PESSOAIS SENSÍVEIS (LGPD): acesso restrito a quem atende a família —
-- coordenador do abrigo, coordenação municipal, assistência social do município e
-- administração. Voluntários NÃO leem estas tabelas (mesmo com leitura geral do painel).

-- ------------------------------------------------------------ coordenadores de abrigo
create table if not exists public.abrigo_responsaveis (
    abrigo_id uuid not null references public.abrigos(id) on delete cascade,
    usuario_id uuid not null references public.usuarios(id) on delete cascade,
    funcao text not null default 'coordenador' check (funcao in ('coordenador', 'apoio')),
    criado_em timestamptz not null default now(),
    criado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id),
    primary key (abrigo_id, usuario_id)
);
alter table public.abrigo_responsaveis enable row level security;

create or replace function public.cidc_coordena_abrigo(p_abrigo_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select exists (
        select 1 from public.abrigo_responsaveis r
        where r.abrigo_id = p_abrigo_id and r.usuario_id = public.cidc_usuario_id_atual()
    )
$$;

-- Quem pode ver/gravar famílias de um abrigo.
create or replace function public.cidc_pode_atender_familias(p_municipio_id char(7), p_abrigo_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (public.cidc_perfil_atual() in ('coordenador_municipal', 'saude_assistencia')
            and public.cidc_municipio_atual() = p_municipio_id)
        or (p_abrigo_id is not null and public.cidc_coordena_abrigo(p_abrigo_id))
$$;
revoke all on function public.cidc_coordena_abrigo(uuid) from public;
revoke all on function public.cidc_pode_atender_familias(char, uuid) from public;
grant execute on function public.cidc_coordena_abrigo(uuid) to authenticated;
grant execute on function public.cidc_pode_atender_familias(char, uuid) to authenticated;

-- Designação: administrador ou coordenação municipal do município do abrigo.
drop policy if exists responsaveis_select on public.abrigo_responsaveis;
create policy responsaveis_select on public.abrigo_responsaveis
    for select to authenticated using (public.cidc_perfil_atual() is not null);
drop policy if exists responsaveis_gestao on public.abrigo_responsaveis;
create policy responsaveis_gestao on public.abrigo_responsaveis
    for all to authenticated
    using (exists (select 1 from public.abrigos a where a.id = abrigo_id
                   and public.cidc_pode_gerenciar_abrigo(a.municipio_id)))
    with check (exists (select 1 from public.abrigos a where a.id = abrigo_id
                        and public.cidc_pode_gerenciar_abrigo(a.municipio_id)));
grant select, insert, delete on public.abrigo_responsaveis to authenticated;

-- Coordenador do abrigo atualiza a ocupação do seu abrigo.
drop policy if exists abrigos_coordenador_atualiza on public.abrigos;
create policy abrigos_coordenador_atualiza on public.abrigos
    for update to authenticated
    using (public.cidc_coordena_abrigo(id))
    with check (public.cidc_coordena_abrigo(id));

-- Para a lista de pessoas que podem ser designadas, coordenação vê os usuários do município.
drop policy if exists usuarios_coordenacao_ve_municipio on public.usuarios;
create policy usuarios_coordenacao_ve_municipio on public.usuarios
    for select to authenticated
    using (public.cidc_perfil_atual() = 'coordenador_municipal' and municipio_id = public.cidc_municipio_atual());

-- ------------------------------------------------------------ famílias abrigadas
create table if not exists public.familias_abrigadas (
    id uuid primary key default gen_random_uuid(),
    abrigo_id uuid references public.abrigos(id) on delete set null,
    municipio_id char(7) not null references public.municipios(id_ibge),
    responsavel_nome text not null check (length(trim(responsavel_nome)) >= 5),
    responsavel_cpf char(11) not null check (responsavel_cpf ~ '^[0-9]{11}$'),
    telefone text,
    endereco_origem text,
    comunidade_id uuid references public.comunidades(id),
    situacao_imovel text not null check (situacao_imovel in
        ('destruido', 'parcialmente_destruido', 'danificado', 'interditado', 'alagado', 'sem_dano')),
    data_entrada date not null default current_date,
    data_saida date,
    necessidades text[] not null default '{}',
    observacoes text,
    consentimento_lgpd boolean not null check (consentimento_lgpd),
    registrado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id),
    criado_em timestamptz not null default now()
);
create unique index if not exists familias_cpf_ativo
    on public.familias_abrigadas (responsavel_cpf) where data_saida is null;

create table if not exists public.membros_familia (
    id uuid primary key default gen_random_uuid(),
    familia_id uuid not null references public.familias_abrigadas(id) on delete cascade,
    nome_completo text not null check (length(trim(nome_completo)) >= 5),
    cpf char(11) check (cpf is null or cpf ~ '^[0-9]{11}$'),
    sem_cpf_motivo text,
    parentesco text not null check (parentesco in (
        'cônjuge/companheiro(a)', 'filho(a)', 'enteado(a)', 'pai/mãe', 'avô/avó', 'neto(a)',
        'irmão/irmã', 'sogro(a)', 'genro/nora', 'tio(a)', 'sobrinho(a)', 'primo(a)', 'outro parente', 'agregado')),
    data_nascimento date,
    necessidades_especiais text,
    -- Pessoa desaparecida: último dia e local em que foi vista; "encontrado_em" encerra a busca.
    desaparecido boolean not null default false,
    visto_por_ultimo_em date,
    ultimo_local_visto text,
    encontrado_em date,
    constraint membro_cpf_ou_motivo check (cpf is not null or length(trim(coalesce(sem_cpf_motivo, ''))) > 0),
    constraint desaparecido_com_data_local check (
        not desaparecido or (visto_por_ultimo_em is not null and length(trim(coalesce(ultimo_local_visto, ''))) > 0))
);
create index if not exists membros_desaparecidos on public.membros_familia (familia_id)
    where desaparecido and encontrado_em is null;

create table if not exists public.fotos_familia (
    id uuid primary key default gen_random_uuid(),
    familia_id uuid not null references public.familias_abrigadas(id) on delete cascade,
    caminho text not null unique,          -- bucket fotos-familias: <municipio>/<familia>/<arquivo>
    descricao text,
    criado_em timestamptz not null default now()
);

alter table public.familias_abrigadas enable row level security;
alter table public.membros_familia enable row level security;
alter table public.fotos_familia enable row level security;

drop policy if exists familias_acesso on public.familias_abrigadas;
create policy familias_acesso on public.familias_abrigadas
    for all to authenticated
    using (public.cidc_pode_atender_familias(municipio_id, abrigo_id))
    with check (public.cidc_pode_atender_familias(municipio_id, abrigo_id));

drop policy if exists membros_acesso on public.membros_familia;
create policy membros_acesso on public.membros_familia
    for all to authenticated
    using (exists (select 1 from public.familias_abrigadas f where f.id = familia_id
                   and public.cidc_pode_atender_familias(f.municipio_id, f.abrigo_id)))
    with check (exists (select 1 from public.familias_abrigadas f where f.id = familia_id
                        and public.cidc_pode_atender_familias(f.municipio_id, f.abrigo_id)));

drop policy if exists fotos_acesso on public.fotos_familia;
create policy fotos_acesso on public.fotos_familia
    for all to authenticated
    using (exists (select 1 from public.familias_abrigadas f where f.id = familia_id
                   and public.cidc_pode_atender_familias(f.municipio_id, f.abrigo_id)))
    with check (exists (select 1 from public.familias_abrigadas f where f.id = familia_id
                        and public.cidc_pode_atender_familias(f.municipio_id, f.abrigo_id)));

grant select, insert, update, delete on public.familias_abrigadas, public.membros_familia, public.fotos_familia
    to authenticated;

-- ------------------------------------------------------------ fotos (Storage privado)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('fotos-familias', 'fotos-familias', false, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Caminho <municipio>/<familia>/<arquivo>: acesso igual ao da família.
create or replace function public.cidc_pode_acessar_foto(p_caminho text)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select exists (
        select 1 from public.familias_abrigadas f
        where f.id::text = split_part(p_caminho, '/', 2)
          and f.municipio_id = split_part(p_caminho, '/', 1)
          and public.cidc_pode_atender_familias(f.municipio_id, f.abrigo_id)
    )
$$;
revoke all on function public.cidc_pode_acessar_foto(text) from public;
grant execute on function public.cidc_pode_acessar_foto(text) to authenticated;

drop policy if exists fotos_familias_leitura on storage.objects;
create policy fotos_familias_leitura on storage.objects
    for select to authenticated
    using (bucket_id = 'fotos-familias' and public.cidc_pode_acessar_foto(name));
drop policy if exists fotos_familias_envio on storage.objects;
create policy fotos_familias_envio on storage.objects
    for insert to authenticated
    with check (bucket_id = 'fotos-familias' and public.cidc_pode_acessar_foto(name));
drop policy if exists fotos_familias_exclusao on storage.objects;
create policy fotos_familias_exclusao on storage.objects
    for delete to authenticated
    using (bucket_id = 'fotos-familias' and public.cidc_pode_acessar_foto(name));
