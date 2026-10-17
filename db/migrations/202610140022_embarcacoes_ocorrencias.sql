-- Embarcações e equipes (resposta).
-- Cadastro de barcos (capacidade, piloto, combustível) e vínculo com as ocorrências.

create table if not exists public.embarcacoes (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nome text not null check (length(trim(nome)) between 3 and 100),
    tipo text not null check (tipo in ('lancha', 'balsa', 'canoa_motorizada', 'jet_ski', 'outro')),
    capacidade integer not null check (capacidade >= 1),
    piloto text check (piloto is null or length(piloto) between 3 and 100),
    telefone_piloto text check (telefone_piloto is null or length(telefone_piloto) <= 20),
    combustivel text check (combustivel is null or length(combustivel) <= 50),
    quantidade_combustivel numeric check (quantidade_combustivel is null or quantidade_combustivel >= 0),
    status text not null check (status in ('disponível', 'em_uso', 'manutencao', 'fora_de_servico')) default 'disponível',
    observacoes text check (observacoes is null or length(observacoes) <= 500),
    registrado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id) on delete set null,
    registrado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);
create index if not exists embarcacoes_municipio_idx on public.embarcacoes (municipio_id);
create index if not exists embarcacoes_status_idx on public.embarcacoes (status);

alter table public.embarcacoes enable row level security;

-- Leitura: quem vê o município vê as embarcações dele.
drop policy if exists embarcacoes_select on public.embarcacoes;
create policy embarcacoes_select on public.embarcacoes
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.embarcacoes to authenticated;

-- Escrita: coordenação, administração e logística do município.
create or replace function public.cidc_pode_gerenciar_embarcacao(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'administrador', 'logistica_abastecimento')), false)
$$;
revoke all on function public.cidc_pode_gerenciar_embarcacao(char) from public;
revoke all on function public.cidc_pode_gerenciar_embarcacao(char) from authenticated, anon;
grant execute on function public.cidc_pode_gerenciar_embarcacao(char) to authenticated;

drop policy if exists embarcacoes_gestao on public.embarcacoes;
create policy embarcacoes_gestao on public.embarcacoes
    for all to authenticated
    using (public.cidc_pode_gerenciar_embarcacao(municipio_id))
    with check (public.cidc_pode_gerenciar_embarcacao(municipio_id));
grant insert, update, delete on public.embarcacoes to authenticated;

-- Função para cadastrar/atualizar embarcação.
create or replace function public.cidc_embarcacao_cadastrar(
    p_id uuid default null,
    p_municipio_id char(7),
    p_nome text,
    p_tipo text,
    p_capacidade integer default null,
    p_piloto text default null,
    p_telefone_piloto text default null,
    p_combustivel text default null,
    p_quantidade_combustivel numeric default null,
    p_status text default 'disponível',
    p_observacoes text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_id uuid := coalesce(p_id, gen_random_uuid());
begin
    if not public.cidc_pode_gerenciar_embarcacao(p_municipio_id) then
        raise exception 'Só coordenação, administração ou logística gerencia embarcações';
    end if;
    insert into public.embarcacoes
        (id, municipio_id, nome, tipo, capacidade, piloto, telefone_piloto,
         combustivel, quantidade_combustivel, status, observacoes,
         registrado_por, registrado_em, atualizado_em)
    values (v_id, p_municipio_id, trim(p_nome), p_tipo, p_capacidade,
            nullif(trim(coalesce(p_piloto, '')), ''),
            nullif(trim(coalesce(p_telefone_piloto, '')), ''),
            nullif(trim(coalesce(p_combustivel, '')), ''),
            p_quantidade_combustivel, p_status,
            nullif(trim(coalesce(p_observacoes, '')), ''),
            public.cidc_usuario_id_atual(), now(), now())
    on conflict (id) do update set
        nome = excluded.nome,
        tipo = excluded.tipo,
        capacidade = excluded.capacidade,
        piloto = excluded.piloto,
        telefone_piloto = excluded.telefone_piloto,
        combustivel = excluded.combustivel,
        quantidade_combustivel = excluded.quantidade_combustivel,
        status = excluded.status,
        observacoes = excluded.observacoes,
        atualizado_em = now();
    return v_id;
end;
$$;
revoke all on function public.cidc_embarcacao_cadastrar(uuid, char, text, text, integer, text, text, text, numeric, text, text) from public;
revoke all on function public.cidc_embarcacao_cadastrar(uuid, char, text, text, integer, text, text, text, numeric, text, text) from authenticated, anon;
grant execute on function public.cidc_embarcacao_cadastrar(uuid, char, text, text, integer, text, text, text, numeric, text, text) to authenticated;

-- Vínculo embarcação ↔ ocorrência (uma ocorrência pode ter uma embarcação atribuída).
alter table public.ocorrencias
    add column if not exists embarcacao_id uuid references public.embarcacoes(id) on delete set null;
create index if not exists ocorrencias_embarcacao_idx on public.ocorrencias (embarcacao_id);

-- Função para atribuir embarcação a uma ocorrência.
create or replace function public.cidc_ocorrencia_atribuir_embarcacao(
    p_ocorrencia uuid,
    p_embarcacao_id uuid default null
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    o public.ocorrencias%rowtype;
    e public.embarcacoes%rowtype;
    v_municipio_id char(7);
begin
    select * into o from public.ocorrencias where id = p_ocorrencia for update;
    if o.id is null then
        raise exception 'Ocorrência não encontrada';
    end if;
    v_municipio_id := o.municipio_id;
    if not public.cidc_pode_ver_municipio(v_municipio_id) then
        raise exception 'Sem permissão para este município';
    end if;
    if p_embarcacao_id is not null then
        select * into e from public.embarcacoes where id = p_embarcacao_id for update;
        if e.id is null then
            raise exception 'Embarcação não encontrada';
        end if;
        if e.municipio_id <> v_municipio_id then
            raise exception 'Embarcação não pertence a este município';
        end if;
        if e.status <> 'disponível' then
            raise exception 'Embarcação já está em uso ou fora de serviço';
        end if;
        -- Libera a embarcação anterior da ocorrência, se houver
        if o.embarcacao_id is not null then
            update public.embarcacoes set status = 'disponível' where id = o.embarcacao_id;
        end if;
        update public.embarcacoes set status = 'em_uso' where id = p_embarcacao_id;
    elsif o.embarcacao_id is not null then
        -- Remove a embarcação da ocorrência
        update public.embarcacoes set status = 'disponível' where id = o.embarcacao_id;
    end if;
    update public.ocorrencias set embarcacao_id = p_embarcacao_id where id = p_ocorrencia;
    return 'ok';
end;
$$;
revoke all on function public.cidc_ocorrencia_atribuir_embarcacao(uuid, uuid) from public;
revoke all on function public.cidc_ocorrencia_atribuir_embarcacao(uuid, uuid) from authenticated, anon;
grant execute on function public.cidc_ocorrencia_atribuir_embarcacao(uuid, uuid) to authenticated;
