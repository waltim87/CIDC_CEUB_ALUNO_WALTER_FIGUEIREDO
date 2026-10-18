-- Retorno das famílias (recuperação).
-- Acompanha quem voltou para casa, quem não tem para onde ir e o que falta
-- (reforma, documentos, benefícios). Respeita a LGPD: dados das famílias
-- só são visíveis a quem já pode vê-las.

alter table public.familias_abrigadas
    add column if not exists data_retorno date check (data_retorno is null or data_retorno >= data_entrada),
    add column if not exists endereco_retorno text check (endereco_retorno is null or length(endereco_retorno) <= 300),
    add column if not exists tem_para_onde_ir boolean,
    add column if not exists motivo_sem_retorno text check (motivo_sem_retorno is null or length(motivo_sem_retorno) <= 500),
    add column if not exists precisa_reforma boolean not null default false,
    add column if not exists precisa_documentos boolean not null default false,
    add column if not exists precisa_beneficios boolean not null default false,
    add column if not exists observacoes_retorno text check (observacoes_retorno is null or length(observacoes_retorno) <= 1000),
    add column if not exists retorno_atualizado_em timestamptz;

create index if not exists familias_retorno_idx on public.familias_abrigadas (municipio_id, data_retorno);

-- View: famílias que ainda estão abrigadas (sem data de saída) com status de retorno.
create or replace view public.familias_retorno_status
with (security_invoker = true) as
select f.id as familia_id, f.municipio_id, f.abrigo_id, f.responsavel_nome,
       f.responsavel_cpf, f.data_entrada, f.data_saida, f.data_retorno,
       f.endereco_retorno, f.tem_para_onde_ir, f.motivo_sem_retorno,
       f.precisa_reforma, f.precisa_documentos, f.precisa_beneficios,
       f.observacoes_retorno, f.retorno_atualizado_em,
       case when f.data_saida is not null then 'saida'
            when f.data_retorno is not null then 'retornou'
            when f.tem_para_onde_ir = false then 'sem_para_onde_ir'
            else 'abrigo' end as status_retorno
  from public.familias_abrigadas f;
grant select on public.familias_retorno_status to authenticated;

-- Função para atualizar o retorno de uma família.
create or replace function public.cidc_familia_retorno_atualizar(
    p_familia_id uuid,
    p_data_retorno date default null,
    p_endereco_retorno text default null,
    p_tem_para_onde_ir boolean default null,
    p_motivo_sem_retorno text default null,
    p_precisa_reforma boolean default null,
    p_precisa_documentos boolean default null,
    p_precisa_beneficios boolean default null,
    p_observacoes_retorno text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_familia record;
    v_id uuid := p_familia_id;
begin
    select f.id, f.municipio_id, f.abrigo_id into v_familia
      from public.familias_abrigadas f where f.id = p_familia_id;
    if v_familia.id is null then
        raise exception 'Família não encontrada';
    end if;
    if not coalesce(public.cidc_pode_atender_familias(v_familia.municipio_id, v_familia.abrigo_id), false) then
        raise exception 'Só quem atende famílias deste município pode atualizar o retorno';
    end if;

    update public.familias_abrigadas
       set data_retorno = coalesce(p_data_retorno, data_retorno),
           endereco_retorno = coalesce(nullif(trim(coalesce(p_endereco_retorno, '')), ''), endereco_retorno),
           tem_para_onde_ir = coalesce(p_tem_para_onde_ir, tem_para_onde_ir),
           motivo_sem_retorno = coalesce(nullif(trim(coalesce(p_motivo_sem_retorno, '')), ''), motivo_sem_retorno),
           precisa_reforma = coalesce(p_precisa_reforma, precisa_reforma),
           precisa_documentos = coalesce(p_precisa_documentos, precisa_documentos),
           precisa_beneficios = coalesce(p_precisa_beneficios, precisa_beneficios),
           observacoes_retorno = coalesce(nullif(trim(coalesce(p_observacoes_retorno, '')), ''), observacoes_retorno),
           retorno_atualizado_em = now()
     where id = p_familia_id;
    return v_id;
end;
$$;
revoke all on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) from public;
revoke all on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) from authenticated, anon;
grant execute on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) to authenticated;
