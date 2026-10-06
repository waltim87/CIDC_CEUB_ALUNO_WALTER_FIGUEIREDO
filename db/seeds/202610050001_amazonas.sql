insert into public.fontes (nome, url, tipo, periodicidade_min, status)
values
    (
        'ANA HidroWebService',
        null,
        'hidrologia',
        60,
        'pendente_confirmacao'
    ),
    (
        'INPE Queimadas',
        'https://www.gov.br/inpe/pt-br/acesso-a-informacao/dados-abertos/monitoramento-ambiental/monitoramento-de-queimadas',
        'focos_calor',
        1440,
        'pendente_confirmacao'
    ),
    (
        'INMET',
        'https://portal.inmet.gov.br/dadoshistoricos',
        'meteorologia',
        60,
        'pendente_confirmacao'
    ),
    (
        'SGB SACE',
        null,
        'alertas_hidrologicos',
        60,
        'pendente_confirmacao'
    ),
    (
        'Cemaden PED',
        'https://sws.cemaden.gov.br/PED/api/ui/swagger.json',
        'monitoramento',
        60,
        'pendente_confirmacao'
    ),
    (
        'IBGE API de Localidades',
        'https://servicodados.ibge.gov.br/api/v1/localidades/estados/13/municipios',
        'municipios',
        10080,
        'operacional'
    ),
    (
        'CNES Dados Abertos',
        'https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude',
        'infraestrutura_saude',
        10080,
        'pendente_confirmacao'
    ),
    (
        'INEP Dados Abertos',
        'https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos',
        'infraestrutura_escolar',
        43200,
        'pendente_confirmacao'
    )
on conflict (nome) do update
set url = excluded.url,
    tipo = excluded.tipo,
    periodicidade_min = excluded.periodicidade_min;

insert into public.municipios (id_ibge, nome, uf)
values
    ('1300029', 'Alvarães', 'AM'),
    ('1300060', 'Amaturá', 'AM'),
    ('1300086', 'Anamã', 'AM'),
    ('1300102', 'Anori', 'AM'),
    ('1300144', 'Apuí', 'AM'),
    ('1300201', 'Atalaia do Norte', 'AM'),
    ('1300300', 'Autazes', 'AM'),
    ('1300409', 'Barcelos', 'AM'),
    ('1300508', 'Barreirinha', 'AM'),
    ('1300607', 'Benjamin Constant', 'AM'),
    ('1300631', 'Beruri', 'AM'),
    ('1300680', 'Boa Vista do Ramos', 'AM'),
    ('1300706', 'Boca do Acre', 'AM'),
    ('1300805', 'Borba', 'AM'),
    ('1300839', 'Caapiranga', 'AM'),
    ('1300904', 'Canutama', 'AM'),
    ('1301001', 'Carauari', 'AM'),
    ('1301100', 'Careiro', 'AM'),
    ('1301159', 'Careiro da Várzea', 'AM'),
    ('1301209', 'Coari', 'AM'),
    ('1301308', 'Codajás', 'AM'),
    ('1301407', 'Eirunepé', 'AM'),
    ('1301506', 'Envira', 'AM'),
    ('1301605', 'Fonte Boa', 'AM'),
    ('1301654', 'Guajará', 'AM'),
    ('1301704', 'Humaitá', 'AM'),
    ('1301803', 'Ipixuna', 'AM'),
    ('1301852', 'Iranduba', 'AM'),
    ('1301902', 'Itacoatiara', 'AM'),
    ('1301951', 'Itamarati', 'AM'),
    ('1302009', 'Itapiranga', 'AM'),
    ('1302108', 'Japurá', 'AM'),
    ('1302207', 'Juruá', 'AM'),
    ('1302306', 'Jutaí', 'AM'),
    ('1302405', 'Lábrea', 'AM'),
    ('1302504', 'Manacapuru', 'AM'),
    ('1302553', 'Manaquiri', 'AM'),
    ('1302603', 'Manaus', 'AM'),
    ('1302702', 'Manicoré', 'AM'),
    ('1302801', 'Maraã', 'AM'),
    ('1302900', 'Maués', 'AM'),
    ('1303007', 'Nhamundá', 'AM'),
    ('1303106', 'Nova Olinda do Norte', 'AM'),
    ('1303205', 'Novo Airão', 'AM'),
    ('1303304', 'Novo Aripuanã', 'AM'),
    ('1303403', 'Parintins', 'AM'),
    ('1303502', 'Pauini', 'AM'),
    ('1303536', 'Presidente Figueiredo', 'AM'),
    ('1303569', 'Rio Preto da Eva', 'AM'),
    ('1303601', 'Santa Isabel do Rio Negro', 'AM'),
    ('1303700', 'Santo Antônio do Içá', 'AM'),
    ('1303809', 'São Gabriel da Cachoeira', 'AM'),
    ('1303908', 'São Paulo de Olivença', 'AM'),
    ('1303957', 'São Sebastião do Uatumã', 'AM'),
    ('1304005', 'Silves', 'AM'),
    ('1304062', 'Tabatinga', 'AM'),
    ('1304104', 'Tapauá', 'AM'),
    ('1304203', 'Tefé', 'AM'),
    ('1304237', 'Tonantins', 'AM'),
    ('1304260', 'Uarini', 'AM'),
    ('1304302', 'Urucará', 'AM'),
    ('1304401', 'Urucurituba', 'AM')
on conflict (id_ibge) do update
set nome = excluded.nome,
    uf = excluded.uf;

insert into public.estacoes (codigo_oficial, fonte_id, nome, rio, municipio_id)
select
    null,
    fontes.id,
    candidatos.nome,
    'Purus',
    candidatos.municipio_id
from public.fontes
cross join (
    values
        ('PENDENTE: confirmar estação ANA no Purus - Lábrea/AM', '1302405'),
        ('PENDENTE: confirmar estação ANA no Purus - Beruri/AM', '1300631'),
        ('PENDENTE: confirmar estação ANA no Purus - Boca do Acre/AM', '1300706')
) as candidatos(nome, municipio_id)
where fontes.nome = 'ANA HidroWebService'
  and not exists (
      select 1
      from public.estacoes existentes
      where existentes.codigo_oficial is null
        and existentes.nome = candidatos.nome
  );

insert into public.configuracao_pesos (nome, pesos_json, validacao_oficial)
values (
    'hipotese_inicial_indice_impacto_humanitario',
    '{"hidrologia":30,"populacao":25,"infraestrutura":20,"logistica":15,"vulnerabilidade_duracao":10}'::jsonb,
    false
)
on conflict (nome) do update
set pesos_json = excluded.pesos_json,
    validacao_oficial = false,
    atualizado_em = now();
