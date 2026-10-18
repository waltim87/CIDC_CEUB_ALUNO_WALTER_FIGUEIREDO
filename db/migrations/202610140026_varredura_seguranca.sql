-- Varredura de segurança de 17/10/2026 (migrations 0004-0022). Corrige:
--  A. Funções de permissão antigas podiam devolver NULL (perfil sem município) e "if not NULL"
--     não barra. Agora todas devolvem true/false.
--  B. 0019 reescreveu cidc_pode_gerenciar_notificacoes e TIROU a logística das assinaturas
--     de alerta (aba da Logística). Restaurado.
--  C. notificacoes_telegram: qualquer pessoa que via o município (voluntários veem todos) lia
--     todas as mensagens enviadas. Agora: coordenação/admin do município e o próprio destinatário.
--  D. Vistorias de abrigo: escrita direta na tabela permitia registrar vistoria (e o selo
--     "pronto") para abrigo de OUTRO município e em nome de outra pessoa. Agora só pela função.
--  E. Embarcações: qualquer pessoa que via o município (voluntários) atribuía/liberava barcos;
--     o cadastro por id sobrescrevia barco de outro município; barco ficava "em uso" para
--     sempre depois da ocorrência resolvida.
--  F. Ficha S2iD: primeiro registro de cada comunidade falhava (coluna criado_em inexistente
--     e famílias/pessoas nulas em colunas obrigatórias).
-- Ao final, uma consulta de auditoria lista o que ainda merece atenção no banco.

-- ------------------------------------------------------------ A. permissões sempre booleanas
create or replace function public.cidc_pode_registrar_afetados(p_municipio_id char(7))
returns boolean language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'agente_campo')), false)
$$;

create or replace function public.cidc_pode_gerenciar_abrigo(p_municipio_id char(7))
returns boolean language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'logistica_abastecimento')), false)
$$;

create or replace function public.cidc_pode_revisar_alerta(p_municipio_id char(7))
returns boolean language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(
        public.cidc_perfil_atual() in ('administrador', 'gestor_nacional', 'operador_monitoramento')
        or (public.cidc_perfil_atual() = 'gestor_estadual'
            and exists (
                select 1 from public.municipios municipio_atribuido
                  join public.municipios municipio_alerta on municipio_alerta.id_ibge = p_municipio_id
                 where municipio_atribuido.id_ibge = public.cidc_municipio_atual()
                   and municipio_atribuido.uf = municipio_alerta.uf))
        or (public.cidc_perfil_atual() = 'coordenador_municipal'
            and public.cidc_municipio_atual() = p_municipio_id), false)
$$;

create or replace function public.cidc_pode_atender_familias(p_municipio_id char(7), p_abrigo_id uuid)
returns boolean language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_perfil_atual() in ('coordenador_municipal', 'saude_assistencia')
            and public.cidc_municipio_atual() = p_municipio_id)
        or (p_abrigo_id is not null and public.cidc_coordena_abrigo(p_abrigo_id)), false)
$$;

-- ------------------------------------------------------------ B. logística volta às assinaturas
create or replace function public.cidc_pode_gerenciar_notificacoes(p_municipio_id char(7))
returns boolean language sql stable security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'logistica_abastecimento')), false)
$$;

-- ------------------------------------------------------------ C. mensagens do Telegram
alter table public.notificacoes_telegram alter column usuario_id drop not null;
drop policy if exists notificacoes_telegram_select on public.notificacoes_telegram;
create policy notificacoes_telegram_select on public.notificacoes_telegram
    for select to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id) or usuario_id = public.cidc_usuario_id_atual());
-- Registro (auditoria) só por quem atua no município; nunca com chat_id completo.
drop policy if exists notificacoes_telegram_insert on public.notificacoes_telegram;
create policy notificacoes_telegram_insert on public.notificacoes_telegram
    for insert to authenticated
    with check (coalesce(public.cidc_municipio_atual() = municipio_id, false) or public.cidc_administrador());
alter table public.notificacoes_telegram drop constraint if exists notificacoes_chat_mascarado;
alter table public.notificacoes_telegram add constraint notificacoes_chat_mascarado
    check (chat_id like '***%') not valid;

-- ------------------------------------------------------------ D. vistorias só pela função
revoke insert, update, delete on public.abrigo_vistorias from authenticated;
drop policy if exists abrigo_vistorias_gestao on public.abrigo_vistorias;
alter table public.abrigo_vistorias alter column vistoriado_por drop not null;

-- Vistoria mais recente de cada abrigo (selo da ÚLTIMA vistoria, não de qualquer uma).
drop view if exists public.abrigo_vistoria_recente;
create view public.abrigo_vistoria_recente
with (security_invoker = true) as
select distinct on (v.abrigo_id)
       v.abrigo_id, v.municipio_id, v.data_vistoria as ultima_vistoria, v.selo_pronto,
       v.data_vistoria < current_date - 90 as vistoria_vencida
  from public.abrigo_vistorias v
 order by v.abrigo_id, v.data_vistoria desc, v.criado_em desc;
grant select on public.abrigo_vistoria_recente to authenticated;

-- ------------------------------------------------------------ E. embarcações
revoke insert, update, delete on public.embarcacoes from authenticated;
drop policy if exists embarcacoes_gestao on public.embarcacoes;

do $$
declare f regprocedure;
begin
    for f in select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'public' and p.proname = 'cidc_embarcacao_cadastrar' loop
        execute 'drop function ' || f;
    end loop;
end $$;

create function public.cidc_embarcacao_cadastrar(
    p_municipio_id char(7),
    p_nome text,
    p_tipo text,
    p_id uuid default null,
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
    v_salvo uuid;
begin
    if not public.cidc_pode_gerenciar_embarcacao(p_municipio_id) then
        raise exception 'Só coordenação, administração ou logística gerencia embarcações';
    end if;
    insert into public.embarcacoes
        (id, municipio_id, nome, tipo, capacidade, piloto, telefone_piloto, combustivel,
         quantidade_combustivel, status, observacoes, registrado_por, registrado_em, atualizado_em)
    values (coalesce(p_id, gen_random_uuid()), p_municipio_id, trim(p_nome), p_tipo, coalesce(p_capacidade, 1),
            nullif(trim(coalesce(p_piloto, '')), ''), nullif(trim(coalesce(p_telefone_piloto, '')), ''),
            nullif(trim(coalesce(p_combustivel, '')), ''), p_quantidade_combustivel,
            coalesce(p_status, 'disponível'), nullif(trim(coalesce(p_observacoes, '')), ''),
            public.cidc_usuario_id_atual(), now(), now())
    on conflict (id) do update set
        nome = excluded.nome, tipo = excluded.tipo, capacidade = excluded.capacidade,
        piloto = excluded.piloto, telefone_piloto = excluded.telefone_piloto,
        combustivel = excluded.combustivel, quantidade_combustivel = excluded.quantidade_combustivel,
        status = excluded.status, observacoes = excluded.observacoes, atualizado_em = now()
     where public.embarcacoes.municipio_id = excluded.municipio_id
    returning id into v_salvo;
    if v_salvo is null then
        raise exception 'Embarcação não encontrada neste município';
    end if;
    return v_salvo;
end;
$$;
revoke all on function public.cidc_embarcacao_cadastrar(char, text, text, uuid, integer, text, text, text, numeric, text, text) from public, anon;
grant execute on function public.cidc_embarcacao_cadastrar(char, text, text, uuid, integer, text, text, text, numeric, text, text) to authenticated;

-- Atribuir barco: coordenação/logística/admin do município ou a equipe responsável da ocorrência.
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
begin
    select * into o from public.ocorrencias where id = p_ocorrencia for update;
    if o.id is null then
        raise exception 'Ocorrência não encontrada';
    end if;
    if not (public.cidc_pode_gerenciar_embarcacao(o.municipio_id)
            or coalesce(o.responsavel_id = public.cidc_usuario_id_atual(), false)
            or coalesce(o.equipe_funcao = public.cidc_perfil_atual()
                        and public.cidc_municipio_atual() = o.municipio_id, false)) then
        raise exception 'Só a coordenação, a logística ou a equipe da ocorrência atribui embarcação';
    end if;
    if o.status in ('resolvida', 'cancelada') and p_embarcacao_id is not null then
        raise exception 'Ocorrência encerrada';
    end if;
    if p_embarcacao_id is not null then
        select * into e from public.embarcacoes where id = p_embarcacao_id for update;
        if e.id is null or e.municipio_id <> o.municipio_id then
            raise exception 'Embarcação não encontrada neste município';
        end if;
        if e.id is distinct from o.embarcacao_id and e.status <> 'disponível' then
            raise exception 'Embarcação já está em uso ou fora de serviço';
        end if;
    end if;
    if o.embarcacao_id is not null and o.embarcacao_id is distinct from p_embarcacao_id then
        update public.embarcacoes set status = 'disponível', atualizado_em = now()
         where id = o.embarcacao_id and status = 'em_uso';
    end if;
    if p_embarcacao_id is not null then
        update public.embarcacoes set status = 'em_uso', atualizado_em = now() where id = p_embarcacao_id;
    end if;
    update public.ocorrencias set embarcacao_id = p_embarcacao_id where id = p_ocorrencia;
    perform public.cidc_ocorrencia_evento(p_ocorrencia, null,
        case when p_embarcacao_id is null then 'Embarcação liberada'
             else 'Embarcação designada: ' || e.nome end);
    return 'ok';
end;
$$;
revoke all on function public.cidc_ocorrencia_atribuir_embarcacao(uuid, uuid) from public, anon;
grant execute on function public.cidc_ocorrencia_atribuir_embarcacao(uuid, uuid) to authenticated;

-- Ocorrência resolvida ou cancelada libera o barco.
create or replace function public.cidc_ocorrencia_libera_embarcacao()
returns trigger language plpgsql security definer
set search_path = pg_catalog, public, pg_temp
as $$
begin
    if new.status in ('resolvida', 'cancelada') and old.status is distinct from new.status
       and new.embarcacao_id is not null then
        update public.embarcacoes set status = 'disponível', atualizado_em = now()
         where id = new.embarcacao_id and status = 'em_uso';
    end if;
    return new;
end;
$$;
drop trigger if exists ocorrencia_libera_embarcacao on public.ocorrencias;
create trigger ocorrencia_libera_embarcacao after update of status on public.ocorrencias
    for each row execute function public.cidc_ocorrencia_libera_embarcacao();
revoke all on function public.cidc_ocorrencia_libera_embarcacao() from public, authenticated, anon;

-- ------------------------------------------------------------ F. ficha S2iD
create or replace function public.cidc_pessoas_afetadas_cadastrar(
    p_comunidade_id uuid,
    p_data date,
    p_familias integer default null,
    p_pessoas integer default null,
    p_desalojados integer default null,
    p_desabrigados integer default null,
    p_obitos integer default null,
    p_danos_casas integer default null,
    p_danos_instalacoes text default null,
    p_necessidades jsonb default null,
    p_fonte_afetados text default null,
    p_observacoes text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_comunidade record;
    v_existente uuid;
    v_id uuid;
begin
    select c.id, c.municipio_id into v_comunidade from public.comunidades c where c.id = p_comunidade_id;
    if v_comunidade.id is null then
        raise exception 'Comunidade não encontrada';
    end if;
    if not public.cidc_pode_registrar_afetados(v_comunidade.municipio_id) then
        raise exception 'Só a coordenação ou o agente de campo do município registra afetados';
    end if;
    select id into v_existente from public.pessoas_afetadas
     where comunidade_id = p_comunidade_id and data::date = p_data limit 1;
    if v_existente is not null then
        update public.pessoas_afetadas
           set familias = coalesce(p_familias, familias), pessoas = coalesce(p_pessoas, pessoas),
               desalojados = coalesce(p_desalojados, desalojados), desabrigados = coalesce(p_desabrigados, desabrigados),
               obitos = coalesce(p_obitos, obitos), danos_casas = coalesce(p_danos_casas, danos_casas),
               danos_instalacoes = coalesce(nullif(trim(coalesce(p_danos_instalacoes, '')), ''), danos_instalacoes),
               necessidades = coalesce(p_necessidades, necessidades),
               fonte_afetados = coalesce(nullif(trim(coalesce(p_fonte_afetados, '')), ''), fonte_afetados),
               observacoes = coalesce(nullif(trim(coalesce(p_observacoes, '')), ''), observacoes),
               atualizado_em = now()
         where id = v_existente;
        return v_existente;
    end if;
    insert into public.pessoas_afetadas
        (comunidade_id, data, familias, pessoas, desalojados, desabrigados, obitos, danos_casas,
         danos_instalacoes, necessidades, fonte_afetados, observacoes, atualizado_em)
    values (p_comunidade_id, p_data, coalesce(p_familias, 0), coalesce(p_pessoas, 0), p_desalojados,
            p_desabrigados, p_obitos, p_danos_casas, nullif(trim(coalesce(p_danos_instalacoes, '')), ''),
            coalesce(p_necessidades, '[]'::jsonb), nullif(trim(coalesce(p_fonte_afetados, '')), ''),
            nullif(trim(coalesce(p_observacoes, '')), ''), now())
    returning id into v_id;
    return v_id;
end;
$$;

-- ------------------------------------------------------------ auditoria final
-- Lista o que ainda merece atenção (resultado vazio = nada encontrado).
select 'tabela sem RLS' as problema, c.relname::text as objeto
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
union all
select 'view sem security_invoker', c.relname::text
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'v'
   and not coalesce('security_invoker=true' = any(c.reloptions), false)
   and not coalesce('security_invoker=on' = any(c.reloptions), false)
union all
select 'função security definer sem search_path', p.oid::regprocedure::text
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public' and p.prosecdef
   and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%')
union all
select 'escrita liberada para anônimo', c.relname::text
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
   and (has_table_privilege('anon', c.oid, 'INSERT') or has_table_privilege('anon', c.oid, 'UPDATE')
        or has_table_privilege('anon', c.oid, 'DELETE'))
   and exists (select 1 from pg_policy pol where pol.polrelid = c.oid
                and (pol.polroles = '{0}' or 'anon'::regrole::oid = any(pol.polroles))
                and pol.polcmd in ('a', 'w', 'd', '*'))
union all
-- Funções que GRAVAM (não "stable") e que um visitante sem login consegue executar.
select 'função que grava e anônimo executa', p.oid::regprocedure::text
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public' and p.proname like 'cidc\_%' and p.prosecdef and p.provolatile = 'v'
   and p.prorettype <> 'trigger'::regtype
   and has_function_privilege('anon', p.oid, 'EXECUTE')
 order by 1, 2;
