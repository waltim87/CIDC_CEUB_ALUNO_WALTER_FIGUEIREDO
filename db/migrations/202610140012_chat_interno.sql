-- Chat interno da rede CIDC (voluntários e equipes).
--   municipio   -> canal geral de um município (quem tem acesso ao município participa)
--   comunidades -> une 1 ou mais comunidades, inclusive de municípios diferentes
--   privado     -> só as pessoas selecionadas por quem criou
-- Pesquisador não usa o chat. CPF digitado em mensagem é mascarado no banco (LGPD).

create table if not exists public.chat_canais (
    id uuid primary key default gen_random_uuid(),
    nome text not null check (length(trim(nome)) between 3 and 80),
    tipo text not null check (tipo in ('municipio', 'comunidades', 'privado')),
    municipio_id char(7) references public.municipios(id_ibge),
    comunidades uuid[] not null default '{}',
    descricao text check (descricao is null or length(descricao) <= 300),
    criado_por uuid references public.usuarios(id) on delete set null,
    criado_em timestamptz not null default now(),
    arquivado boolean not null default false,
    check (tipo <> 'municipio' or municipio_id is not null),
    check (tipo <> 'comunidades' or cardinality(comunidades) >= 1)
);
create unique index if not exists chat_canal_municipio_unico
    on public.chat_canais (municipio_id) where tipo = 'municipio';

create table if not exists public.chat_membros (
    canal_id uuid not null references public.chat_canais(id) on delete cascade,
    usuario_id uuid not null references public.usuarios(id) on delete cascade,
    adicionado_em timestamptz not null default now(),
    lido_ate timestamptz,
    primary key (canal_id, usuario_id)
);

create table if not exists public.chat_mensagens (
    id uuid primary key default gen_random_uuid(),
    canal_id uuid not null references public.chat_canais(id) on delete cascade,
    usuario_id uuid not null default public.cidc_usuario_id_atual() references public.usuarios(id) on delete cascade,
    autor_nome text not null default '',
    autor_perfil text not null default '',
    texto text not null check (length(trim(texto)) between 1 and 1000),
    criado_em timestamptz not null default now()
);
create index if not exists chat_mensagens_canal_idx on public.chat_mensagens (canal_id, criado_em desc);

alter table public.chat_canais enable row level security;
alter table public.chat_membros enable row level security;
alter table public.chat_mensagens enable row level security;

-- ------------------------------------------------------------ quem participa de um canal
create or replace function public.cidc_pode_usar_canal(p_canal_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_perfil_atual(), 'pesquisador') <> 'pesquisador'
       and exists (
           select 1 from public.chat_canais c
            where c.id = p_canal_id
              and (
                  (c.tipo = 'municipio' and public.cidc_pode_ver_municipio(c.municipio_id))
                  or (c.tipo = 'comunidades' and exists (
                        select 1 from public.comunidades co
                         where co.id = any(c.comunidades)
                           and public.cidc_pode_ver_municipio(co.municipio_id)))
                  or exists (select 1 from public.chat_membros m
                              where m.canal_id = c.id and m.usuario_id = public.cidc_usuario_id_atual())
              )
       )
$$;

drop policy if exists chat_canais_select on public.chat_canais;
create policy chat_canais_select on public.chat_canais
    for select to authenticated using (public.cidc_pode_usar_canal(id));

drop policy if exists chat_membros_select on public.chat_membros;
create policy chat_membros_select on public.chat_membros
    for select to authenticated using (public.cidc_pode_usar_canal(canal_id));
drop policy if exists chat_membros_sair on public.chat_membros;
create policy chat_membros_sair on public.chat_membros
    for delete to authenticated using (usuario_id = public.cidc_usuario_id_atual());
drop policy if exists chat_membros_lido on public.chat_membros;
create policy chat_membros_lido on public.chat_membros
    for update to authenticated
    using (usuario_id = public.cidc_usuario_id_atual())
    with check (usuario_id = public.cidc_usuario_id_atual());

drop policy if exists chat_mensagens_select on public.chat_mensagens;
create policy chat_mensagens_select on public.chat_mensagens
    for select to authenticated using (public.cidc_pode_usar_canal(canal_id));
drop policy if exists chat_mensagens_insert on public.chat_mensagens;
create policy chat_mensagens_insert on public.chat_mensagens
    for insert to authenticated
    with check (
        usuario_id = public.cidc_usuario_id_atual()
        and public.cidc_pode_usar_canal(canal_id)
        and not exists (select 1 from public.chat_canais c where c.id = canal_id and c.arquivado)
    );
drop policy if exists chat_mensagens_delete on public.chat_mensagens;
create policy chat_mensagens_delete on public.chat_mensagens
    for delete to authenticated
    using (usuario_id = public.cidc_usuario_id_atual() or public.cidc_administrador());

grant select on public.chat_canais to authenticated;
grant select, update (lido_ate), delete on public.chat_membros to authenticated;
grant select, insert, delete on public.chat_mensagens to authenticated;

-- CPF com dígitos verificadores válidos (telefone com 11 dígitos quase nunca passa).
create or replace function public.cidc_cpf_valido(p_digitos text)
returns boolean
language plpgsql
immutable
set search_path = pg_catalog, pg_temp
as $$
declare
    s int;
    dv int;
begin
    if p_digitos !~ '^\d{11}$' or p_digitos ~ '^(\d)\1{10}$' then
        return false;
    end if;
    for k in 9..10 loop
        s := 0;
        for i in 1..k loop
            s := s + substr(p_digitos, i, 1)::int * (k + 2 - i);
        end loop;
        dv := (s * 10) % 11 % 10;
        if dv <> substr(p_digitos, k + 1, 1)::int then
            return false;
        end if;
    end loop;
    return true;
end;
$$;

-- Autor gravado pelo banco (não dá para se passar por outra pessoa) e CPF mascarado.
create or replace function public.cidc_chat_preparar_mensagem()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    achado text;
    digitos text;
begin
    select u.nome, u.perfil into new.autor_nome, new.autor_perfil
      from public.usuarios u where u.id = new.usuario_id;
    new.texto := trim(new.texto);
    for achado in
        select (regexp_matches(new.texto, '\d{3}\.?\d{3}\.?\d{3}-?\d{2}', 'g'))[1]
    loop
        digitos := regexp_replace(achado, '\D', '', 'g');
        if public.cidc_cpf_valido(digitos) then
            new.texto := replace(new.texto, achado,
                substr(digitos, 1, 3) || '.***.***-' || substr(digitos, 10, 2));
        end if;
    end loop;
    if auth.uid() is not null then
        new.criado_em := now();   -- pelo app, a hora é sempre a do servidor
    end if;
    return new;
end;
$$;
drop trigger if exists chat_preparar_mensagem on public.chat_mensagens;
create trigger chat_preparar_mensagem before insert on public.chat_mensagens
    for each row execute function public.cidc_chat_preparar_mensagem();

-- ------------------------------------------------------------ criar canais
create or replace function public.cidc_chat_criar_canal(
    p_nome text,
    p_tipo text,
    p_municipio_id char(7) default null,
    p_comunidades uuid[] default '{}',
    p_membros uuid[] default '{}',
    p_descricao text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_eu uuid := public.cidc_usuario_id_atual();
    v_canal uuid;
begin
    if v_eu is null or coalesce(public.cidc_perfil_atual(), 'pesquisador') = 'pesquisador' then
        raise exception 'Seu perfil não usa o chat interno';
    end if;
    if p_tipo = 'municipio' then
        if not public.cidc_pode_ver_municipio(p_municipio_id) then
            raise exception 'Sem acesso a este município';
        end if;
        select id into v_canal from public.chat_canais where tipo = 'municipio' and municipio_id = p_municipio_id;
        if v_canal is null then
            insert into public.chat_canais (nome, tipo, municipio_id, criado_por)
            select 'Geral - ' || m.nome || '/' || m.uf, 'municipio', m.id_ibge, v_eu
              from public.municipios m where m.id_ibge = p_municipio_id
            returning id into v_canal;
        end if;
        return v_canal;
    elsif p_tipo = 'comunidades' then
        if coalesce(cardinality(p_comunidades), 0) = 0 then
            raise exception 'Selecione ao menos uma comunidade';
        end if;
        if exists (select 1 from unnest(p_comunidades) c(id)
                    where not exists (select 1 from public.comunidades co
                                       where co.id = c.id and public.cidc_pode_ver_municipio(co.municipio_id))) then
            raise exception 'Comunidade inválida ou sem acesso';
        end if;
    elsif p_tipo = 'privado' then
        if coalesce(cardinality(p_membros), 0) = 0 then
            raise exception 'Selecione ao menos uma pessoa';
        end if;
    else
        raise exception 'Tipo de canal inválido';
    end if;

    insert into public.chat_canais (nome, tipo, comunidades, descricao, criado_por)
    values (trim(p_nome), p_tipo, coalesce(p_comunidades, '{}'), nullif(trim(coalesce(p_descricao, '')), ''), v_eu)
    returning id into v_canal;
    insert into public.chat_membros (canal_id, usuario_id)
    select v_canal, u.id from public.usuarios u
     where u.id = v_eu or (u.id = any(p_membros) and u.perfil <> 'pesquisador')
    on conflict do nothing;
    return v_canal;
end;
$$;

-- Quem criou um canal privado pode incluir mais pessoas.
create or replace function public.cidc_chat_adicionar_membros(p_canal_id uuid, p_membros uuid[])
returns integer
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_total integer;
begin
    if not exists (select 1 from public.chat_canais
                    where id = p_canal_id and (criado_por = public.cidc_usuario_id_atual() or public.cidc_administrador())) then
        raise exception 'Só quem criou o canal pode incluir pessoas';
    end if;
    insert into public.chat_membros (canal_id, usuario_id)
    select p_canal_id, u.id from public.usuarios u where u.id = any(p_membros) and u.perfil <> 'pesquisador'
    on conflict do nothing;
    get diagnostics v_total = row_count;
    return v_total;
end;
$$;

-- Lista de pessoas para seleção: só nome, perfil e município (sem telefone, e-mail ou CPF).
create or replace function public.cidc_chat_pessoas()
returns table (id uuid, nome text, perfil text, municipio_id char(7))
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select u.id, u.nome, u.perfil, u.municipio_id
      from public.usuarios u
     where coalesce(public.cidc_perfil_atual(), 'pesquisador') <> 'pesquisador'
       and u.perfil <> 'pesquisador'
       and u.auth_id is not null
       and u.id <> public.cidc_usuario_id_atual()
       and (u.municipio_id is null or public.cidc_pode_ver_municipio(u.municipio_id))
     order by u.nome
$$;

revoke all on function public.cidc_pode_usar_canal(uuid) from public;
revoke all on function public.cidc_chat_criar_canal(text, text, char, uuid[], uuid[], text) from public;
revoke all on function public.cidc_chat_adicionar_membros(uuid, uuid[]) from public;
revoke all on function public.cidc_chat_pessoas() from public;
grant execute on function public.cidc_pode_usar_canal(uuid) to authenticated;
grant execute on function public.cidc_chat_criar_canal(text, text, char, uuid[], uuid[], text) to authenticated;
grant execute on function public.cidc_chat_adicionar_membros(uuid, uuid[]) to authenticated;
grant execute on function public.cidc_chat_pessoas() to authenticated;

-- Comunidades: todos que veem o município leem (necessário para escolher no chat).
drop policy if exists comunidades_chat_leitura on public.comunidades;
create policy comunidades_chat_leitura on public.comunidades
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
