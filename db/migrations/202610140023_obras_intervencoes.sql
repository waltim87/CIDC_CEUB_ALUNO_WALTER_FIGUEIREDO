-- Obras e intervenções (mitigação).
-- Cadastro de obras com status, valor, fonte do recurso e comunidades beneficiadas.
-- Indicador: quantas pessoas saíram da área de risco com cada ação.

create table if not exists public.obras_intervencoes (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nome text not null check (length(trim(nome)) between 5 and 200),
    descricao text check (descricao is null or length(descricao) <= 1000),
    tipo text not null check (tipo in (
        'contencao_margem', 'eleve_casas', 'poço', 'ponte', 'outro')),
    status text not null check (status in (
        'planejada', 'em_andamento', 'concluida', 'cancelada', 'suspensa')) default 'planejada',
    valor numeric check (valor is null or valor >= 0),
    fonte_recurso text check (fonte_recurso is null or length(fonte_recurso) <= 200),
    comunidades_beneficiadas text[] not null default '{}',
    pessoas_retiradas_risco integer check (pessoas_retiradas_risco is null or pessoas_retiradas_risco >= 0),
    data_inicio date,
    data_previsao_termino date,
    data_termino date,
    responsavel text check (responsavel is null or length(responsavel) <= 200),
    observacoes text check (observacoes is null or length(observacoes) <= 1000),
    registrado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id) on delete set null,
    registrado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);
create index if not exists obras_intervencoes_municipio_idx on public.obras_intervencoes (municipio_id);
create index if not exists obras_intervencoes_status_idx on public.obras_intervencoes (status);

alter table public.obras_intervencoes enable row level security;

-- Leitura: quem vê o município vê as obras dele.
drop policy if exists obras_intervencoes_select on public.obras_intervencoes;
create policy obras_intervencoes_select on public.obras_intervencoes
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.obras_intervencoes to authenticated;

-- Escrita: coordenação e administração do município.
create or replace function public.cidc_pode_gerenciar_obra(p_municipio_id char(7))
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
revoke all on function public.cidc_pode_gerenciar_obra(char) from public;
revoke all on function public.cidc_pode_gerenciar_obra(char) from authenticated, anon;
grant execute on function public.cidc_pode_gerenciar_obra(char) to authenticated;

drop policy if exists obras_intervencoes_gestao on public.obras_intervencoes;
create policy obras_intervencoes_gestao on public.obras_intervencoes
    for all to authenticated
    using (public.cidc_pode_gerenciar_obra(municipio_id))
    with check (public.cidc_pode_gerenciar_obra(municipio_id));
grant insert, update, delete on public.obras_intervencoes to authenticated;

-- Função para cadastrar/atualizar obra.
-- Obrigatórios primeiro (Postgres não aceita parâmetro sem default depois de um com default).
-- O app chama pelo NOME dos parâmetros, então a ordem não importa para ele.
-- Remove as versões que podem ter ficado de tentativas anteriores.
drop function if exists public.cidc_obra_cadastrar(char, text, text, text, text, numeric, text, text[], integer, date, date, date, text, text);
drop function if exists public.cidc_obra_cadastrar(uuid, char, text, text, text, text, numeric, text, text[], integer, date, date, date, text, text);

create or replace function public.cidc_obra_cadastrar(
    p_municipio_id char(7),
    p_nome text,
    p_tipo text,
    p_id uuid default null,
    p_descricao text default null,
    p_status text default 'planejada',
    p_valor numeric default null,
    p_fonte_recurso text default null,
    p_comunidades_beneficiadas text[] default null,
    p_pessoas_retiradas_risco integer default null,
    p_data_inicio date default null,
    p_data_previsao_termino date default null,
    p_data_termino date default null,
    p_responsavel text default null,
    p_observacoes text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_id uuid := coalesce(p_id, gen_random_uuid());
    v_salvo uuid;
begin
    if not public.cidc_pode_gerenciar_obra(p_municipio_id) then
        raise exception 'Só coordenação ou administração gerencia obras';
    end if;
    insert into public.obras_intervencoes
        (id, municipio_id, nome, descricao, tipo, status, valor, fonte_recurso,
         comunidades_beneficiadas, pessoas_retiradas_risco, data_inicio,
         data_previsao_termino, data_termino, responsavel, observacoes,
         registrado_por, registrado_em, atualizado_em)
    values (v_id, p_municipio_id, trim(p_nome), nullif(trim(coalesce(p_descricao, '')), ''),
            p_tipo, coalesce(p_status, 'planejada'), p_valor, nullif(trim(coalesce(p_fonte_recurso, '')), ''),
            coalesce(p_comunidades_beneficiadas, '{}'), p_pessoas_retiradas_risco, p_data_inicio,
            p_data_previsao_termino, p_data_termino,
            nullif(trim(coalesce(p_responsavel, '')), ''),
            nullif(trim(coalesce(p_observacoes, '')), ''),
            public.cidc_usuario_id_atual(), now(), now())
    on conflict (id) do update set
        nome = excluded.nome,
        descricao = excluded.descricao,
        tipo = excluded.tipo,
        status = excluded.status,
        valor = excluded.valor,
        fonte_recurso = excluded.fonte_recurso,
        comunidades_beneficiadas = excluded.comunidades_beneficiadas,
        pessoas_retiradas_risco = excluded.pessoas_retiradas_risco,
        data_inicio = excluded.data_inicio,
        data_previsao_termino = excluded.data_previsao_termino,
        data_termino = excluded.data_termino,
        responsavel = excluded.responsavel,
        observacoes = excluded.observacoes,
        atualizado_em = now()
    -- Só atualiza obra do MESMO município que a pessoa pode gerenciar
    -- (sem isso, dava para sobrescrever a obra de outro município pelo id).
    where public.obras_intervencoes.municipio_id = excluded.municipio_id
    returning id into v_salvo;
    if v_salvo is null then
        raise exception 'Obra não encontrada neste município';
    end if;
    return v_salvo;
end;
$$;
revoke all on function public.cidc_obra_cadastrar(char, text, text, uuid, text, text, numeric, text, text[], integer, date, date, date, text, text) from public;
revoke all on function public.cidc_obra_cadastrar(char, text, text, uuid, text, text, numeric, text, text[], integer, date, date, date, text, text) from anon;
grant execute on function public.cidc_obra_cadastrar(char, text, text, uuid, text, text, numeric, text, text[], integer, date, date, date, text, text) to authenticated;
