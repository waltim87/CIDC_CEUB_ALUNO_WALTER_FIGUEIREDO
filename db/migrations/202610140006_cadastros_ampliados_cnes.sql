-- Campos ampliados dos cadastros e importação de estabelecimentos de saúde do CNES.
-- Colunas latitude/longitude ficam legíveis no painel; geom continua disponível.

-- Infraestrutura crítica (inclui estabelecimentos de saúde importados do CNES).
alter table public.infraestrutura
    add column if not exists endereco text,
    add column if not exists bairro text,
    add column if not exists cep text,
    add column if not exists telefone text,
    add column if not exists email text,
    add column if not exists responsavel text,
    add column if not exists observacoes text,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists cnes_codigo text,
    add column if not exists tipo_unidade text,
    add column if not exists esfera text,
    add column if not exists turno text,
    add column if not exists atendimento_hospitalar boolean,
    add column if not exists centro_cirurgico boolean,
    add column if not exists centro_obstetrico boolean,
    add column if not exists fonte text not null default 'cadastro manual',
    add column if not exists atualizado_em timestamptz not null default now();
create unique index if not exists infraestrutura_cnes_unico
    on public.infraestrutura (cnes_codigo) where cnes_codigo is not null;

-- Comunidades.
alter table public.comunidades
    add column if not exists rio text,
    add column if not exists distancia_sede_km numeric check (distancia_sede_km is null or distancia_sede_km >= 0),
    add column if not exists tempo_acesso_horas numeric check (tempo_acesso_horas is null or tempo_acesso_horas >= 0),
    add column if not exists contato_nome text,
    add column if not exists contato_telefone text,
    add column if not exists populacao_fonte text,
    add column if not exists observacoes text,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists atualizado_em timestamptz not null default now();

-- Abrigos.
alter table public.abrigos
    add column if not exists tipo_local text,
    add column if not exists endereco text,
    add column if not exists responsavel text,
    add column if not exists telefone text,
    add column if not exists possui_agua boolean,
    add column if not exists possui_energia boolean,
    add column if not exists possui_banheiro boolean,
    add column if not exists acessivel boolean,
    add column if not exists observacoes text,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists atualizado_em timestamptz not null default now();

-- Recursos (estoques).
alter table public.recursos
    add column if not exists unidade text,
    add column if not exists local_armazenamento text,
    add column if not exists validade date,
    add column if not exists responsavel text,
    add column if not exists observacoes text;

-- Plano de contingência.
alter table public.planos_contingencia
    add column if not exists responsavel text,
    add column if not exists telefone text,
    add column if not exists link_documento text,
    add column if not exists validade date,
    add column if not exists observacoes text;

-- Situação oficial.
alter table public.situacao_municipal
    add column if not exists link text,
    add column if not exists observacoes text;

-- Registro de campo.
alter table public.pessoas_afetadas
    add column if not exists desalojados integer check (desalojados is null or desalojados >= 0),
    add column if not exists desabrigados integer check (desabrigados is null or desabrigados >= 0),
    add column if not exists observacoes text,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision;

-- Importação semanal do CNES pelo GitHub Actions (collectors/cnes.py).
grant select, insert, update on public.infraestrutura to service_role;
grant select, update on public.fontes to service_role;
update public.fontes
set url = 'https://apidadosabertos.saude.gov.br/cnes/estabelecimentos'
where nome = 'CNES Dados Abertos';
