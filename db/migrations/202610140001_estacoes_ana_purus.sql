-- Ativa a coleta ANA: cadastra estações reais do Purus (AM) da telemetria
-- pública da ANA e remove os marcadores pendentes sem código oficial.
-- Códigos, nomes e coordenadas: inventário ANA HIDRO consultado em 03-04/10/2026
-- e consultas reais ao ServiceANA em 14/10/2026.
-- Cotas de alerta/emergência ficam NULAS até virem de fonte oficial (SGB/SACE).

update public.fontes
set url = 'https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos'
where nome = 'ANA HidroWebService';

insert into public.estacoes (codigo_oficial, fonte_id, nome, rio, municipio_id, geom)
select
    candidatas.codigo,
    fontes.id,
    candidatas.nome,
    'Purus',
    candidatas.municipio_id,
    extensions.st_setsrid(extensions.st_makepoint(candidatas.lon, candidatas.lat), 4326)
from public.fontes
cross join (
    values
        ('13410000', 'SERINGAL DA CARIDADE', '1300706', -9.0439::float8, -68.5772::float8),
        ('13870000', 'LÁBREA', '1302405', -7.2581::float8, -64.7975::float8),
        ('13962000', 'ARUMÃ - JUSANTE', '1300631', -4.7286::float8, -62.1453::float8),
        ('13990000', 'BERURI', '1300631', -3.8989::float8, -61.3742::float8)
) as candidatas(codigo, nome, municipio_id, lat, lon)
where fontes.nome = 'ANA HidroWebService'
on conflict (codigo_oficial) do update
set nome = excluded.nome,
    rio = excluded.rio,
    municipio_id = excluded.municipio_id,
    geom = excluded.geom;

-- Marcadores do seed da Fase 1 (sem código oficial e sem leituras).
delete from public.estacoes e
where e.codigo_oficial is null
  and e.nome like 'PENDENTE: confirmar estação ANA no Purus%'
  and not exists (select 1 from public.leituras l where l.estacao_id = e.id);
