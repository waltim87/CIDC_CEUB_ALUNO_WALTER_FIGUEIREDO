-- Abrir ocorrência SEM relato de campo sempre falhava ("record v_relato is not assigned yet"):
-- a função lia a latitude do relato mesmo quando não havia relato. Encontrado no teste integrado
-- de 17/10/2026; até então só tinha sido testada a abertura a partir de um relato.

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
    v_lat double precision;
    v_lon double precision;
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
        v_lat := v_relato.latitude;
        v_lon := v_relato.longitude;
    end if;
    insert into public.ocorrencias (municipio_id, relato_id, tipo, prioridade, titulo, descricao, local_descricao,
                                    latitude, longitude, pessoas_envolvidas, aberta_por)
    values (p_municipio_id, p_relato_id, p_tipo, coalesce(p_prioridade, 'media'), trim(p_titulo),
            nullif(trim(coalesce(p_descricao, '')), ''), nullif(trim(coalesce(p_local, '')), ''),
            coalesce(p_latitude, v_lat), coalesce(p_longitude, v_lon),
            p_pessoas, public.cidc_usuario_id_atual())
    returning id into v_id;
    perform public.cidc_ocorrencia_evento(v_id, 'aberta',
        case when p_relato_id is null then 'Ocorrência aberta' else 'Ocorrência aberta a partir de um relato de campo' end);
    return v_id;
end;
$$;
