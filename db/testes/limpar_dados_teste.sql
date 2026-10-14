-- Remove TODOS os dados de teste criados por dados_teste_abrigos_familias_relatos.sql.
begin;
delete from public.familias_abrigadas where observacoes like '[TESTE]%';   -- membros e fotos em cascata
delete from public.abrigos where nome like '[TESTE]%';                      -- designações em cascata
delete from public.relatos where descricao like '[TESTE]%';                -- votos em cascata
commit;

select (select count(*) from public.abrigos where nome like '[TESTE]%') as abrigos_teste,
       (select count(*) from public.familias_abrigadas where observacoes like '[TESTE]%') as familias_teste,
       (select count(*) from public.relatos where descricao like '[TESTE]%') as relatos_teste;
