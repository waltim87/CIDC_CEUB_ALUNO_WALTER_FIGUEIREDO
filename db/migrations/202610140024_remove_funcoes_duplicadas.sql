-- Remove versões antigas (de tentativas anteriores) das funções de áreas de risco e de obras.
-- Com duas versões no banco, o Supabase não sabia qual chamar (erro PGRST203) quando o app
-- não enviava todos os campos, e a versão antiga não tinha a proteção contra alterar o
-- registro de outro município. Fica só a versão correta das migrations 0017 e 0023.

do $$
declare
    f regprocedure;
begin
    for f in
        select p.oid::regprocedure
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname in ('cidc_area_risco_cadastrar', 'cidc_obra_cadastrar')
           and p.oid not in (
               'public.cidc_area_risco_cadastrar(char, text, text, text, uuid, uuid, integer, integer, text, double precision, double precision, text)'::regprocedure,
               'public.cidc_obra_cadastrar(char, text, text, uuid, text, text, numeric, text, text[], integer, date, date, date, text, text)'::regprocedure)
    loop
        execute 'drop function ' || f;
        raise notice 'Removida a versão antiga: %', f;
    end loop;
end $$;

notify pgrst, 'reload schema';

select p.oid::regprocedure as funcao_que_ficou
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public' and p.proname in ('cidc_area_risco_cadastrar', 'cidc_obra_cadastrar');
