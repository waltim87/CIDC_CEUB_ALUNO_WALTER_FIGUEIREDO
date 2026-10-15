-- Ajuda humanitária: estoque por movimentos (entradas e saídas) e entregas a famílias
-- abrigadas e a comunidades, com baixa automática e aviso de entrega repetida.
--   saldo = soma dos movimentos do município por item (nunca fica negativo)
--   entrega à família: quem atende famílias (coordenação, saúde/assistência, coordenador do
--   abrigo) e a logística; entrega à comunidade: logística e coordenação.
-- Nome e CPF das famílias continuam protegidos pela RLS de familias_abrigadas.

create table if not exists public.ajuda_movimentos (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    item text not null check (item in (
        'cesta_basica', 'agua_potavel', 'kit_higiene', 'kit_limpeza', 'colchao', 'rede', 'cobertor',
        'roupas', 'kit_dormitorio', 'filtro_agua', 'hipoclorito', 'racao_animal', 'combustivel', 'outro')),
    quantidade numeric(12, 2) not null check (quantidade <> 0),   -- + entrada, - saída
    motivo text not null check (motivo in (
        'doacao', 'compra', 'envio_estadual', 'envio_federal', 'transferencia',
        'entrega_familia', 'entrega_comunidade', 'entrega_abrigo', 'perda', 'ajuste')),
    origem_destino text check (origem_destino is null or length(origem_destino) <= 200),
    familia_id uuid references public.familias_abrigadas(id) on delete set null,
    comunidade_id uuid references public.comunidades(id) on delete set null,
    abrigo_id uuid references public.abrigos(id) on delete set null,
    pessoas_atendidas integer check (pessoas_atendidas is null or pessoas_atendidas >= 0),
    entrega_id uuid,                       -- agrupa os itens de uma mesma entrega
    justificativa_repeticao text,
    observacao text check (observacao is null or length(observacao) <= 500),
    registrado_por uuid default public.cidc_usuario_id_atual() references public.usuarios(id) on delete set null,
    registrado_em timestamptz not null default now(),
    check ((motivo in ('doacao', 'compra', 'envio_estadual', 'envio_federal', 'transferencia') and quantidade > 0)
        or (motivo in ('entrega_familia', 'entrega_comunidade', 'entrega_abrigo', 'perda') and quantidade < 0)
        or motivo = 'ajuste')
);
create index if not exists ajuda_movimentos_municipio_idx on public.ajuda_movimentos (municipio_id, item);
create index if not exists ajuda_movimentos_familia_idx on public.ajuda_movimentos (familia_id, registrado_em desc)
    where familia_id is not null;

alter table public.ajuda_movimentos enable row level security;

create or replace function public.cidc_pode_movimentar_estoque(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'logistica_abastecimento')), false)
$$;

-- Leitura: quem vê o município vê o estoque e as entregas (sem nome de família: isso fica na
-- tabela de famílias, com RLS própria).
drop policy if exists ajuda_select on public.ajuda_movimentos;
create policy ajuda_select on public.ajuda_movimentos
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.ajuda_movimentos to authenticated;
-- Escrita só pelas funções abaixo (conferem saldo, permissão e repetição).

create or replace view public.ajuda_saldo
with (security_invoker = true) as
select municipio_id, item, sum(quantidade) as saldo, max(registrado_em) as ultimo_movimento
  from public.ajuda_movimentos
 group by municipio_id, item;
grant select on public.ajuda_saldo to authenticated;

create or replace function public.cidc_saldo_item(p_municipio_id char(7), p_item text)
returns numeric
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(sum(quantidade), 0) from public.ajuda_movimentos
     where municipio_id = p_municipio_id and item = p_item
$$;

-- ------------------------------------------------------------ entrada / perda / ajuste
create or replace function public.cidc_estoque_movimentar(
    p_municipio_id char(7),
    p_item text,
    p_quantidade numeric,
    p_motivo text,
    p_origem_destino text default null,
    p_observacao text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_id uuid;
    v_qtd numeric := p_quantidade;
begin
    if not public.cidc_pode_movimentar_estoque(p_municipio_id) then
        raise exception 'Só a logística ou a coordenação do município movimenta o estoque';
    end if;
    if p_motivo not in ('doacao', 'compra', 'envio_estadual', 'envio_federal', 'transferencia', 'perda', 'ajuste') then
        raise exception 'Use a entrega a família/comunidade para registrar saídas de ajuda';
    end if;
    if coalesce(p_quantidade, 0) = 0 then
        raise exception 'Informe a quantidade';
    end if;
    if p_motivo = 'perda' then
        v_qtd := -abs(p_quantidade);
    elsif p_motivo <> 'ajuste' then
        v_qtd := abs(p_quantidade);
    end if;
    perform pg_advisory_xact_lock(hashtext(p_municipio_id || p_item));
    if public.cidc_saldo_item(p_municipio_id, p_item) + v_qtd < 0 then
        raise exception 'Saldo insuficiente de %: há % no estoque', p_item, public.cidc_saldo_item(p_municipio_id, p_item);
    end if;
    insert into public.ajuda_movimentos (municipio_id, item, quantidade, motivo, origem_destino, observacao)
    values (p_municipio_id, p_item, v_qtd, p_motivo, nullif(trim(coalesce(p_origem_destino, '')), ''),
            nullif(trim(coalesce(p_observacao, '')), ''))
    returning id into v_id;
    return v_id;
end;
$$;

-- ------------------------------------------------------------ entregas
-- p_itens: {"cesta_basica": 1, "agua_potavel": 20}. Confere o saldo de todos antes de baixar.
-- Família que recebeu o mesmo item há menos de p_janela_dias: exige justificativa.
create or replace function public.cidc_ajuda_entregar(
    p_municipio_id char(7),
    p_itens jsonb,
    p_familia_id uuid default null,
    p_comunidade_id uuid default null,
    p_abrigo_id uuid default null,
    p_pessoas integer default null,
    p_justificativa text default null,
    p_observacao text default null,
    p_janela_dias integer default 7
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_familia record;
    v_motivo text;
    v_abrigo uuid := p_abrigo_id;
    v_entrega uuid := gen_random_uuid();
    v_item text;
    v_qtd numeric;
    v_repetidos text[] := '{}';
    v_destino text;
begin
    if num_nonnulls(p_familia_id, p_comunidade_id, p_abrigo_id) = 0 then
        raise exception 'Informe a família, a comunidade ou o abrigo que recebe';
    end if;
    if p_itens is null or jsonb_typeof(p_itens) <> 'object' or p_itens = '{}'::jsonb then
        raise exception 'Informe os itens entregues';
    end if;

    if p_familia_id is not null then
        select id, municipio_id, abrigo_id, data_saida into v_familia
          from public.familias_abrigadas where id = p_familia_id;
        if v_familia.id is null or v_familia.municipio_id <> p_municipio_id then
            raise exception 'Família não encontrada neste município';
        end if;
        if not (coalesce(public.cidc_pode_atender_familias(p_municipio_id, v_familia.abrigo_id), false)
                or public.cidc_pode_movimentar_estoque(p_municipio_id)) then
            raise exception 'Sem permissão para registrar entrega a famílias deste município';
        end if;
        v_motivo := 'entrega_familia';
        v_abrigo := coalesce(v_abrigo, v_familia.abrigo_id);
        select array_agg(distinct m.item) into v_repetidos
          from public.ajuda_movimentos m
         where m.familia_id = p_familia_id and m.motivo = 'entrega_familia'
           and m.item in (select jsonb_object_keys(p_itens))
           and m.registrado_em > now() - make_interval(days => p_janela_dias);
        if coalesce(cardinality(v_repetidos), 0) > 0 and length(trim(coalesce(p_justificativa, ''))) < 5 then
            raise exception 'REPETIDA: esta família já recebeu % nos últimos % dias. Informe a justificativa para entregar de novo',
                array_to_string(v_repetidos, ', '), p_janela_dias;
        end if;
    else
        if not public.cidc_pode_movimentar_estoque(p_municipio_id) then
            raise exception 'Só a logística ou a coordenação registra entregas a comunidades e abrigos';
        end if;
        if p_comunidade_id is not null then
            if not exists (select 1 from public.comunidades where id = p_comunidade_id and municipio_id = p_municipio_id) then
                raise exception 'Comunidade não encontrada neste município';
            end if;
            v_motivo := 'entrega_comunidade';
        else
            v_motivo := 'entrega_abrigo';
        end if;
    end if;
    if v_abrigo is not null and not exists (select 1 from public.abrigos where id = v_abrigo and municipio_id = p_municipio_id) then
        raise exception 'Abrigo não encontrado neste município';
    end if;

    -- Confere todos os saldos antes de baixar qualquer item (tudo ou nada).
    for v_item, v_qtd in select key, value::numeric from jsonb_each_text(p_itens) loop
        if v_qtd is null or v_qtd <= 0 then
            raise exception 'Quantidade inválida para %', v_item;
        end if;
        perform pg_advisory_xact_lock(hashtext(p_municipio_id || v_item));
        if public.cidc_saldo_item(p_municipio_id, v_item) < v_qtd then
            raise exception 'Saldo insuficiente de %: há % no estoque', v_item, public.cidc_saldo_item(p_municipio_id, v_item);
        end if;
    end loop;

    for v_item, v_qtd in select key, value::numeric from jsonb_each_text(p_itens) loop
        insert into public.ajuda_movimentos (municipio_id, item, quantidade, motivo, familia_id, comunidade_id,
                                             abrigo_id, pessoas_atendidas, entrega_id, justificativa_repeticao, observacao)
        values (p_municipio_id, v_item, -v_qtd, v_motivo, p_familia_id, p_comunidade_id, v_abrigo, p_pessoas,
                v_entrega, case when coalesce(cardinality(v_repetidos), 0) > 0 then trim(p_justificativa) end,
                nullif(trim(coalesce(p_observacao, '')), ''));
    end loop;
    return jsonb_build_object('entrega_id', v_entrega, 'repetidos', coalesce(to_jsonb(v_repetidos), '[]'::jsonb));
end;
$$;

-- Famílias abrigadas (ainda no abrigo) e a última entrega de cada item — para ver quem
-- está sem receber. Só devolve as famílias que a pessoa já pode ver (RLS de familias_abrigadas).
create or replace view public.ajuda_cobertura_familias
with (security_invoker = true) as
select f.id as familia_id, f.municipio_id, f.abrigo_id, f.data_entrada,
       max(m.registrado_em) filter (where m.item = 'cesta_basica') as ultima_cesta,
       max(m.registrado_em) filter (where m.item = 'kit_higiene') as ultimo_kit_higiene,
       max(m.registrado_em) filter (where m.item = 'agua_potavel') as ultima_agua,
       max(m.registrado_em) as ultima_entrega,
       count(distinct m.entrega_id) as entregas
  from public.familias_abrigadas f
  left join public.ajuda_movimentos m on m.familia_id = f.id and m.motivo = 'entrega_familia'
 where f.data_saida is null
 group by f.id, f.municipio_id, f.abrigo_id, f.data_entrada;
grant select on public.ajuda_cobertura_familias to authenticated;

revoke all on function public.cidc_pode_movimentar_estoque(char) from public;
revoke all on function public.cidc_saldo_item(char, text) from public;
revoke all on function public.cidc_estoque_movimentar(char, text, numeric, text, text, text) from public;
revoke all on function public.cidc_ajuda_entregar(char, jsonb, uuid, uuid, uuid, integer, text, text, integer) from public;
grant execute on function public.cidc_pode_movimentar_estoque(char) to authenticated;
grant execute on function public.cidc_saldo_item(char, text) to authenticated;
grant execute on function public.cidc_estoque_movimentar(char, text, numeric, text, text, text) to authenticated;
grant execute on function public.cidc_ajuda_entregar(char, jsonb, uuid, uuid, uuid, integer, text, text, integer) to authenticated;
