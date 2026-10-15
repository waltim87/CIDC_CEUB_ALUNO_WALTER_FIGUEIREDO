-- Correção: quem não é da equipe conseguia mudar a situação de ocorrência sem responsável
-- (comparação com NULL não barrava). Encontrado no teste de 14/10/2026.

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

-- Mesma causa nas funções de permissão: perfil sem município (ou sem perfil) fazia a função
-- devolver NULL em vez de false, e "if not ..." nas funções do chat, do plano e das
-- ocorrências não barrava. Agora elas sempre devolvem true/false (RLS não muda: NULL já era negado).
create or replace function public.cidc_pode_operar_municipio(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(
        public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() = 'coordenador_municipal'
        ), false)
$$;

create or replace function public.cidc_pode_ver_municipio(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(
        public.cidc_perfil_atual() in (
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
        ), false)
$$;

create or replace function public.cidc_pode_abrir_ocorrencia(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(
        public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'operador_monitoramento', 'agente_campo',
                                               'saude_assistencia', 'logistica_abastecimento')), false)
$$;
