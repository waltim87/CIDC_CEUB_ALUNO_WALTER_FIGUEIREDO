-- DADOS DE TESTE (fictícios) — 5 abrigos, 100 famílias com membros e desaparecidos, 10 relatos.
-- Tudo marcado com "[TESTE]"/"TESTE" para não ser confundido com dado real.
-- Apagar depois com: db/testes/limpar_dados_teste.sql
-- Rodar no SQL Editor do Supabase DEPOIS da migration 202610140009.

begin;

-- CPF fictício com dígitos verificadores válidos (passa na validação do app).
create or replace function pg_temp.cpf_teste(base bigint) returns text
language plpgsql as $$
declare
    d text := lpad((base % 1000000000)::text, 9, '0');
    s int := 0;
    dv1 int;
    dv2 int;
begin
    for i in 1..9 loop s := s + substr(d, i, 1)::int * (11 - i); end loop;
    dv1 := (s * 10) % 11 % 10;
    d := d || dv1::text;
    s := 0;
    for i in 1..10 loop s := s + substr(d, i, 1)::int * (12 - i); end loop;
    dv2 := (s * 10) % 11 % 10;
    return d || dv2::text;
end;
$$;

do $$
declare
    municipios char(7)[] := array['1302405', '1300706', '1300631', '1302603', '1301704'];
    nomes_abrigo text[] := array['Escola Municipal Rio Purus', 'Ginásio Poliesportivo', 'Centro Comunitário São José',
                                 'Escola Estadual Beira-Rio', 'Igreja Matriz'];
    primeiros text[] := array['Maria', 'José', 'Ana', 'João', 'Francisca', 'Antônio', 'Raimunda', 'Francisco',
                              'Luzia', 'Pedro', 'Rosa', 'Carlos', 'Joana', 'Paulo', 'Socorro', 'Raimundo',
                              'Juliana', 'Marcos', 'Aparecida', 'Sebastião'];
    sobrenomes text[] := array['Silva', 'Souza', 'Oliveira', 'Lima', 'Pereira', 'Costa', 'Ferreira', 'Rodrigues',
                               'Almeida', 'Nascimento', 'Araújo', 'Batista', 'Barbosa', 'Gomes', 'Monteiro'];
    parentescos text[] := array['cônjuge/companheiro(a)', 'filho(a)', 'filho(a)', 'neto(a)', 'pai/mãe', 'irmão/irmã'];
    situacoes text[] := array['destruido', 'parcialmente_destruido', 'danificado', 'interditado', 'alagado', 'alagado'];
    necessidades text[] := array['água', 'alimento', 'roupas', 'medicamento', 'kit higiene', 'colchão/rede'];
    locais text[] := array['margem do rio Purus, próximo ao porto', 'comunidade ribeirinha a montante',
                           'estrada de acesso à sede', 'barco de transporte para a sede'];
    abrigos uuid[] := '{}';
    v_abrigo uuid;
    v_familia uuid;
    v_mun char(7);
    n_membros int;
begin
    for k in 1..5 loop
        insert into public.abrigos (municipio_id, nome, capacidade, ocupacao, tipo_local, endereco,
                                    responsavel, telefone, possui_agua, possui_energia, possui_banheiro, acessivel)
        values (municipios[k], '[TESTE] ' || nomes_abrigo[k], 150, 0, 'escola', 'Endereço de teste, ' || k,
                'TESTE Coordenação ' || k, '(97) 90000-000' || k, true, true, true, k % 2 = 0)
        returning id into v_abrigo;
        abrigos := abrigos || v_abrigo;
    end loop;

    for i in 1..100 loop
        v_abrigo := abrigos[(i % 5) + 1];
        v_mun := municipios[(i % 5) + 1];
        insert into public.familias_abrigadas (
            abrigo_id, municipio_id, responsavel_nome, responsavel_cpf, telefone, endereco_origem,
            situacao_imovel, data_entrada, necessidades, observacoes, consentimento_lgpd)
        values (
            v_abrigo, v_mun,
            'TESTE ' || primeiros[(i % 20) + 1] || ' ' || sobrenomes[(i % 15) + 1] || ' ' || sobrenomes[((i * 7) % 15) + 1],
            pg_temp.cpf_teste(900000000 + i * 7919),
            '(97) 9' || lpad((80000000 + i * 37)::text, 8, '0'),
            'Rua de Teste, ' || i || ' — bairro fictício',
            situacoes[(i % 6) + 1], current_date - (i % 10),
            array[necessidades[(i % 6) + 1], necessidades[((i + 2) % 6) + 1]],
            '[TESTE] cadastro fictício para testes do sistema', true)
        returning id into v_familia;

        n_membros := (i / 5) % 5;  -- 0 a 4 membros, variando dentro de cada abrigo
        for j in 1..n_membros loop
            insert into public.membros_familia (
                familia_id, nome_completo, cpf, sem_cpf_motivo, parentesco, data_nascimento,
                desaparecido, visto_por_ultimo_em, ultimo_local_visto)
            values (
                v_familia,
                'TESTE ' || primeiros[((i + j * 3) % 20) + 1] || ' ' || sobrenomes[(i % 15) + 1],
                case when j = 4 then null else pg_temp.cpf_teste(800000000 + i * 1000 + j) end,
                case when j = 4 then 'recém-nascido(a), sem documento' end,
                parentescos[((j - 1) % 6) + 1],
                current_date - ((5 + j * 9 + i % 30) * 365),
                (i % 13 = 0 and j = 1),
                case when i % 13 = 0 and j = 1 then current_date - (i % 4 + 1) end,
                case when i % 13 = 0 and j = 1 then locais[(i % 4) + 1] end);
        end loop;
    end loop;

    -- Ocupação dos abrigos de teste = pessoas presentes (responsável + membros não desaparecidos).
    update public.abrigos a set ocupacao = sub.pessoas
    from (
        select f.abrigo_id,
               count(distinct f.id) + count(m.id) filter (where not m.desaparecido) as pessoas
        from public.familias_abrigadas f
        left join public.membros_familia m on m.familia_id = f.id
        where f.observacoes like '[TESTE]%' and f.data_saida is null
        group by f.abrigo_id
    ) sub
    where a.id = sub.abrigo_id;
end $$;

-- 10 relatos de campo de teste (autor: primeira conta administradora).
insert into public.relatos (usuario_id, municipio_id, tipo, intensidade, descricao, latitude, longitude, status,
                            confirmacoes, negacoes, criado_em)
select (select id from public.usuarios where perfil = 'administrador' order by id limit 1),
       v.municipio_id, v.tipo, v.intensidade, '[TESTE] ' || v.descricao, v.lat, v.lon, v.status,
       v.conf, v.neg, now() - (v.horas || ' hours')::interval
from (values
    ('1302405', 'rio_baixando', 'forte', 'Praias aparecendo em frente à cidade; barcos encalhando.', -7.262, -64.80, 'confirmado', 4, 0, 3),
    ('1302405', 'isolamento_comunidade', 'forte', 'Comunidade sem acesso por barco grande há 2 dias.', -7.10, -64.58, 'novo', 1, 0, 5),
    ('1300706', 'rio_baixando', 'moderada', 'Nível baixou bastante na última semana.', -8.743, -67.39, 'confirmado', 3, 0, 8),
    ('1300706', 'incendio_fumaca', 'forte', 'Fumaça densa vinda do sul, cheiro forte de queimada.', -8.80, -67.45, 'confirmado', 5, 1, 2),
    ('1300631', 'chuva_forte', 'moderada', 'Chuva forte com ventania no fim da tarde.', -3.899, -61.37, 'novo', 2, 0, 1),
    ('1302603', 'cheia_alagamento', 'fraca', 'Rua alagada após chuva, água baixando.', -3.12, -60.02, 'descartado', 0, 3, 20),
    ('1302603', 'chuva_forte', 'forte', 'Temporal com queda de árvores na zona norte.', -3.03, -59.99, 'confirmado', 6, 0, 4),
    ('1301704', 'rio_baixando', 'moderada', 'Balsa com dificuldade de atracar no porto.', -7.50, -63.02, 'novo', 1, 1, 6),
    ('1301704', 'incendio_fumaca', 'moderada', 'Foco de fogo em pasto próximo à BR-230.', -7.56, -63.10, 'novo', 0, 0, 2),
    ('1300631', 'rio_subindo', 'fraca', 'Igarapé subiu depois da chuva da noite.', -4.73, -62.15, 'novo', 0, 0, 1)
) as v(municipio_id, tipo, intensidade, descricao, lat, lon, status, conf, neg, horas);

commit;

-- Conferência
select (select count(*) from public.abrigos where nome like '[TESTE]%') as abrigos_teste,
       (select count(*) from public.familias_abrigadas where observacoes like '[TESTE]%') as familias_teste,
       (select count(*) from public.membros_familia m join public.familias_abrigadas f on f.id = m.familia_id
         where f.observacoes like '[TESTE]%') as membros_teste,
       (select count(*) from public.membros_familia m join public.familias_abrigadas f on f.id = m.familia_id
         where f.observacoes like '[TESTE]%' and m.desaparecido) as desaparecidos_teste,
       (select count(*) from public.relatos where descricao like '[TESTE]%') as relatos_teste;
