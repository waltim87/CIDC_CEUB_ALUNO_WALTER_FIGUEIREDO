-- Responsáveis por área (matriz de atribuição) e ligação com as outras áreas.
--   responsaveis_area: quem é o TITULAR e o SUPLENTE de cada área em cada município
--   (coordenação, monitoramento, campo, saúde, assistência, logística, abrigos, embarcações,
--   comunicação, voluntários, obras, áreas de risco, recuperação, registro no S2iD).
-- Ligações automáticas:
--   - Tarefa do plano/manual com função e sem pessoa  -> vai para o titular da área da função.
--   - Ocorrência que recebe equipe e não tem pessoa   -> vai para o titular da área da equipe.
--   - Tarefas e ocorrências guardam o NOME do responsável (quem não pode ler a tabela de
--     usuários, como os voluntários, vê o nome sem acessar dados pessoais).
-- Pode ser uma pessoa com conta no CIDC ou alguém sem conta (ex.: secretário de saúde), com
-- telefone institucional opcional. Não cadastre telefone pessoal sem consentimento (LGPD).

create table if not exists public.responsaveis_area (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    area text not null check (area in (
        'coordenacao_geral', 'monitoramento_alerta', 'campo_vistorias', 'saude', 'assistencia_social',
        'logistica_estoque', 'abrigos', 'embarcacoes_transporte', 'comunicacao_populacao', 'voluntarios',
        'obras_mitigacao', 'areas_risco', 'recuperacao_retorno', 's2id_registro')),
    papel text not null default 'titular' check (papel in ('titular', 'suplente')),
    usuario_id uuid references public.usuarios(id) on delete set null,
    nome_exibicao text not null check (length(trim(nome_exibicao)) between 3 and 120),
    contato_institucional text check (contato_institucional is null or length(contato_institucional) <= 120),
    desde date not null default current_date,
    ate date,
    observacao text check (observacao is null or length(observacao) <= 300),
    atribuido_por uuid references public.usuarios(id) on delete set null,
    atribuido_em timestamptz not null default now(),
    check (ate is null or ate >= desde)
);
-- Um titular e um suplente ativos por área e município.
create unique index if not exists responsaveis_area_ativo_unico
    on public.responsaveis_area (municipio_id, area, papel) where ate is null;
create index if not exists responsaveis_area_usuario_idx on public.responsaveis_area (usuario_id) where ate is null;

alter table public.responsaveis_area enable row level security;
drop policy if exists responsaveis_area_select on public.responsaveis_area;
create policy responsaveis_area_select on public.responsaveis_area
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.responsaveis_area to authenticated;
-- Escrita só pelas funções abaixo.

-- Área de cada função (perfil) usada nas tarefas e ocorrências.
create or replace function public.cidc_area_da_funcao(p_funcao text)
returns text language sql immutable
set search_path = pg_catalog, pg_temp
as $$
    select case p_funcao
        when 'coordenador_municipal' then 'coordenacao_geral'
        when 'operador_monitoramento' then 'monitoramento_alerta'
        when 'agente_campo' then 'campo_vistorias'
        when 'saude_assistencia' then 'saude'
        when 'logistica_abastecimento' then 'logistica_estoque'
        when 'voluntario' then 'voluntarios'
    end
$$;

-- Titular ativo (com conta no CIDC) de uma área; se não houver, o suplente.
create or replace function public.cidc_responsavel_da_area(p_municipio_id char(7), p_area text)
returns table (usuario_id uuid, nome text)
language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select r.usuario_id, r.nome_exibicao
      from public.responsaveis_area r
     where r.municipio_id = p_municipio_id and r.area = p_area and r.ate is null and r.usuario_id is not null
     order by (r.papel = 'titular') desc
     limit 1
$$;

-- Definir (ou trocar) o responsável de uma área: encerra o anterior do mesmo papel.
create or replace function public.cidc_responsavel_area_definir(
    p_municipio_id char(7),
    p_area text,
    p_papel text default 'titular',
    p_usuario_id uuid default null,
    p_nome_externo text default null,
    p_contato text default null,
    p_observacao text default null
)
returns uuid
language plpgsql security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_nome text;
    v_id uuid;
begin
    if not public.cidc_pode_operar_municipio(p_municipio_id) then
        raise exception 'Só a coordenação municipal ou a administração define os responsáveis';
    end if;
    if p_usuario_id is not null then
        select nome into v_nome from public.usuarios
         where id = p_usuario_id and (municipio_id = p_municipio_id or perfil in ('administrador', 'gestor_estadual'));
        if v_nome is null then
            raise exception 'A pessoa escolhida não é deste município';
        end if;
    else
        v_nome := nullif(trim(coalesce(p_nome_externo, '')), '');
        if v_nome is null or length(v_nome) < 3 then
            raise exception 'Escolha uma pessoa com conta ou informe o nome completo';
        end if;
    end if;
    update public.responsaveis_area set ate = current_date
     where municipio_id = p_municipio_id and area = p_area and papel = coalesce(p_papel, 'titular') and ate is null;
    insert into public.responsaveis_area (municipio_id, area, papel, usuario_id, nome_exibicao,
                                          contato_institucional, observacao, atribuido_por)
    values (p_municipio_id, p_area, coalesce(p_papel, 'titular'), p_usuario_id, v_nome,
            nullif(trim(coalesce(p_contato, '')), ''), nullif(trim(coalesce(p_observacao, '')), ''),
            public.cidc_usuario_id_atual())
    returning id into v_id;
    return v_id;
end;
$$;

create or replace function public.cidc_responsavel_area_encerrar(p_id uuid)
returns void language plpgsql security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_municipio char(7);
begin
    select municipio_id into v_municipio from public.responsaveis_area where id = p_id and ate is null;
    if v_municipio is null then
        raise exception 'Atribuição não encontrada ou já encerrada';
    end if;
    if not public.cidc_pode_operar_municipio(v_municipio) then
        raise exception 'Só a coordenação municipal ou a administração encerra atribuições';
    end if;
    update public.responsaveis_area set ate = current_date where id = p_id;
end;
$$;

revoke all on function public.cidc_responsavel_da_area(char, text) from public, anon;
revoke all on function public.cidc_responsavel_area_definir(char, text, text, uuid, text, text, text) from public, anon;
revoke all on function public.cidc_responsavel_area_encerrar(uuid) from public, anon;
grant execute on function public.cidc_responsavel_da_area(char, text) to authenticated;
grant execute on function public.cidc_responsavel_area_definir(char, text, text, uuid, text, text, text) to authenticated;
grant execute on function public.cidc_responsavel_area_encerrar(uuid) to authenticated;

-- ------------------------------------------------------------ ligação: tarefas
alter table public.acoes add column if not exists responsavel_nome text;

create or replace function public.cidc_acoes_responsavel_da_area()
returns trigger language plpgsql security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    r record;
begin
    if new.responsavel_id is null and new.responsavel_funcao is not null then
        select * into r from public.cidc_responsavel_da_area(new.municipio_id, public.cidc_area_da_funcao(new.responsavel_funcao));
        if r.usuario_id is not null then
            new.responsavel_id := r.usuario_id;
        end if;
    end if;
    if new.responsavel_id is distinct from (case when tg_op = 'UPDATE' then old.responsavel_id end)
       or new.responsavel_nome is null then
        select nome into new.responsavel_nome from public.usuarios where id = new.responsavel_id;
    end if;
    return new;
end;
$$;
drop trigger if exists acoes_responsavel_da_area on public.acoes;
-- Nome com "z" para rodar depois de acoes_preencher (que define o município).
create trigger acoes_z_responsavel_da_area before insert or update of responsavel_id, responsavel_funcao on public.acoes
    for each row execute function public.cidc_acoes_responsavel_da_area();

-- ------------------------------------------------------------ ligação: ocorrências
create or replace function public.cidc_ocorrencia_responsavel_da_area()
returns trigger language plpgsql security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    r record;
begin
    if new.responsavel_id is null and new.equipe_funcao is not null
       and new.equipe_funcao is distinct from (case when tg_op = 'UPDATE' then old.equipe_funcao end) then
        select * into r from public.cidc_responsavel_da_area(new.municipio_id, public.cidc_area_da_funcao(new.equipe_funcao));
        if r.usuario_id is not null then
            new.responsavel_id := r.usuario_id;
            new.responsavel_nome := r.nome;
        end if;
    end if;
    return new;
end;
$$;
drop trigger if exists ocorrencia_responsavel_da_area on public.ocorrencias;
create trigger ocorrencia_responsavel_da_area before insert or update of equipe_funcao on public.ocorrencias
    for each row execute function public.cidc_ocorrencia_responsavel_da_area();

revoke all on function public.cidc_acoes_responsavel_da_area() from public, authenticated, anon;
revoke all on function public.cidc_ocorrencia_responsavel_da_area() from public, authenticated, anon;

-- Preenche o nome nas tarefas que já existem.
update public.acoes a set responsavel_nome = u.nome
  from public.usuarios u where u.id = a.responsavel_id and a.responsavel_nome is null;
