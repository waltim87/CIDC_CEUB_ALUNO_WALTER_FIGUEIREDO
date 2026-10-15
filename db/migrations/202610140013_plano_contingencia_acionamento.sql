-- Plano de Contingência operacional (Plancon) com acionamento e tarefas automáticas.
--   plano_protocolo     -> o que fazer em cada nível (atenção / alerta / alto) e ameaça
--   plano_acionamentos  -> cada vez que o plano é ativado (alerta aprovado ou decisão manual)
--   acoes               -> tarefas dos 5 eixos; agora pertencem ao MUNICÍPIO (alerta é opcional)
-- Acionamento automático: quando um alerta é APROVADO por uma pessoa (o robô só cria rascunho).

-- ------------------------------------------------------------ tarefas sem depender de alerta
alter table public.acoes
    add column if not exists municipio_id char(7) references public.municipios(id_ibge),
    add column if not exists responsavel_funcao text,
    add column if not exists origem text not null default 'manual',
    add column if not exists protocolo_id uuid,
    add column if not exists acionamento_id uuid,
    add column if not exists criado_em timestamptz not null default now(),
    add column if not exists concluida_em timestamptz,
    add column if not exists observacao text;

update public.acoes a set municipio_id = al.municipio_id
  from public.alertas al where al.id = a.alerta_id and a.municipio_id is null;

alter table public.acoes drop constraint if exists acoes_status_valido;
alter table public.acoes add constraint acoes_status_valido
    check (status in ('pendente', 'em_andamento', 'concluida', 'cancelada'));
alter table public.acoes drop constraint if exists acoes_origem_valida;
alter table public.acoes add constraint acoes_origem_valida check (origem in ('manual', 'plano'));
alter table public.acoes drop constraint if exists acoes_funcao_valida;
alter table public.acoes add constraint acoes_funcao_valida check (responsavel_funcao is null or responsavel_funcao in (
    'coordenador_municipal', 'operador_monitoramento', 'agente_campo', 'saude_assistencia',
    'logistica_abastecimento', 'voluntario'));

-- Município vem do alerta quando não informado; data de conclusão automática.
create or replace function public.cidc_acoes_preencher()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
begin
    if new.municipio_id is null and new.alerta_id is not null then
        select municipio_id into new.municipio_id from public.alertas where id = new.alerta_id;
    end if;
    if new.municipio_id is null then
        raise exception 'Tarefa sem município';
    end if;
    if new.status = 'concluida' and (tg_op = 'INSERT' or old.status is distinct from 'concluida') then
        new.concluida_em := now();
    elsif new.status <> 'concluida' then
        new.concluida_em := null;
    end if;
    return new;
end;
$$;
drop trigger if exists acoes_preencher on public.acoes;
create trigger acoes_preencher before insert or update on public.acoes
    for each row execute function public.cidc_acoes_preencher();

create index if not exists acoes_municipio_idx on public.acoes (municipio_id, status);

-- Quem pode atualizar uma tarefa: coordenação/admin, o responsável nomeado, ou quem tem
-- a FUNÇÃO indicada no município (ex.: a saúde de Lábrea atualiza tarefas da saúde de Lábrea).
create or replace function public.cidc_pode_executar_acao(p_municipio_id char(7), p_funcao text, p_responsavel uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_pode_operar_municipio(p_municipio_id)
        or p_responsavel = public.cidc_usuario_id_atual()
        or (p_funcao is not null
            and p_funcao = public.cidc_perfil_atual()
            and public.cidc_municipio_atual() = p_municipio_id)
$$;

drop policy if exists acoes_select_escopo on public.acoes;
create policy acoes_select_escopo on public.acoes
    for select to authenticated
    using (
        public.cidc_pode_ver_municipio(municipio_id)
        or responsavel_id = public.cidc_usuario_id_atual()
        or public.cidc_perfil_atual() = 'operador_monitoramento'
    );
drop policy if exists acoes_operacao_escopo on public.acoes;
drop policy if exists acoes_insert on public.acoes;
create policy acoes_insert on public.acoes
    for insert to authenticated
    with check (public.cidc_pode_operar_municipio(municipio_id));
drop policy if exists acoes_update on public.acoes;
create policy acoes_update on public.acoes
    for update to authenticated
    using (public.cidc_pode_executar_acao(municipio_id, responsavel_funcao, responsavel_id))
    with check (public.cidc_pode_executar_acao(municipio_id, responsavel_funcao, responsavel_id));
drop policy if exists acoes_delete on public.acoes;
create policy acoes_delete on public.acoes
    for delete to authenticated using (public.cidc_pode_operar_municipio(municipio_id));
grant select, insert, update, delete on public.acoes to authenticated;

-- ------------------------------------------------------------ protocolo do plano
create table if not exists public.plano_protocolo (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nivel text not null check (nivel in ('atencao', 'alerta', 'alto')),
    ameaca text not null default 'qualquer' check (ameaca in ('cheia', 'seca', 'incendio', 'qualquer')),
    eixo text not null check (eixo in ('prevencao', 'mitigacao', 'preparacao', 'resposta', 'recuperacao')),
    descricao text not null check (length(trim(descricao)) between 5 and 300),
    responsavel_funcao text check (responsavel_funcao is null or responsavel_funcao in (
        'coordenador_municipal', 'operador_monitoramento', 'agente_campo', 'saude_assistencia',
        'logistica_abastecimento', 'voluntario')),
    prazo_horas integer not null default 24 check (prazo_horas between 1 and 2160),
    ordem integer not null default 100,
    ativo boolean not null default true,
    criado_em timestamptz not null default now()
);
create index if not exists plano_protocolo_municipio_idx on public.plano_protocolo (municipio_id, nivel);

create table if not exists public.plano_acionamentos (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    nivel text not null check (nivel in ('atencao', 'alerta', 'alto')),
    ameaca text not null check (ameaca in ('cheia', 'seca', 'incendio', 'qualquer')),
    origem text not null check (origem in ('alerta_aprovado', 'manual')),
    alerta_id uuid references public.alertas(id) on delete set null,
    acionado_por uuid references public.usuarios(id) on delete set null,
    acionado_em timestamptz not null default now(),
    tarefas_criadas integer not null default 0,
    encerrado_em timestamptz,
    observacao text
);
create index if not exists plano_acionamentos_municipio_idx on public.plano_acionamentos (municipio_id, acionado_em desc);

alter table public.acoes drop constraint if exists acoes_protocolo_fk;
alter table public.acoes add constraint acoes_protocolo_fk
    foreign key (protocolo_id) references public.plano_protocolo(id) on delete set null;
alter table public.acoes drop constraint if exists acoes_acionamento_fk;
alter table public.acoes add constraint acoes_acionamento_fk
    foreign key (acionamento_id) references public.plano_acionamentos(id) on delete set null;

alter table public.plano_protocolo enable row level security;
alter table public.plano_acionamentos enable row level security;

drop policy if exists plano_protocolo_select on public.plano_protocolo;
create policy plano_protocolo_select on public.plano_protocolo
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists plano_protocolo_escrita on public.plano_protocolo;
create policy plano_protocolo_escrita on public.plano_protocolo
    for all to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));
grant select, insert, update, delete on public.plano_protocolo to authenticated;

drop policy if exists plano_acionamentos_select on public.plano_acionamentos;
create policy plano_acionamentos_select on public.plano_acionamentos
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists plano_acionamentos_encerrar on public.plano_acionamentos;
create policy plano_acionamentos_encerrar on public.plano_acionamentos
    for update to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));
grant select, update (encerrado_em, observacao) on public.plano_acionamentos to authenticated;

-- ------------------------------------------------------------ acionar o plano
-- Cria as tarefas do protocolo para o nível (inclui os níveis abaixo: no "alto" entram também
-- as tarefas de atenção e alerta) e a ameaça. Não duplica tarefa ainda aberta do mesmo item.
-- Interna: sem conferência de permissão; só o gatilho do alerta e a função pública a chamam.
create or replace function public.cidc_acionar_plano_interno(
    p_municipio_id char(7),
    p_nivel text,
    p_ameaca text,
    p_alerta_id uuid,
    p_observacao text
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_niveis text[];
    v_id uuid;
    v_total integer;
begin
    v_niveis := case p_nivel
        when 'atencao' then array['atencao']
        when 'alerta' then array['atencao', 'alerta']
        when 'alto' then array['atencao', 'alerta', 'alto']
    end;
    if v_niveis is null then
        raise exception 'Nível inválido: %', p_nivel;
    end if;

    insert into public.plano_acionamentos (municipio_id, nivel, ameaca, origem, alerta_id, acionado_por, observacao)
    values (p_municipio_id, p_nivel, coalesce(p_ameaca, 'qualquer'),
            case when p_alerta_id is null then 'manual' else 'alerta_aprovado' end,
            p_alerta_id, public.cidc_usuario_id_atual(), nullif(trim(coalesce(p_observacao, '')), ''))
    returning id into v_id;

    insert into public.acoes (municipio_id, alerta_id, eixo, descricao, responsavel_funcao, prazo,
                              status, origem, protocolo_id, acionamento_id)
    select p.municipio_id, p_alerta_id, p.eixo, p.descricao, p.responsavel_funcao,
           now() + p.prazo_horas * interval '1 hour', 'pendente', 'plano', p.id, v_id
      from public.plano_protocolo p
     where p.municipio_id = p_municipio_id
       and p.ativo
       and p.nivel = any(v_niveis)
       and (p.ameaca = 'qualquer' or p.ameaca = coalesce(p_ameaca, 'qualquer') or coalesce(p_ameaca, 'qualquer') = 'qualquer')
       and not exists (
           select 1 from public.acoes a
            where a.protocolo_id = p.id and a.status in ('pendente', 'em_andamento'))
     order by p.ordem, p.prazo_horas;
    get diagnostics v_total = row_count;
    update public.plano_acionamentos set tarefas_criadas = v_total where id = v_id;
    return v_id;
end;
$$;

-- Pública (app): acionamento manual, só coordenação municipal ou administração.
create or replace function public.cidc_acionar_plano(
    p_municipio_id char(7),
    p_nivel text,
    p_ameaca text default 'qualquer',
    p_observacao text default null
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
begin
    if not public.cidc_pode_operar_municipio(p_municipio_id) then
        raise exception 'Só a coordenação municipal ou a administração aciona o plano';
    end if;
    return public.cidc_acionar_plano_interno(p_municipio_id, p_nivel, p_ameaca, null, p_observacao);
end;
$$;

-- Ameaça de um alerta do robô: rio subindo = cheia; descendo = seca; estável = pela posição
-- na faixa histórica (abaixo de 50% = perto da seca recorde).
create or replace function public.cidc_ameaca_do_alerta(p_alerta_id uuid)
returns text
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce((
        select case
            when ar.direcao = 'subindo' then 'cheia'
            when ar.direcao = 'descendo' then 'seca'
            when (select avg((e ->> 'posicao_pct')::numeric) from jsonb_array_elements(coalesce(ar.estacoes_json, '[]'::jsonb)) e
                   where e ->> 'posicao_pct' is not null) < 50 then 'seca'
            when exists (select 1 from jsonb_array_elements(coalesce(ar.estacoes_json, '[]'::jsonb)) e
                          where e ->> 'posicao_pct' is not null) then 'cheia'
        end
          from public.alertas al join public.analises_risco ar on ar.id = al.analise_id
         where al.id = p_alerta_id), 'qualquer')
$$;

create or replace function public.cidc_alerta_aciona_plano()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_nivel text := case lower(new.classe)
        when 'atenção' then 'atencao' when 'atencao' then 'atencao'
        when 'alerta' then 'alerta'
        when 'alto' then 'alto' when 'crítico' then 'alto' when 'critico' then 'alto'
    end;
begin
    if new.status = 'aprovado' and old.status is distinct from 'aprovado' and v_nivel is not null
       and exists (select 1 from public.plano_protocolo where municipio_id = new.municipio_id and ativo) then
        perform public.cidc_acionar_plano_interno(new.municipio_id, v_nivel, public.cidc_ameaca_do_alerta(new.id), new.id,
                                          'Acionado ao aprovar o alerta ' || new.classe);
    end if;
    return new;
end;
$$;
drop trigger if exists alerta_aciona_plano on public.alertas;
create trigger alerta_aciona_plano after update of status on public.alertas
    for each row execute function public.cidc_alerta_aciona_plano();

-- ------------------------------------------------------------ modelo sugerido de protocolo
-- Ponto de partida genérico para municípios ribeirinhos do Amazonas. A coordenação revisa,
-- apaga e inclui ações conforme o seu plano oficial.
create or replace function public.cidc_carregar_modelo_plano(p_municipio_id char(7))
returns integer
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    v_total integer;
begin
    if not public.cidc_pode_operar_municipio(p_municipio_id) then
        raise exception 'Só a coordenação municipal ou a administração edita o plano';
    end if;
    if exists (select 1 from public.plano_protocolo where municipio_id = p_municipio_id) then
        raise exception 'Este município já tem protocolo; edite as ações existentes';
    end if;
    insert into public.plano_protocolo (municipio_id, nivel, ameaca, eixo, descricao, responsavel_funcao, prazo_horas, ordem)
    select p_municipio_id, m.nivel, m.ameaca, m.eixo, m.descricao, m.funcao, m.prazo, m.ordem
      from (values
        ('atencao', 'qualquer', 'preparacao', 'Acompanhar estações e réguas duas vezes ao dia e registrar no painel', 'operador_monitoramento', 24, 10),
        ('atencao', 'qualquer', 'preparacao', 'Avisar lideranças comunitárias e voluntários (chat interno e Telegram)', 'coordenador_municipal', 12, 20),
        ('atencao', 'qualquer', 'preparacao', 'Conferir estoques: água potável, cestas básicas, kits de higiene e combustível', 'logistica_abastecimento', 48, 30),
        ('atencao', 'cheia', 'preparacao', 'Vistoriar abrigos: água, energia, banheiros, cozinha e acessibilidade', 'logistica_abastecimento', 48, 40),
        ('atencao', 'cheia', 'prevencao', 'Atualizar a lista de famílias em áreas de risco de inundação e de terras caídas', 'agente_campo', 72, 50),
        ('atencao', 'seca', 'preparacao', 'Mapear comunidades que podem ficar isoladas e rotas alternativas de acesso', 'logistica_abastecimento', 72, 60),
        ('atencao', 'seca', 'preparacao', 'Verificar captação e qualidade da água nas comunidades', 'saude_assistencia', 72, 70),
        ('atencao', 'incendio', 'prevencao', 'Orientar a população sobre queimadas e fumaça (rádio, escolas, igrejas)', 'coordenador_municipal', 48, 80),
        ('alerta', 'cheia', 'resposta', 'Abrir os abrigos prioritários e designar coordenadores de abrigo', 'coordenador_municipal', 12, 110),
        ('alerta', 'cheia', 'resposta', 'Mobilizar embarcações, pilotos e combustível', 'logistica_abastecimento', 12, 120),
        ('alerta', 'cheia', 'resposta', 'Remover famílias das áreas de risco alto e cadastrar as abrigadas', 'agente_campo', 24, 130),
        ('alerta', 'qualquer', 'resposta', 'Equipe de saúde nos abrigos e comunidades: triagem, medicamentos e vacinas', 'saude_assistencia', 24, 140),
        ('alerta', 'qualquer', 'resposta', 'Comunicar escolas, unidades de saúde e serviços que podem ser atingidos', 'coordenador_municipal', 12, 150),
        ('alerta', 'seca', 'resposta', 'Levar água potável e alimentos às comunidades isoladas', 'logistica_abastecimento', 24, 160),
        ('alerta', 'incendio', 'resposta', 'Acionar Corpo de Bombeiros e brigadas; mapear focos próximos a comunidades', 'coordenador_municipal', 12, 170),
        ('alerta', 'incendio', 'resposta', 'Atenção a doenças respiratórias: avisar unidades de saúde e grupos de risco', 'saude_assistencia', 24, 180),
        ('alto', 'qualquer', 'resposta', 'Avaliar decreto de Situação de Emergência e solicitar apoio estadual e federal', 'coordenador_municipal', 24, 210),
        ('alto', 'qualquer', 'resposta', 'Registrar danos, afetados, desalojados e desabrigados para o S2iD', 'agente_campo', 48, 220),
        ('alto', 'qualquer', 'resposta', 'Organizar a distribuição de ajuda humanitária por família, sem duplicar', 'logistica_abastecimento', 24, 230),
        ('alto', 'qualquer', 'recuperacao', 'Planejar o retorno das famílias e o levantamento das casas danificadas', 'coordenador_municipal', 168, 240)
      ) m(nivel, ameaca, eixo, descricao, funcao, prazo, ordem);
    get diagnostics v_total = row_count;
    return v_total;
end;
$$;

revoke all on function public.cidc_pode_executar_acao(char, text, uuid) from public;
revoke all on function public.cidc_acionar_plano_interno(char, text, text, uuid, text) from public;
revoke all on function public.cidc_acionar_plano_interno(char, text, text, uuid, text) from authenticated, anon;
revoke all on function public.cidc_acionar_plano(char, text, text, text) from public;
revoke all on function public.cidc_alerta_aciona_plano() from public;
revoke all on function public.cidc_ameaca_do_alerta(uuid) from public;
revoke all on function public.cidc_carregar_modelo_plano(char) from public;
grant execute on function public.cidc_pode_executar_acao(char, text, uuid) to authenticated;
grant execute on function public.cidc_acionar_plano(char, text, text, text) to authenticated;
grant execute on function public.cidc_carregar_modelo_plano(char) to authenticated;
