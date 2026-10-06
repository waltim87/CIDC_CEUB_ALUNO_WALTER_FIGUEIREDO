create extension if not exists postgis with schema extensions;

create table if not exists public.fontes (
    id uuid primary key default gen_random_uuid(),
    nome text not null unique,
    url text,
    tipo text not null,
    periodicidade_min integer check (periodicidade_min > 0),
    ultima_coleta timestamptz,
    status text not null default 'pendente_confirmacao',
    criado_em timestamptz not null default now()
);

create table if not exists public.municipios (
    id_ibge char(7) primary key,
    nome text not null,
    uf char(2) not null,
    calha text,
    populacao bigint check (populacao is null or populacao >= 0),
    geom extensions.geometry(MultiPolygon, 4326)
);

create table if not exists public.comunidades (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nome text not null,
    populacao_estimada bigint check (populacao_estimada is null or populacao_estimada >= 0),
    acesso_principal text,
    geom extensions.geometry(Point, 4326)
);

create table if not exists public.estacoes (
    id uuid primary key default gen_random_uuid(),
    codigo_oficial text unique,
    fonte_id uuid not null references public.fontes(id),
    nome text not null,
    rio text,
    municipio_id char(7) references public.municipios(id_ibge),
    cota_alerta numeric,
    cota_emergencia numeric,
    geom extensions.geometry(Point, 4326),
    constraint estacoes_cotas_validas check (
        cota_alerta is null or cota_emergencia is null or cota_emergencia >= cota_alerta
    )
);

create table if not exists public.leituras (
    id uuid primary key default gen_random_uuid(),
    estacao_id uuid not null references public.estacoes(id),
    data_hora_leitura timestamptz not null,
    nivel_cm numeric,
    vazao numeric,
    chuva_mm numeric,
    tendencia text,
    fonte_id uuid not null references public.fontes(id),
    coletado_em timestamptz not null default now(),
    constraint leituras_medida_informada check (
        nivel_cm is not null or vazao is not null or chuva_mm is not null
    ),
    constraint leituras_estacao_data_unica unique (estacao_id, data_hora_leitura)
);
create index if not exists leituras_estacao_data_idx
    on public.leituras (estacao_id, data_hora_leitura desc);

create table if not exists public.focos_calor (
    id uuid primary key default gen_random_uuid(),
    data_hora timestamptz not null,
    lat double precision not null check (lat between -90 and 90),
    lon double precision not null check (lon between -180 and 180),
    municipio_id char(7) references public.municipios(id_ibge),
    satelite text,
    geom extensions.geometry(Point, 4326)
);

create table if not exists public.infraestrutura (
    id uuid primary key default gen_random_uuid(),
    tipo text not null check (tipo in ('ubs', 'escola', 'porto', 'captacao', 'energia')),
    nome text not null,
    municipio_id char(7) not null references public.municipios(id_ibge),
    geom extensions.geometry(Point, 4326)
);

create table if not exists public.situacao_municipal (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    data date not null,
    situacao text not null check (situacao in ('emergencia', 'alerta', 'atencao', 'normal')),
    fonte text not null
);

create table if not exists public.regras (
    id uuid primary key default gen_random_uuid(),
    condicao_json jsonb not null,
    classe text not null,
    acao_recomendada text not null,
    reavaliar_em_horas integer not null check (reavaliar_em_horas > 0),
    ativa boolean not null default true
);

create table if not exists public.configuracao_pesos (
    id uuid primary key default gen_random_uuid(),
    nome text not null unique,
    pesos_json jsonb not null,
    validacao_oficial boolean not null default false,
    atualizado_em timestamptz not null default now(),
    constraint pesos_json_objeto check (jsonb_typeof(pesos_json) = 'object')
);

create table if not exists public.indices (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    data_hora timestamptz not null,
    score_hidrologia numeric check (score_hidrologia between 0 and 100),
    score_populacao numeric check (score_populacao between 0 and 100),
    score_infra numeric check (score_infra between 0 and 100),
    score_logistica numeric check (score_logistica between 0 and 100),
    score_vulnerabilidade numeric check (score_vulnerabilidade between 0 and 100),
    score_total numeric check (score_total between 0 and 100),
    classe text not null
);

create table if not exists public.usuarios (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    perfil text not null,
    municipio_id char(7) references public.municipios(id_ibge),
    auth_id uuid unique references auth.users(id) on delete set null
);

create table if not exists public.alertas (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    indice_id uuid references public.indices(id),
    classe text not null,
    texto text not null,
    canal text,
    criado_em timestamptz not null default now(),
    emitido_em timestamptz,
    status text not null default 'rascunho'
        check (status in ('rascunho', 'aprovado', 'enviado', 'encerrado')),
    aprovado_por uuid references public.usuarios(id)
);

create table if not exists public.recursos (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    tipo text not null check (
        tipo in ('agua', 'alimento', 'medicamento', 'oxigenio', 'combustivel', 'purificador')
    ),
    quantidade numeric not null check (quantidade >= 0),
    atualizado_em timestamptz not null default now()
);

create table if not exists public.abrigos (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nome text not null,
    capacidade integer not null check (capacidade >= 0),
    ocupacao integer not null default 0 check (ocupacao >= 0 and ocupacao <= capacidade),
    geom extensions.geometry(Point, 4326)
);

create table if not exists public.pessoas_afetadas (
    id uuid primary key default gen_random_uuid(),
    comunidade_id uuid not null references public.comunidades(id),
    familias integer not null check (familias >= 0),
    pessoas integer not null check (pessoas >= 0),
    necessidades jsonb not null default '[]'::jsonb,
    data timestamptz not null
);

create table if not exists public.acoes (
    id uuid primary key default gen_random_uuid(),
    alerta_id uuid references public.alertas(id),
    eixo text not null check (eixo in ('prevencao', 'mitigacao', 'preparacao', 'resposta', 'recuperacao')),
    descricao text not null,
    responsavel_id uuid references public.usuarios(id),
    prazo timestamptz,
    status text not null default 'pendente'
);

create table if not exists public.planos_contingencia (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null unique references public.municipios(id_ibge),
    atualizado_em timestamptz,
    possui_reguas boolean not null default false,
    rotas_alternativas jsonb not null default '[]'::jsonb
);

create table if not exists public.auditoria (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid references public.usuarios(id),
    acao text not null,
    tabela text not null,
    registro_id text,
    data_hora timestamptz not null default now()
);

create index if not exists comunidades_municipio_idx on public.comunidades (municipio_id);
create index if not exists estacoes_municipio_idx on public.estacoes (municipio_id);
create index if not exists focos_calor_data_idx on public.focos_calor (data_hora desc);
create index if not exists alertas_municipio_criado_idx
    on public.alertas (municipio_id, criado_em desc);
create index if not exists indices_municipio_data_idx
    on public.indices (municipio_id, data_hora desc);
create index if not exists usuarios_auth_id_idx on public.usuarios (auth_id);

create index if not exists municipios_geom_gix on public.municipios using gist (geom);
create index if not exists comunidades_geom_gix on public.comunidades using gist (geom);
create index if not exists estacoes_geom_gix on public.estacoes using gist (geom);
create index if not exists focos_calor_geom_gix on public.focos_calor using gist (geom);
create index if not exists infraestrutura_geom_gix on public.infraestrutura using gist (geom);
create index if not exists abrigos_geom_gix on public.abrigos using gist (geom);

alter table public.fontes enable row level security;
alter table public.municipios enable row level security;
alter table public.comunidades enable row level security;
alter table public.estacoes enable row level security;
alter table public.leituras enable row level security;
alter table public.focos_calor enable row level security;
alter table public.infraestrutura enable row level security;
alter table public.situacao_municipal enable row level security;
alter table public.regras enable row level security;
alter table public.configuracao_pesos enable row level security;
alter table public.indices enable row level security;
alter table public.usuarios enable row level security;
alter table public.alertas enable row level security;
alter table public.recursos enable row level security;
alter table public.abrigos enable row level security;
alter table public.pessoas_afetadas enable row level security;
alter table public.acoes enable row level security;
alter table public.planos_contingencia enable row level security;
alter table public.auditoria enable row level security;
