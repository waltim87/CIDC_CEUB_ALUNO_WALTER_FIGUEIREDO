-- Remove TODOS os dados de teste de dados_teste_abrigos_familias_relatos.sql e chat_teste.sql.
-- (As contas de teste saem com limpar_usuarios_teste.sql.)
begin;
-- Movimentos de ajuda humanitária de teste (estoque, entregas a família/comunidade/abrigo)
delete from public.ajuda_movimentos where observacao like '[TESTE]%';
-- Áreas de risco de teste
delete from public.areas_risco_comunidade where descricao like '[TESTE]%';
delete from public.familias_abrigadas where observacoes like '[TESTE]%';   -- membros e fotos em cascata
delete from public.abrigos where nome like '[TESTE]%';                      -- designações em cascata
delete from public.relatos where descricao like '[TESTE]%';                -- votos em cascata
delete from public.chat_mensagens where texto like '[TESTE]%';
delete from public.acoes where acionamento_id in (select id from public.plano_acionamentos where observacao like '[TESTE]%');
delete from public.plano_acionamentos where observacao like '[TESTE]%';
delete from public.chat_canais where nome like '[TESTE]%';                 -- membros e mensagens em cascata
delete from public.comunidades where nome like '[TESTE]%';
commit;

select (select count(*) from public.abrigos where nome like '[TESTE]%') as abrigos_teste,
       (select count(*) from public.familias_abrigadas where observacoes like '[TESTE]%') as familias_teste,
       (select count(*) from public.relatos where descricao like '[TESTE]%') as relatos_teste,
       (select count(*) from public.chat_mensagens where texto like '[TESTE]%') as mensagens_teste,
       (select count(*) from public.ajuda_movimentos where observacao like '[TESTE]%') as ajuda_movimentos_teste,
       (select count(*) from public.areas_risco_comunidade where descricao like '[TESTE]%') as areas_risco_teste;
