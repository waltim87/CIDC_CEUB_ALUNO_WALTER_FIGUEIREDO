insert into public.regras (
    condicao_json,
    classe,
    acao_recomendada,
    reavaliar_em_horas,
    ativa
)
select
    regras.condicao_json,
    regras.classe,
    regras.acao_recomendada,
    regras.reavaliar_em_horas,
    false
from (
    values
        (
            '{"campo":"score_total","operador":"entre","valor":[21,40]}'::jsonb,
            'Atenção',
            'Revisar as leituras e o plano municipal de contingência.',
            6
        ),
        (
            '{"campo":"score_total","operador":"entre","valor":[41,60]}'::jsonb,
            'Alerta',
            'Verificar comunidades expostas, recursos e rotas disponíveis.',
            3
        ),
        (
            '{"campo":"score_total","operador":"entre","valor":[61,80]}'::jsonb,
            'Alto',
            'Mobilizar a coordenação municipal para revisar preparação e resposta.',
            1
        ),
        (
            '{"campo":"score_total","operador":"maior_que","valor":80}'::jsonb,
            'Crítico',
            'Acionar imediatamente a coordenação responsável e validar os dados.',
            1
        )
) as regras(condicao_json, classe, acao_recomendada, reavaliar_em_horas)
where not exists (
    select 1 from public.regras existentes
    where existentes.condicao_json = regras.condicao_json
);
