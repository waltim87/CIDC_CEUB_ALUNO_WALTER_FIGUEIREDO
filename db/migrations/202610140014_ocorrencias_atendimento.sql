-- Ocorrências com atendimento: o relato (ou chamado) vira um CASO com equipe responsável,
-- prioridade e linha do tempo até "resolvida".
--   aberta -> atribuida -> em_deslocamento -> em_atendimento -> resolvida   (ou cancelada)
-- Todas as mudanças passam pela função cidc_ocorrencia_atualizar, que confere a permissão e
-- grava o evento na linha do tempo (quem, quando, o quê).

create table if not exists public.ocorrencias (
    id uuid primary key default gen_random_uuid(),
    numero bigint generated always as identity,
    municipio_id char(7) not null references public.municipios(id_ibge),
    relato_id uuid references public.relatos(id) on delete set null,
    tipo text not null check (tipo in (
        'resgate', 'cheia_alagamento', 'isolamento_comunidade', 'incendio_fumaca', 'saude',
        'abastecimento', 'desabamento_erosao', 'outro')),
    prioridade text not null default 'media' check (prioridade in ('baixa', 'media', 'alta', 'critica')),
    titulo text not null check (length(trim(titulo)) between 5 and 120),
    descricao text check (descricao is null or length(descricao) <= 1000),
    local_descricao text check (local_descricao is null or length(local_descricao) <= 300),
    latitude double precision check (latitude is null or latitude between -90 and 90),
    longitude double precision check (longitude is null or longitude between -180 and 180),
    pessoas_envolvidas integer check (pessoas_envolvidas is null or pessoas_envolvidas between 0 and 100000),
    status text not null default 'aberta' check (status in (
        'aberta', 'atribuida', 'em_deslocamento', 'em_atendimento', 'resolvida', 'cancelada')),
    equipe_funcao text check (equipe_funcao is null or equipe_funcao in (
        'coordenador_municipal', 'operador_monitoramento', 'agente_campo', 'saude_assistencia',
        'logistica_abastecimento', 'voluntario')),
    responsavel_id uuid references public.usuarios(id) on delete set null,
    responsavel_nome text,
    aberta_por uuid references public.usuarios(id) on delete set null,
    aberta_em timestamptz not null default now(),
    atribuida_em timestamptz,
    resolvida_em timestamptz,
    resultado text check (resultado is null or length(resultado) <= 1000)
);
create index if not exists ocorrencias_municipio_idx on public.ocorrencias (municipio_id, status, aberta_em desc);
create unique index if not exists ocorrencias_relato_unico on public.ocorrencias (relato_id) where relato_id is not null;

create table if not exists public.ocorrencia_eventos (
    id uuid primary key default gen_random_uuid(),
    ocorrencia_id uuid not null references public.ocorrencias(id) on delete cascade,
    usuario_id uuid references public.usuarios(id) on delete set null,
    autor_nome text not null default '',
    status_novo text,
    texto text not null,
    criado_em timestamptz not null default now()
);
create index if not exists ocorrencia_eventos_idx on public.ocorrencia_eventos (ocorrencia_id, criado_em);

alter table public.ocorrencias enable row level security;
alter table public.ocorrencia_eventos enable row level security;

-- Quem vê o município vê as ocorrências (voluntários leem tudo, como no restante do painel).
drop policy if exists ocorrencias_select on public.ocorrencias;
create policy ocorrencias_select on public.ocorrencias
    for select to authenticated
    using (public.cidc_pode_ver_municipio(municipio_id) or responsavel_id = public.cidc_usuario_id_atual());
drop policy if exists ocorrencia_eventos_select on public.ocorrencia_eventos;
create policy ocorrencia_eventos_select on public.ocorrencia_eventos
    for select to authenticated
    using (exists (select 1 from public.ocorrencias o where o.id = ocorrencia_id
                    and (public.cidc_pode_ver_municipio(o.municipio_id) or o.responsavel_id = public.cidc_usuario_id_atual())));
grant select on public.ocorrencias, public.ocorrencia_eventos to authenticated;

-- Equipes do município (e administração) abrem ocorrências.
create or replace function public.cidc_pode_abrir_ocorrencia(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'operador_monitoramento', 'agente_campo',
                                               'saude_assistencia', 'logistica_abastecimento'))
$$;

create or replace function public.cidc_ocorrencia_evento(p_ocorrencia uuid, p_status text, p_texto text)
returns void
language sql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    insert into public.ocorrencia_eventos (ocorrencia_id, usuario_id, autor_nome, status_novo, texto)
    select p_ocorrencia, u.id, coalesce(u.nome, 'sistema'), p_status, p_texto
      from (select 1) x left join public.usuarios u on u.id = public.cidc_usuario_id_atual();
$$;

create or replace function public.cidc_ocorrencia_abrir(
    p_municipio_id char(7),
    p_tipo text,
    p_prioridade text,
    p_titulo text,
    p_descricao text default null,
    p_local text default null,
    p_latitude double precision default null,
    p_longitude double precision default null,
    p_pessoas integer default null,
    p_relato_id uuid default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_id uuid;
    v_relato record;
begin
    if not public.cidc_pode_abrir_ocorrencia(p_municipio_id) then
        raise exception 'Só as equipes do município abrem ocorrências (voluntários registram relatos)';
    end if;
    if p_relato_id is not null then
        select * into v_relato from public.relatos where id = p_relato_id;
        if v_relato.id is null or v_relato.municipio_id <> p_municipio_id then
            raise exception 'Relato inválido para este município';
        end if;
        if exists (select 1 from public.ocorrencias where relato_id = p_relato_id) then
            raise exception 'Este relato já virou uma ocorrência';
        end if;
    end if;
    insert into public.ocorrencias (municipio_id, relato_id, tipo, prioridade, titulo, descricao, local_descricao,
                                    latitude, longitude, pessoas_envolvidas, aberta_por)
    values (p_municipio_id, p_relato_id, p_tipo, coalesce(p_prioridade, 'media'), trim(p_titulo),
            nullif(trim(coalesce(p_descricao, '')), ''), nullif(trim(coalesce(p_local, '')), ''),
            coalesce(p_latitude, v_relato.latitude), coalesce(p_longitude, v_relato.longitude),
            p_pessoas, public.cidc_usuario_id_atual())
    returning id into v_id;
    perform public.cidc_ocorrencia_evento(v_id, 'aberta',
        case when p_relato_id is null then 'Ocorrência aberta' else 'Ocorrência aberta a partir de um relato de campo' end);
    return v_id;
end;
$$;

-- Uma função para tudo: atribuir equipe/pessoa, avançar a situação, mudar prioridade, anotar.
--   Coordenação/admin: tudo.
--   Responsável (pessoa) ou alguém da equipe atribuída, no município: assumir, avançar, anotar.
create or replace function public.cidc_ocorrencia_atualizar(
    p_ocorrencia uuid,
    p_status text default null,
    p_texto text default null,
    p_equipe text default null,
    p_responsavel uuid default null,
    p_prioridade text default null,
    p_assumir boolean default false
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    o public.ocorrencias%rowtype;
    v_eu uuid := public.cidc_usuario_id_atual();
    v_coord boolean;
    v_equipe boolean;
    v_nome text;
    v_partes text[] := '{}';
begin
    select * into o from public.ocorrencias where id = p_ocorrencia for update;
    if o.id is null then
        raise exception 'Ocorrência não encontrada';
    end if;
    -- Encerrada: só aceita anotação, ou reabertura pela coordenação.
    if o.status in ('resolvida', 'cancelada') and p_status is distinct from 'aberta'
       and (p_status is not null or p_equipe is not null or p_responsavel is not null
            or p_prioridade is not null or p_assumir) then
        raise exception 'Ocorrência encerrada; a coordenação pode reabrir';
    end if;
    -- coalesce: comparação com valor vazio (sem responsável) dá NULL, e "not NULL" não barraria.
    v_coord := coalesce(public.cidc_pode_operar_municipio(o.municipio_id), false);
    v_equipe := coalesce(o.responsavel_id = v_eu, false)
        or coalesce(o.equipe_funcao = public.cidc_perfil_atual()
                    and public.cidc_municipio_atual() = o.municipio_id, false);

    if p_assumir then
        if not (v_coord or coalesce(public.cidc_municipio_atual() = o.municipio_id
                and public.cidc_perfil_atual() in ('agente_campo', 'saude_assistencia', 'logistica_abastecimento',
                                                   'operador_monitoramento', 'voluntario'), false)) then
            raise exception 'Só equipes e voluntários do município podem assumir';
        end if;
        select nome into v_nome from public.usuarios where id = v_eu;
        update public.ocorrencias set responsavel_id = v_eu, responsavel_nome = v_nome,
               equipe_funcao = coalesce(equipe_funcao, public.cidc_perfil_atual()),
               status = case when status = 'aberta' then 'atribuida' else status end,
               atribuida_em = coalesce(atribuida_em, now())
         where id = o.id;
        perform public.cidc_ocorrencia_evento(o.id, 'atribuida', v_nome || ' assumiu a ocorrência'
            || coalesce(': ' || nullif(trim(coalesce(p_texto, '')), ''), ''));
        return 'assumida';
    end if;

    if (p_equipe is not null or p_responsavel is not null or p_prioridade is not null
        or p_status in ('cancelada', 'aberta')) and not v_coord then
        raise exception 'Só a coordenação municipal atribui equipes, muda prioridade, cancela ou reabre';
    end if;
    if not (v_coord or v_equipe) then
        raise exception 'Você não é responsável por esta ocorrência';
    end if;

    if p_equipe is not null then
        update public.ocorrencias set equipe_funcao = p_equipe,
               status = case when status = 'aberta' then 'atribuida' else status end,
               atribuida_em = coalesce(atribuida_em, now()) where id = o.id;
        v_partes := v_partes || ('Equipe: ' || p_equipe);
    end if;
    if p_responsavel is not null then
        select nome into v_nome from public.usuarios where id = p_responsavel
           and (municipio_id = o.municipio_id or perfil = 'administrador');
        if v_nome is null then
            raise exception 'Responsável precisa ser do município da ocorrência';
        end if;
        update public.ocorrencias set responsavel_id = p_responsavel, responsavel_nome = v_nome,
               status = case when status = 'aberta' then 'atribuida' else status end,
               atribuida_em = coalesce(atribuida_em, now()) where id = o.id;
        v_partes := v_partes || ('Responsável: ' || v_nome);
    end if;
    if p_prioridade is not null then
        update public.ocorrencias set prioridade = p_prioridade where id = o.id;
        v_partes := v_partes || ('Prioridade: ' || p_prioridade);
    end if;
    if p_status is not null and p_status <> o.status then
        update public.ocorrencias set status = p_status,
               resolvida_em = case when p_status in ('resolvida', 'cancelada') then now() end,
               resultado = case when p_status in ('resolvida', 'cancelada')
                                then coalesce(nullif(trim(coalesce(p_texto, '')), ''), resultado) else resultado end,
               atribuida_em = case when p_status <> 'aberta' then coalesce(atribuida_em, now()) end
         where id = o.id;
    end if;
    if p_status is not null or p_texto is not null or cardinality(v_partes) > 0 then
        perform public.cidc_ocorrencia_evento(o.id, p_status,
            coalesce(nullif(array_to_string(v_partes, ' · '), '') || coalesce(' — ' || nullif(trim(coalesce(p_texto, '')), ''), ''),
                     nullif(trim(coalesce(p_texto, '')), ''), 'Situação: ' || p_status));
    end if;
    return 'ok';
end;
$$;

revoke all on function public.cidc_pode_abrir_ocorrencia(char) from public;
revoke all on function public.cidc_ocorrencia_evento(uuid, text, text) from public;
revoke all on function public.cidc_ocorrencia_evento(uuid, text, text) from authenticated, anon;
revoke all on function public.cidc_ocorrencia_abrir(char, text, text, text, text, text, double precision, double precision, integer, uuid) from public;
revoke all on function public.cidc_ocorrencia_atualizar(uuid, text, text, text, uuid, text, boolean) from public;
grant execute on function public.cidc_pode_abrir_ocorrencia(char) to authenticated;
grant execute on function public.cidc_ocorrencia_abrir(char, text, text, text, text, text, double precision, double precision, integer, uuid) to authenticated;
grant execute on function public.cidc_ocorrencia_atualizar(uuid, text, text, text, uuid, text, boolean) to authenticated;
