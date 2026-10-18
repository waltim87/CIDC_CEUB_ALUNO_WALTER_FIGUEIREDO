-- Correções do retorno das famílias (0021), encontradas no teste de 17/10/2026:
--  1. Salvar sempre falhava: a função buscava a família sem o abrigo e depois usava o abrigo
--     ("record v_familia has no field abrigo_id").
--  2. Família que voltou para casa continuava "abrigada" (sem data de saída) e aparecia como
--     sem cesta na ajuda humanitária. Agora o retorno preenche a saída do abrigo.
--  3. Permissão sem coalesce (NULL não barrava) — mesma lição da 0015.
--  4. A view devolvia o CPF sem necessidade (LGPD: só o que é usado).

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
begin
    select f.id, f.municipio_id, f.abrigo_id, f.data_entrada into v_familia
      from public.familias_abrigadas f where f.id = p_familia_id;
    if v_familia.id is null then
        raise exception 'Família não encontrada';
    end if;
    if not coalesce(public.cidc_pode_atender_familias(v_familia.municipio_id, v_familia.abrigo_id), false) then
        raise exception 'Só quem atende famílias deste município pode atualizar o retorno';
    end if;
    if p_data_retorno is not null and p_data_retorno < v_familia.data_entrada then
        raise exception 'A data de retorno não pode ser anterior à entrada no abrigo (%)',
            to_char(v_familia.data_entrada, 'DD/MM/YYYY');
    end if;

    update public.familias_abrigadas
       set data_retorno = coalesce(p_data_retorno, data_retorno),
           -- Voltou para casa = saiu do abrigo (deixa de contar como abrigada).
           data_saida = coalesce(data_saida, p_data_retorno),
           endereco_retorno = coalesce(nullif(trim(coalesce(p_endereco_retorno, '')), ''), endereco_retorno),
           tem_para_onde_ir = coalesce(p_tem_para_onde_ir, tem_para_onde_ir),
           motivo_sem_retorno = coalesce(nullif(trim(coalesce(p_motivo_sem_retorno, '')), ''), motivo_sem_retorno),
           precisa_reforma = coalesce(p_precisa_reforma, precisa_reforma),
           precisa_documentos = coalesce(p_precisa_documentos, precisa_documentos),
           precisa_beneficios = coalesce(p_precisa_beneficios, precisa_beneficios),
           observacoes_retorno = coalesce(nullif(trim(coalesce(p_observacoes_retorno, '')), ''), observacoes_retorno),
           retorno_atualizado_em = now()
     where id = p_familia_id;
    return p_familia_id;
end;
$$;
revoke all on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) from public;
revoke all on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) from anon;
grant execute on function public.cidc_familia_retorno_atualizar(uuid, date, text, boolean, text, boolean, boolean, boolean, text) to authenticated;

-- Famílias que já tinham data de retorno: passam a constar como fora do abrigo.
update public.familias_abrigadas set data_saida = data_retorno
 where data_retorno is not null and data_saida is null;

-- View sem CPF (não é usada pelo app; mantida para consultas e relatórios).
drop view if exists public.familias_retorno_status;
create view public.familias_retorno_status
with (security_invoker = true) as
select f.id as familia_id, f.municipio_id, f.abrigo_id, f.responsavel_nome,
       f.data_entrada, f.data_saida, f.data_retorno,
       f.endereco_retorno, f.tem_para_onde_ir, f.motivo_sem_retorno,
       f.precisa_reforma, f.precisa_documentos, f.precisa_beneficios,
       f.observacoes_retorno, f.retorno_atualizado_em,
       case when f.data_retorno is not null then 'retornou'
            when f.data_saida is not null then 'saida'
            when f.tem_para_onde_ir = false then 'sem_para_onde_ir'
            else 'abrigo' end as status_retorno
  from public.familias_abrigadas f;
grant select on public.familias_retorno_status to authenticated;
