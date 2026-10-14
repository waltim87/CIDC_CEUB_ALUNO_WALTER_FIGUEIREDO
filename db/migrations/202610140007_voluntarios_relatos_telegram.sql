-- Voluntários (autocadastro com termo de responsabilidade), relatos colaborativos
-- tipo "Waze" (chuva, rio baixando/subindo, cheia, incêndio/fumaça) e envio
-- automático de alertas aprovados pelo Telegram (core/telegram_robo.py).

-- ------------------------------------------------------------ perfil voluntário
-- Voluntário lê tudo (como gestor nacional), mas não opera nem aprova alertas.
create or replace function public.cidc_pode_ver_municipio(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_perfil_atual() in (
            'gestor_nacional',
            'administrador',
            'voluntario'
        )
        or (
            public.cidc_perfil_atual() = 'gestor_estadual'
            and exists (
                select 1
                from public.municipios municipio_atribuido
                join public.municipios municipio_alvo
                  on municipio_alvo.id_ibge = p_municipio_id
                where municipio_atribuido.id_ibge = public.cidc_municipio_atual()
                  and municipio_atribuido.uf = municipio_alvo.uf
            )
        )
        or (
            public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'agente_campo',
                'saude_assistencia',
                'logistica_abastecimento'
            )
            and public.cidc_municipio_atual() = p_municipio_id
        )
$$;

-- Estações e leituras: voluntário também lê as estações sem município.
drop policy if exists estacoes_select_perfis on public.estacoes;
create policy estacoes_select_perfis on public.estacoes
    for select to authenticated
    using (
        (municipio_id is not null and (
            public.cidc_pode_ver_municipio(municipio_id)
            or public.cidc_perfil_atual() = 'operador_monitoramento'))
        or (municipio_id is null and (
            public.cidc_gestor_global() or public.cidc_perfil_atual() = 'voluntario'))
    );

-- ------------------------------------------------------------ voluntários
create table if not exists public.voluntarios (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null unique references public.usuarios(id) on delete cascade,
    nome text not null,
    telefone text,
    municipio_id char(7) not null references public.municipios(id_ibge),
    habilidades text[] not null default '{}',
    possui_embarcacao boolean not null default false,
    disponibilidade text,
    termo_versao text not null,
    termo_aceito_em timestamptz not null,
    telegram_codigo text not null unique default substr(md5(gen_random_uuid()::text), 1, 12),
    telegram_chat_id text,
    ativo boolean not null default true,
    criado_em timestamptz not null default now()
);
alter table public.voluntarios enable row level security;

drop policy if exists voluntarios_select on public.voluntarios;
create policy voluntarios_select on public.voluntarios
    for select to authenticated
    using (
        usuario_id = public.cidc_usuario_id_atual()
        or public.cidc_pode_operar_municipio(municipio_id)
    );
drop policy if exists voluntarios_update on public.voluntarios;
create policy voluntarios_update on public.voluntarios
    for update to authenticated
    using (usuario_id = public.cidc_usuario_id_atual() or public.cidc_pode_operar_municipio(municipio_id))
    with check (usuario_id = public.cidc_usuario_id_atual() or public.cidc_pode_operar_municipio(municipio_id));
grant select, update on public.voluntarios to authenticated;

-- Autocadastro: cria o perfil "voluntario" para a conta logada, exige o aceite do termo.
create or replace function public.cidc_cadastrar_voluntario(
    p_nome text,
    p_telefone text,
    p_municipio_id char(7),
    p_habilidades text[],
    p_possui_embarcacao boolean,
    p_disponibilidade text,
    p_termo_versao text,
    p_aceite boolean
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_usuario_id uuid;
    v_perfil text;
    v_codigo text;
begin
    if auth.uid() is null then
        raise exception 'É preciso estar autenticado para se cadastrar como voluntário';
    end if;
    if not coalesce(p_aceite, false) then
        raise exception 'É obrigatório aceitar o termo de responsabilidade';
    end if;
    if length(trim(coalesce(p_nome, ''))) < 3 then
        raise exception 'Informe o nome completo';
    end if;
    if not exists (select 1 from public.municipios where id_ibge = p_municipio_id) then
        raise exception 'Município inválido';
    end if;

    select id, perfil into v_usuario_id, v_perfil from public.usuarios where auth_id = auth.uid();
    if v_usuario_id is null then
        insert into public.usuarios (nome, perfil, municipio_id, auth_id)
        values (trim(p_nome), 'voluntario', p_municipio_id, auth.uid())
        returning id into v_usuario_id;
    elsif v_perfil <> 'voluntario' then
        raise exception 'Esta conta já tem o perfil %; o cadastro de voluntário é para contas novas', v_perfil;
    end if;

    insert into public.voluntarios (
        usuario_id, nome, telefone, municipio_id, habilidades, possui_embarcacao,
        disponibilidade, termo_versao, termo_aceito_em
    ) values (
        v_usuario_id, trim(p_nome), nullif(trim(coalesce(p_telefone, '')), ''), p_municipio_id,
        coalesce(p_habilidades, '{}'), coalesce(p_possui_embarcacao, false),
        nullif(trim(coalesce(p_disponibilidade, '')), ''), p_termo_versao, now()
    )
    on conflict (usuario_id) do update set
        nome = excluded.nome, telefone = excluded.telefone, municipio_id = excluded.municipio_id,
        habilidades = excluded.habilidades, possui_embarcacao = excluded.possui_embarcacao,
        disponibilidade = excluded.disponibilidade, termo_versao = excluded.termo_versao,
        termo_aceito_em = now()
    returning telegram_codigo into v_codigo;
    return v_codigo;
end;
$$;
revoke all on function public.cidc_cadastrar_voluntario(text, text, char, text[], boolean, text, text, boolean) from public;
grant execute on function public.cidc_cadastrar_voluntario(text, text, char, text[], boolean, text, text, boolean) to authenticated;

-- ------------------------------------------------------------ relatos colaborativos
create table if not exists public.relatos (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default public.cidc_usuario_id_atual() references public.usuarios(id),
    municipio_id char(7) not null references public.municipios(id_ibge),
    tipo text not null check (tipo in (
        'chuva_forte', 'rio_baixando', 'rio_subindo', 'cheia_alagamento',
        'incendio_fumaca', 'isolamento_comunidade', 'outro')),
    intensidade text not null default 'moderada' check (intensidade in ('fraca', 'moderada', 'forte')),
    descricao text,
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    status text not null default 'novo' check (status in ('novo', 'confirmado', 'descartado')),
    confirmacoes integer not null default 0,
    negacoes integer not null default 0,
    criado_em timestamptz not null default now()
);
create index if not exists relatos_recentes on public.relatos (criado_em desc);

create table if not exists public.relato_votos (
    relato_id uuid not null references public.relatos(id) on delete cascade,
    usuario_id uuid not null default public.cidc_usuario_id_atual() references public.usuarios(id),
    confirma boolean not null,
    criado_em timestamptz not null default now(),
    primary key (relato_id, usuario_id)
);

alter table public.relatos enable row level security;
alter table public.relato_votos enable row level security;

drop policy if exists relatos_select_perfis on public.relatos;
create policy relatos_select_perfis on public.relatos
    for select to authenticated using (public.cidc_perfil_atual() is not null);
drop policy if exists relatos_select_publico on public.relatos;
create policy relatos_select_publico on public.relatos
    for select to anon using (status = 'confirmado');
drop policy if exists relatos_insert_proprio on public.relatos;
create policy relatos_insert_proprio on public.relatos
    for insert to authenticated
    with check (public.cidc_perfil_atual() is not null and usuario_id = public.cidc_usuario_id_atual());
drop policy if exists relatos_moderacao on public.relatos;
create policy relatos_moderacao on public.relatos
    for update to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));

drop policy if exists votos_select on public.relato_votos;
create policy votos_select on public.relato_votos
    for select to authenticated using (public.cidc_perfil_atual() is not null);
drop policy if exists votos_insert_proprio on public.relato_votos;
create policy votos_insert_proprio on public.relato_votos
    for insert to authenticated
    with check (public.cidc_perfil_atual() is not null and usuario_id = public.cidc_usuario_id_atual());

grant select, insert, update on public.relatos to authenticated;
grant select on public.relatos to anon;
grant select, insert on public.relato_votos to authenticated;

-- Contagem de votos; 3 confirmações de outras pessoas confirmam, 3 negações descartam.
create or replace function public.cidc_contar_voto_relato()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_autor uuid;
begin
    select usuario_id into v_autor from public.relatos where id = new.relato_id;
    if v_autor = new.usuario_id then
        raise exception 'O autor não pode votar no próprio relato';
    end if;
    update public.relatos r set
        confirmacoes = r.confirmacoes + case when new.confirma then 1 else 0 end,
        negacoes = r.negacoes + case when new.confirma then 0 else 1 end,
        status = case
            when r.status <> 'novo' then r.status
            when new.confirma and r.confirmacoes + 1 >= 3 then 'confirmado'
            when not new.confirma and r.negacoes + 1 >= 3 then 'descartado'
            else r.status end
    where r.id = new.relato_id;
    return new;
end;
$$;
drop trigger if exists relato_votos_contagem on public.relato_votos;
create trigger relato_votos_contagem after insert on public.relato_votos
    for each row execute function public.cidc_contar_voto_relato();

-- ------------------------------------------------------------ Telegram automático
grant select, insert, update on public.assinaturas_alerta to service_role;
grant select, insert on public.entregas_alerta to service_role;
grant select, update on public.alertas to service_role;
grant select, update on public.voluntarios to service_role;
grant select on public.relatos to service_role;
