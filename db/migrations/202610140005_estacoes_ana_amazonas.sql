-- Estações telemétricas de rio da ANA no Amazonas que transmitiam nível em
-- 14/10/2026: 49 estações em 27 municípios.
-- Gerado por scripts/inventario_estacoes_am.py + scripts/gerar_migration_estacoes.py.
-- Marcadores de cheia/seca: preenchidos automaticamente por collectors/marcadores.py.

alter table public.estacoes
    add column if not exists latitude double precision,
    add column if not exists longitude double precision;

insert into public.estacoes (codigo_oficial, fonte_id, nome, rio, municipio_id, latitude, longitude, geom)
select
    v.codigo, f.id, v.nome, v.rio, v.municipio_id, v.lat, v.lon,
    extensions.st_setsrid(extensions.st_makepoint(v.lon, v.lat), 4326)
from public.fontes f
cross join (
values
    ('10100000', 'TABATINGA', 'Solimões-Amazonas', '1304062', -4.2347, -69.9447),
    ('10200000', 'PALMEIRAS DO JAVARI', 'Javari', '1300201', -5.1389, -72.8136),
    ('10910000', 'LADÁRIO - JUSANTE', 'Itacuai', '1300201', -4.5836, -70.2644),
    ('11400000', 'SÃO PAULO DE OLIVENÇA', 'Solimões-Amazonas', '1303908', -3.4569, -68.9119),
    ('11500000', 'SANTO ANTÔNIO DO IÇÁ', 'Solimões-Amazonas', '1303700', -3.1017, -67.9356),
    ('12520000', 'IPIXUNA', 'Juruá', '1301803', -7.0556, -71.6892),
    ('12680000', 'ENVIRA', 'Tarauacá', '1301506', -7.4281, -70.0225),
    ('12700000', 'SANTOS DUMONT', 'Juruá', '1301951', -6.4403, -68.2461),
    ('12845000', 'VILA BITTENCOURT', 'Caquetá/Japurá', '1302108', -1.3947, -69.4283),
    ('12850000', 'ACANAUI', 'Caquetá/Japurá', '1302108', -1.8211, -66.6092),
    ('12900001', 'TEFÉ - MISSÕES', 'Solimões-Amazonas', '1304203', -3.3758, -64.6547),
    ('13100000', 'SERINGAL MOREIRA', 'Coari', '1301209', -5.1092, -63.9847),
    ('13150003', 'COARI', 'Solimões-Amazonas', '1301209', -4.0856, -63.0833),
    ('13410000', 'SERINGAL DA CARIDADE', 'Purus', '1300706', -9.0439, -68.5772),
    ('13650000', 'FLORIANO PEIXOTO', 'Acre', '1300706', -9.0667, -67.3969),
    ('13870000', 'LÁBREA', 'Purus', '1302405', -7.2581, -64.7975),
    ('13885000', 'CRISTO', 'Mucuim', '1302405', -7.4644, -64.2433),
    ('13990000', 'BERURI', 'Purus', '1300631', -3.8989, -61.3742),
    ('14100000', 'MANACAPURU', 'Solimões-Amazonas', '1302504', -3.3106, -60.6094),
    ('14110000', 'CUCUÍ', 'Negro', '1303809', 1.2153, -66.8525),
    ('14280001', 'TARAQUÁ', 'Vaupés/Uaupés', '1303809', 0.1303, -68.5386),
    ('14330000', 'CURICURIARI', 'Negro', '1303809', -0.2006, -66.8022),
    ('14420000', 'SERRINHA', 'Negro', '1303601', -0.4819, -64.8289),
    ('14480002', 'BARCELOS', 'Negro', '1300409', -0.9658, -62.9311),
    ('14840000', 'MOURA', 'Negro', '1300409', -1.4567, -61.6347),
    ('14990000', 'MANAUS', 'Negro', '1302603', -3.1383, -60.0272),
    ('15030000', 'JATUARANA', 'Solimões-Amazonas', '1302603', -3.0633, -59.6478),
    ('15627320', 'SÃO RAFAEL', 'Madeira', '1301704', -6.5136, -62.3264),
    ('15627360', 'MOANENSE', 'Madeira', '1301704', -6.9958, -62.8183),
    ('15629000', 'UHE SANTO ANTÔNIO HUMAITÁ', 'Madeira', '1301704', -7.5053, -63.0211),
    ('15630000', 'HUMAITÁ', 'Madeira', '1301704', -7.5028, -63.0183),
    ('15700050', 'CURUÇÁ', 'Madeira', '1302702', -6.0353, -61.6922),
    ('15850050', 'NOVO ARIPUANÃ', 'Madeira', '1302702', -5.0803, -60.3233),
    ('15850060', 'MACACO  PREGO', 'Madeira', '1302702', -5.4508, -60.7272),
    ('15860000', 'FAZENDA VISTA ALEGRE', 'Madeira', '1303304', -4.8972, -60.0253),
    ('15910000', 'SANTARÉM SUCUNDURI', 'Sucunduri', '1300144', -6.7956, -59.0422),
    ('15960060', 'URUCURITUBA', 'Madeira', '1300300', -3.5489, -58.9269),
    ('16018000', 'UHE PITINGA MONTANTE', 'Pitinga', '1303536', -0.585, -59.7761),
    ('16019000', 'UHE PITINGA SERRA', 'Igarapé Da Serra', '1303536', -0.5956, -59.7772),
    ('16020000', 'UHE PITINGA BARRAMENTO', 'Pitinga', '1303536', -0.8658, -59.6047),
    ('16020100', 'UHE PITINGA JUSANTE', 'Pitinga', '1303536', -0.8661, -59.6011),
    ('16020200', 'UHE BALBINA RIO PITINGA', 'Pitinga', '1303536', -0.9911, -59.4797),
    ('16030000', 'ITACOATIARA', 'Solimões-Amazonas', '1301902', -3.1539, -58.4114),
    ('16062000', 'UHE BALBINA MONTANTE', 'Uatumã', '1303536', -1.2106, -60.2347),
    ('16070980', 'UHE BALBINA BARRAMENTO', 'Uatumã', '1303536', -1.9161, -59.4756),
    ('16090000', 'UHE BALBINA JUSANTE', 'Uatumã', '1303536', -1.9494, -59.4767),
    ('16100000', 'CACHOEIRA MORENA', 'Uatumã', '1303536', -2.1061, -59.3442),
    ('16350002', 'PARINTINS', 'Solimões-Amazonas', '1303403', -2.6306, -56.7519),
    ('17430000', 'BARRA DO SÃO MANUEL', 'Tapajós', '1300805', -7.3397, -58.1553)
) as v(codigo, nome, rio, municipio_id, lat, lon)
where f.nome = 'ANA HidroWebService'
on conflict (codigo_oficial) do update
set nome = excluded.nome,
    rio = excluded.rio,
    municipio_id = excluded.municipio_id,
    latitude = excluded.latitude,
    longitude = excluded.longitude,
    geom = excluded.geom;

-- O robô grava os marcadores históricos calculados (somente estas colunas).
grant update (
    cheia_historica_cm, cheia_historica_data, seca_historica_cm, seca_historica_data, historico_fonte
) on public.estacoes to service_role;
