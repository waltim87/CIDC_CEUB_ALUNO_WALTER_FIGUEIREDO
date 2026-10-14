-- Análises de risco geradas pelo robô (core/robo.py) a cada 3 horas.
-- São TRIAGEM INDICATIVA: hipóteses sem validação oficial, não substituem
-- alertas aprovados por humano. O texto pode vir da IA (Gemini, camada gratuita)
-- ou do modelo fixo quando a IA falha ou cita números fora dos dados.

create table if not exists public.analises_risco (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    gerado_em timestamptz not null default now(),
    sinal text not null check (
        sinal in ('sem_dados', 'normal', 'atencao', 'alerta', 'alto')
    ),
    direcao text check (direcao in ('subindo', 'descendo', 'estavel')),
    texto text not null,
    metodo text not null check (metodo in ('ia', 'modelo_fixo')),
    modelo text,
    fatores_json jsonb not null default '[]'::jsonb,
    estacoes_json jsonb not null default '[]'::jsonb,
    fontes_json jsonb not null default '[]'::jsonb,
    data_hora_leitura_referencia timestamptz
);

create index if not exists analises_risco_municipio_data
    on public.analises_risco (municipio_id, gerado_em desc);

alter table public.analises_risco enable row level security;

drop policy if exists analises_select_escopo on public.analises_risco;
create policy analises_select_escopo on public.analises_risco
    for select to authenticated
    using (
        public.cidc_pode_ver_municipio(municipio_id)
        or public.cidc_perfil_atual() = 'operador_monitoramento'
    );

grant select on public.analises_risco to authenticated;
grant select, insert, delete on public.analises_risco to service_role;
-- O robô lê séries de leituras e as estações com coordenadas.
grant select on public.leituras, public.estacoes, public.municipios to service_role;
