-- DADOS DE TESTE do chat interno (fictícios): 4 comunidades, 3 canais e 12 mensagens.
-- Rodar DEPOIS da migration 202610140012 e de usuarios_teste.sql.
-- Apagar com db/testes/limpar_dados_teste.sql (comunidades, canais e mensagens "[TESTE]").

begin;

insert into public.comunidades (municipio_id, nome, populacao_estimada, acesso_principal)
select v.municipio_id, v.nome, v.populacao, v.acesso
  from (values
    ('1302405', '[TESTE] Comunidade São Raimundo', 320, 'fluvial'),
    ('1302405', '[TESTE] Comunidade Nova Esperança', 180, 'fluvial'),
    ('1300706', '[TESTE] Comunidade Santa Luzia', 250, 'fluvial'),
    ('1300706', '[TESTE] Comunidade Boa Vista do Purus', 140, 'fluvial/ramal')
  ) v(municipio_id, nome, populacao, acesso)
 where not exists (select 1 from public.comunidades c where c.nome = v.nome);

do $$
declare
    v_geral uuid;
    v_comunidades uuid;
    v_privado uuid;
begin
    create temp table pessoa on commit drop as
    select split_part(a.email, '@', 1) as conta, us.id
      from auth.users a join public.usuarios us on us.auth_id = a.id
     where a.email like '%@cidc-teste.example';
    if (select count(*) from pessoa) < 10 then
        raise exception 'Rode antes db/testes/usuarios_teste.sql';
    end if;

    -- Canal geral de Lábrea
    select id into v_geral from public.chat_canais where tipo = 'municipio' and municipio_id = '1302405';
    if v_geral is null then
        insert into public.chat_canais (nome, tipo, municipio_id, criado_por)
        values ('Geral - Lábrea/AM', 'municipio', '1302405', (select id from pessoa where conta = 'coordenacao.labrea'))
        returning id into v_geral;
    end if;

    -- Canal ENTRE comunidades de dois municípios (Lábrea e Boca do Acre)
    insert into public.chat_canais (nome, tipo, comunidades, descricao, criado_por)
    values ('[TESTE] Comunidades do Purus', 'comunidades',
            (select array_agg(id) from public.comunidades where nome like '[TESTE]%'),
            'Lideranças e voluntários das comunidades ao longo do rio Purus',
            (select id from pessoa where conta = 'voluntario1'))
    returning id into v_comunidades;

    -- Canal privado com pessoas selecionadas
    insert into public.chat_canais (nome, tipo, descricao, criado_por)
    values ('[TESTE] Abrigo Escola Rio Purus - equipe', 'privado', 'Coordenação, campo e apoio do abrigo',
            (select id from pessoa where conta = 'coordenacao.labrea'))
    returning id into v_privado;
    insert into public.chat_membros (canal_id, usuario_id)
    select v_privado, id from pessoa where conta in ('coordenacao.labrea', 'campo.labrea', 'voluntario1', 'saude.labrea');

    insert into public.chat_mensagens (canal_id, usuario_id, texto, criado_em)
    select c.canal, p.id, '[TESTE] ' || c.texto, now() - c.minutos * interval '1 minute'
      from (values
        (v_geral, 'coordenacao.labrea', 'Bom dia a todos. Rio Purus subiu 18 cm nas últimas 24 h na régua da cidade.', 300),
        (v_geral, 'voluntario1', 'Confirmo: no porto a água já chegou na segunda escada.', 290),
        (v_geral, 'monitoramento.labrea', 'Estação da ANA mostra nível em atenção. Próxima leitura às 15h.', 240),
        (v_geral, 'logistica.labrea', 'Temos 2 barcos e 300 kits de higiene disponíveis no galpão.', 200),
        (v_comunidades, 'voluntario1', 'Pessoal de São Raimundo: como está a água aí?', 180),
        (v_comunidades, 'voluntario2', 'Em Santa Luzia o ramal já está alagado, só dá para sair de barco.', 170),
        (v_comunidades, 'voluntario1', 'Aqui em Nova Esperança ainda está tranquilo, mas a correnteza aumentou.', 160),
        (v_comunidades, 'coordenacao.boca', 'Vamos mandar uma voadeira para Boa Vista do Purus amanhã cedo.', 120),
        (v_privado, 'coordenacao.labrea', 'O abrigo está com 38 de 60 vagas ocupadas.', 100),
        (v_privado, 'campo.labrea', 'Chegaram mais 3 famílias. Uma idosa precisa de remédio de pressão.', 90),
        (v_privado, 'saude.labrea', 'Levo a medicação às 14h e faço a triagem de todos.', 80),
        (v_privado, 'voluntario1', 'Posso ajudar na distribuição das refeições à noite.', 60)
      ) c(canal, conta, texto, minutos)
      join pessoa p on p.conta = c.conta;
end $$;

commit;

select c.nome, c.tipo, count(m.id) as mensagens
  from public.chat_canais c left join public.chat_mensagens m on m.canal_id = c.id
 group by c.nome, c.tipo order by c.tipo;
