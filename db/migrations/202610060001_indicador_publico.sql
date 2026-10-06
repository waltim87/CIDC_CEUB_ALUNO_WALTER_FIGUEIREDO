-- Fase 5: indicador público leitura -> emissão, sem abrir a tabela indices.
-- Expõe apenas horários de alertas já enviados (mesma visibilidade pública).
create or replace function public.indicador_latencia_publica()
returns table (
    alerta_id uuid,
    emitido_em timestamptz,
    data_hora_leitura_referencia timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select a.id, a.emitido_em, i.data_hora_leitura_referencia
    from public.alertas a
    join public.indices i on i.id = a.indice_id
    where a.status = 'enviado'
      and a.emitido_em is not null
    order by a.emitido_em desc
    limit 1000;
$$;

revoke all on function public.indicador_latencia_publica() from public;
grant execute on function public.indicador_latencia_publica() to anon, authenticated;
