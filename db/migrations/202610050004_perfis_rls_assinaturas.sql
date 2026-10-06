create or replace function public.cidc_perfil_atual()
returns text
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select perfil
    from public.usuarios
    where auth_id = (select auth.uid())
    limit 1
$$;

create or replace function public.cidc_municipio_atual()
returns char(7)
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select municipio_id
    from public.usuarios
    where auth_id = (select auth.uid())
    limit 1
$$;

create or replace function public.cidc_usuario_id_atual()
returns uuid
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select id
    from public.usuarios
    where auth_id = (select auth.uid())
    limit 1
$$;

create or replace function public.cidc_administrador()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_perfil_atual() = 'administrador', false)
$$;

create or replace function public.cidc_gestor_global()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(
        public.cidc_perfil_atual() in (
            'gestor_nacional',
            'operador_monitoramento',
            'administrador'
        ),
        false
    )
$$;

create or replace function public.cidc_pode_ver_municipio(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_perfil_atual() in (
            'gestor_nacional',
            'administrador'
        )
        or (
            public.cidc_perfil_atual() = 'gestor_estadual'
            and exists (
                select 1
                from public.municipios municipio_atribuido
                join public.municipios municipio_alvo
                  on municipio_alvo.id_ibge = p_municipio_id
                where municipio_atribuido.id_ibge = public.cidc_municipio_atual()
                  and municipio_atribuido.uf = municipio_alvo.uf
            )
        )
        or (
            public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'agente_campo',
                'saude_assistencia',
                'logistica_abastecimento'
            )
            and public.cidc_municipio_atual() = p_municipio_id
        )
$$;

create or replace function public.cidc_pode_operar_municipio(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() = 'coordenador_municipal'
        )
$$;

create or replace function public.cidc_pode_registrar_afetados(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'agente_campo'
            )
        )
$$;

create or replace function public.cidc_pode_gerenciar_abrigo(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'logistica_abastecimento'
            )
        )
$$;

create or replace function public.cidc_pode_gerenciar_notificacoes(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_administrador()
        or (
            public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'logistica_abastecimento'
            )
            and public.cidc_municipio_atual() = p_municipio_id
        )
$$;

create or replace function public.cidc_pode_revisar_alerta(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select public.cidc_perfil_atual() in (
        'administrador',
        'gestor_nacional',
        'operador_monitoramento'
    )
    or (
        public.cidc_perfil_atual() = 'gestor_estadual'
        and exists (
            select 1
            from public.municipios municipio_atribuido
            join public.municipios municipio_alerta
              on municipio_alerta.id_ibge = p_municipio_id
            where municipio_atribuido.id_ibge = public.cidc_municipio_atual()
              and municipio_atribuido.uf = municipio_alerta.uf
        )
    )
    or (
        public.cidc_perfil_atual() = 'coordenador_municipal'
        and public.cidc_municipio_atual() = p_municipio_id
    )
$$;

revoke all on function public.cidc_perfil_atual() from public;
revoke all on function public.cidc_municipio_atual() from public;
revoke all on function public.cidc_usuario_id_atual() from public;
revoke all on function public.cidc_administrador() from public;
revoke all on function public.cidc_gestor_global() from public;
revoke all on function public.cidc_pode_ver_municipio(char) from public;
revoke all on function public.cidc_pode_operar_municipio(char) from public;
revoke all on function public.cidc_pode_registrar_afetados(char) from public;
revoke all on function public.cidc_pode_gerenciar_abrigo(char) from public;
revoke all on function public.cidc_pode_gerenciar_notificacoes(char) from public;
revoke all on function public.cidc_pode_revisar_alerta(char) from public;
grant execute on function public.cidc_perfil_atual() to authenticated;
grant execute on function public.cidc_municipio_atual() to authenticated;
grant execute on function public.cidc_usuario_id_atual() to authenticated;
grant execute on function public.cidc_administrador() to authenticated;
grant execute on function public.cidc_gestor_global() to authenticated;
grant execute on function public.cidc_pode_ver_municipio(char) to authenticated;
grant execute on function public.cidc_pode_operar_municipio(char) to authenticated;
grant execute on function public.cidc_pode_registrar_afetados(char) to authenticated;
grant execute on function public.cidc_pode_gerenciar_abrigo(char) to authenticated;
grant execute on function public.cidc_pode_gerenciar_notificacoes(char) to authenticated;
grant execute on function public.cidc_pode_revisar_alerta(char) to authenticated;

create table if not exists public.assinaturas_alerta (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    canal text not null check (canal in ('telegram', 'email')),
    destino text not null,
    ativo boolean not null default false,
    confirmado_em timestamptz,
    criado_em timestamptz not null default now(),
    criado_por uuid references public.usuarios(id),
    constraint assinaturas_destino_nao_vazio check (length(trim(destino)) > 0),
    constraint assinaturas_ativas_confirmadas check (not ativo or confirmado_em is not null),
    constraint assinaturas_destino_unico unique (municipio_id, canal, destino)
);

create table if not exists public.entregas_alerta (
    id uuid primary key default gen_random_uuid(),
    alerta_id uuid not null references public.alertas(id),
    assinatura_id uuid references public.assinaturas_alerta(id),
    canal text not null check (canal in ('telegram', 'email')),
    destino_mascarado text not null,
    status text not null check (status in ('enviado', 'falha')),
    erro text,
    tentado_em timestamptz not null default now()
);

create index if not exists assinaturas_alerta_municipio_ativo_idx
    on public.assinaturas_alerta (municipio_id, canal) where ativo;
create index if not exists entregas_alerta_alerta_idx
    on public.entregas_alerta (alerta_id, tentado_em desc);

alter table public.assinaturas_alerta enable row level security;
alter table public.entregas_alerta enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.assinaturas_alerta to authenticated;
grant select, insert on public.entregas_alerta to authenticated;

grant select on public.municipios, public.situacao_municipal, public.alertas to anon;
grant select, insert, update, delete on
    public.fontes,
    public.municipios,
    public.comunidades,
    public.estacoes,
    public.leituras,
    public.focos_calor,
    public.infraestrutura,
    public.situacao_municipal,
    public.regras,
    public.configuracao_pesos,
    public.indices,
    public.usuarios,
    public.alertas,
    public.recursos,
    public.abrigos,
    public.pessoas_afetadas,
    public.acoes,
    public.planos_contingencia,
    public.auditoria
to authenticated;

drop policy if exists municipios_leitura_publica on public.municipios;
create policy municipios_leitura_publica on public.municipios
    for select to anon, authenticated using (true);

drop policy if exists usuarios_select_proprio_perfil on public.usuarios;
create policy usuarios_select_proprio_perfil on public.usuarios
    for select to authenticated
    using (auth_id = (select auth.uid()) or public.cidc_administrador());

drop policy if exists usuarios_admin_gerencia on public.usuarios;
create policy usuarios_admin_gerencia on public.usuarios
    for all to authenticated
    using (public.cidc_administrador())
    with check (public.cidc_administrador());

drop policy if exists fontes_select_perfis_autenticados on public.fontes;
create policy fontes_select_perfis_autenticados on public.fontes
    for select to authenticated
    using (public.cidc_perfil_atual() is not null);

drop policy if exists fontes_admin_gerencia on public.fontes;
create policy fontes_admin_gerencia on public.fontes
    for all to authenticated
    using (public.cidc_administrador())
    with check (public.cidc_administrador());

drop policy if exists municipios_select_perfis on public.municipios;
create policy municipios_select_perfis on public.municipios
    for select to authenticated using (public.cidc_perfil_atual() is not null);

drop policy if exists comunidades_select_escopo on public.comunidades;
create policy comunidades_select_escopo on public.comunidades
    for select to authenticated
    using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists comunidades_insert_escopo on public.comunidades;
create policy comunidades_insert_escopo on public.comunidades
    for insert to authenticated
    with check (public.cidc_pode_operar_municipio(municipio_id));
drop policy if exists comunidades_update_escopo on public.comunidades;
create policy comunidades_update_escopo on public.comunidades
    for update to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));
drop policy if exists comunidades_delete_escopo on public.comunidades;
create policy comunidades_delete_escopo on public.comunidades
    for delete to authenticated using (public.cidc_administrador());

drop policy if exists estacoes_select_perfis on public.estacoes;
create policy estacoes_select_perfis on public.estacoes
    for select to authenticated
    using (
        (
            municipio_id is not null
            and (
                public.cidc_pode_ver_municipio(municipio_id)
                or public.cidc_perfil_atual() = 'operador_monitoramento'
            )
        )
        or (
            municipio_id is null
            and public.cidc_gestor_global()
        )
    );
drop policy if exists estacoes_admin_gerencia on public.estacoes;
create policy estacoes_admin_gerencia on public.estacoes
    for all to authenticated using (public.cidc_administrador())
    with check (public.cidc_administrador());

drop policy if exists leituras_select_perfis on public.leituras;
create policy leituras_select_perfis on public.leituras
    for select to authenticated
    using (
        exists (
            select 1 from public.estacoes e
            where e.id = estacao_id
              and (
                  (
                      e.municipio_id is not null
                      and (
                          public.cidc_pode_ver_municipio(e.municipio_id)
                          or public.cidc_perfil_atual() = 'operador_monitoramento'
                      )
                  )
                  or (
                      e.municipio_id is null
                      and public.cidc_gestor_global()
                  )
              )
        )
    );

drop policy if exists focos_select_perfis on public.focos_calor;
create policy focos_select_perfis on public.focos_calor
    for select to authenticated
    using (
        (
            municipio_id is not null
            and (
                public.cidc_pode_ver_municipio(municipio_id)
                or public.cidc_perfil_atual() = 'operador_monitoramento'
            )
        )
        or (
            municipio_id is null
            and public.cidc_gestor_global()
        )
    );
drop policy if exists focos_insert_escopo on public.focos_calor;
create policy focos_insert_escopo on public.focos_calor
    for insert to authenticated
    with check (municipio_id is not null and public.cidc_pode_operar_municipio(municipio_id));

drop policy if exists infraestrutura_select_escopo on public.infraestrutura;
create policy infraestrutura_select_escopo on public.infraestrutura
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists infraestrutura_operacao_escopo on public.infraestrutura;
create policy infraestrutura_operacao_escopo on public.infraestrutura
    for all to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));

drop policy if exists situacao_select_publica on public.situacao_municipal;
create policy situacao_select_publica on public.situacao_municipal
    for select to anon, authenticated using (true);
drop policy if exists situacao_operacao_escopo on public.situacao_municipal;
create policy situacao_operacao_escopo on public.situacao_municipal
    for all to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));

drop policy if exists regras_select_autenticado on public.regras;
create policy regras_select_autenticado on public.regras
    for select to authenticated using (public.cidc_perfil_atual() is not null);
drop policy if exists regras_admin_gerencia on public.regras;
create policy regras_admin_gerencia on public.regras
    for all to authenticated using (public.cidc_administrador())
    with check (public.cidc_administrador());

drop policy if exists pesos_select_autenticado on public.configuracao_pesos;
create policy pesos_select_autenticado on public.configuracao_pesos
    for select to authenticated using (public.cidc_perfil_atual() is not null);
drop policy if exists pesos_admin_gerencia on public.configuracao_pesos;
create policy pesos_admin_gerencia on public.configuracao_pesos
    for all to authenticated using (public.cidc_administrador())
    with check (public.cidc_administrador());

drop policy if exists indices_select_escopo on public.indices;
create policy indices_select_escopo on public.indices
    for select to authenticated
    using (
        public.cidc_pode_ver_municipio(municipio_id)
        or public.cidc_perfil_atual() = 'operador_monitoramento'
    );
drop policy if exists indices_insert_operador on public.indices;

drop policy if exists alertas_select_escopo on public.alertas;
create policy alertas_select_escopo on public.alertas
    for select to authenticated
    using (
        public.cidc_pode_ver_municipio(municipio_id)
        or public.cidc_pode_revisar_alerta(municipio_id)
    );
drop policy if exists alertas_publicos_aprovados on public.alertas;
create policy alertas_publicos_aprovados on public.alertas
    for select to anon using (status = 'enviado');
drop policy if exists alertas_insert_motor on public.alertas;
drop policy if exists alertas_revisao_humana on public.alertas;
create policy alertas_revisao_humana on public.alertas
    for update to authenticated
    using (public.cidc_pode_revisar_alerta(municipio_id))
    with check (public.cidc_pode_revisar_alerta(municipio_id));

create or replace function public.cidc_validar_transicao_alerta()
returns trigger
language plpgsql
set search_path = pg_catalog, public, pg_temp
as $$
begin
    if auth.uid() is null then
        return new;
    end if;

    if old.status = 'rascunho'
       and new.status in ('aprovado', 'rejeitado')
       and new.id = old.id
       and new.municipio_id = old.municipio_id
       and new.indice_id is not distinct from old.indice_id
       and new.regra_id is not distinct from old.regra_id
       and new.classe = old.classe
       and new.canal is not distinct from old.canal
       and new.criado_em = old.criado_em
       and new.emitido_em is not distinct from old.emitido_em
       and (
           (
               new.status = 'aprovado'
               and length(trim(new.texto)) > 0
               and new.aprovado_por = public.cidc_usuario_id_atual()
           )
           or (
               new.status = 'rejeitado'
               and new.texto = old.texto
               and new.aprovado_por is not distinct from old.aprovado_por
           )
       ) then
        return new;
    end if;

    if old.status = 'aprovado'
       and new.status = 'aprovado'
       and old.emitido_em is null
       and new.emitido_em is not null
       and (
           public.cidc_administrador()
           or (
               public.cidc_perfil_atual() = 'coordenador_municipal'
               and public.cidc_municipio_atual() = old.municipio_id
           )
       )
       and new.id = old.id
       and new.municipio_id = old.municipio_id
       and new.indice_id is not distinct from old.indice_id
       and new.regra_id is not distinct from old.regra_id
       and new.classe = old.classe
       and new.texto = old.texto
       and new.canal is not distinct from old.canal
       and new.criado_em = old.criado_em
       and new.aprovado_por is not distinct from old.aprovado_por then
        return new;
    end if;

    if old.status = 'aprovado'
       and new.status in ('enviado', 'encerrado')
       and new.id = old.id
       and new.municipio_id = old.municipio_id
       and new.indice_id is not distinct from old.indice_id
       and new.regra_id is not distinct from old.regra_id
       and new.classe = old.classe
       and new.texto = old.texto
       and new.canal is not distinct from old.canal
       and new.criado_em = old.criado_em
       and new.aprovado_por is not distinct from old.aprovado_por
       and (
           new.status = 'encerrado'
           or public.cidc_administrador()
           or (
               public.cidc_perfil_atual() = 'coordenador_municipal'
               and public.cidc_municipio_atual() = old.municipio_id
           )
       )
       and (
           (new.status = 'enviado' and new.emitido_em is not null)
           or (
               new.status = 'encerrado'
               and new.emitido_em is not distinct from old.emitido_em
           )
       ) then
        return new;
    end if;

    raise exception 'Transição de alerta não permitida; use o fluxo de revisão humana';
end
$$;

revoke all on function public.cidc_validar_transicao_alerta() from public;
drop trigger if exists cidc_validar_transicao_alerta on public.alertas;
create trigger cidc_validar_transicao_alerta
    before update on public.alertas
    for each row execute function public.cidc_validar_transicao_alerta();

drop policy if exists recursos_select_escopo on public.recursos;
create policy recursos_select_escopo on public.recursos
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists recursos_operacao_escopo on public.recursos;
create policy recursos_operacao_escopo on public.recursos
    for all to authenticated
    using (
        public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = municipio_id
            and public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'saude_assistencia',
                'logistica_abastecimento'
            )
        )
    )
    with check (
        public.cidc_administrador()
        or (
            public.cidc_municipio_atual() = municipio_id
            and public.cidc_perfil_atual() in (
                'coordenador_municipal',
                'saude_assistencia',
                'logistica_abastecimento'
            )
        )
    );

drop policy if exists abrigos_select_escopo on public.abrigos;
create policy abrigos_select_escopo on public.abrigos
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists abrigos_operacao_escopo on public.abrigos;
create policy abrigos_operacao_escopo on public.abrigos
    for all to authenticated
    using (public.cidc_pode_gerenciar_abrigo(municipio_id))
    with check (public.cidc_pode_gerenciar_abrigo(municipio_id));

drop policy if exists afetados_select_escopo on public.pessoas_afetadas;
create policy afetados_select_escopo on public.pessoas_afetadas
    for select to authenticated
    using (
        exists (
            select 1 from public.comunidades c
            where c.id = comunidade_id
              and public.cidc_pode_ver_municipio(c.municipio_id)
        )
    );
drop policy if exists afetados_insert_escopo on public.pessoas_afetadas;
create policy afetados_insert_escopo on public.pessoas_afetadas
    for insert to authenticated
    with check (
        exists (
            select 1 from public.comunidades c
            where c.id = comunidade_id
              and public.cidc_pode_registrar_afetados(c.municipio_id)
        )
    );
drop policy if exists afetados_update_escopo on public.pessoas_afetadas;
create policy afetados_update_escopo on public.pessoas_afetadas
    for update to authenticated
    using (
        exists (
            select 1 from public.comunidades c
            where c.id = comunidade_id
              and public.cidc_pode_registrar_afetados(c.municipio_id)
        )
    )
    with check (
        exists (
            select 1 from public.comunidades c
            where c.id = comunidade_id
              and public.cidc_pode_registrar_afetados(c.municipio_id)
        )
    );

drop policy if exists acoes_select_escopo on public.acoes;
create policy acoes_select_escopo on public.acoes
    for select to authenticated
    using (
        public.cidc_administrador()
        or responsavel_id = public.cidc_usuario_id_atual()
        or exists (
            select 1 from public.alertas al
            where al.id = alerta_id
              and public.cidc_pode_ver_municipio(al.municipio_id)
        )
    );
drop policy if exists acoes_operacao_escopo on public.acoes;
create policy acoes_operacao_escopo on public.acoes
    for all to authenticated
    using (
        public.cidc_administrador()
        or (
            responsavel_id = public.cidc_usuario_id_atual()
            and status <> 'concluida'
        )
        or exists (
            select 1 from public.alertas al
            where al.id = alerta_id
              and public.cidc_pode_operar_municipio(al.municipio_id)
        )
    )
    with check (
        public.cidc_administrador()
        or (
            responsavel_id = public.cidc_usuario_id_atual()
            and exists (
                select 1 from public.alertas al
                where al.id = alerta_id
                  and public.cidc_pode_ver_municipio(al.municipio_id)
            )
        )
        or exists (
            select 1 from public.alertas al
            where al.id = alerta_id
              and public.cidc_pode_operar_municipio(al.municipio_id)
        )
    );

drop policy if exists planos_select_escopo on public.planos_contingencia;
create policy planos_select_escopo on public.planos_contingencia
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
drop policy if exists planos_operacao_escopo on public.planos_contingencia;
create policy planos_operacao_escopo on public.planos_contingencia
    for all to authenticated
    using (public.cidc_pode_operar_municipio(municipio_id))
    with check (public.cidc_pode_operar_municipio(municipio_id));

drop policy if exists auditoria_select_admin on public.auditoria;
create policy auditoria_select_admin on public.auditoria
    for select to authenticated using (public.cidc_administrador());

drop policy if exists assinaturas_select_escopo on public.assinaturas_alerta;
create policy assinaturas_select_escopo on public.assinaturas_alerta
    for select to authenticated using (public.cidc_pode_gerenciar_notificacoes(municipio_id));
drop policy if exists assinaturas_operacao_escopo on public.assinaturas_alerta;
create policy assinaturas_operacao_escopo on public.assinaturas_alerta
    for all to authenticated using (public.cidc_pode_gerenciar_notificacoes(municipio_id))
    with check (public.cidc_pode_gerenciar_notificacoes(municipio_id));

drop policy if exists entregas_select_escopo on public.entregas_alerta;
create policy entregas_select_escopo on public.entregas_alerta
    for select to authenticated
    using (
        exists (
            select 1 from public.alertas al
            where al.id = alerta_id
              and public.cidc_pode_gerenciar_notificacoes(al.municipio_id)
        )
    );
drop policy if exists entregas_insert_escopo on public.entregas_alerta;
create policy entregas_insert_escopo on public.entregas_alerta
    for insert to authenticated
    with check (
        exists (
            select 1 from public.alertas al
            where al.id = alerta_id
              and (
                  public.cidc_administrador()
                  or (
                      public.cidc_perfil_atual() = 'coordenador_municipal'
                      and public.cidc_municipio_atual() = al.municipio_id
                  )
              )
        )
    );

create or replace function public.cidc_registrar_auditoria()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
    registro_id_atual text;
begin
    if tg_op = 'DELETE' then
        registro_id_atual := old.id::text;
    else
        registro_id_atual := new.id::text;
    end if;

    insert into public.auditoria (usuario_id, acao, tabela, registro_id)
    values (
        public.cidc_usuario_id_atual(),
        tg_op,
        tg_table_name,
        registro_id_atual
    );
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end
$$;

do $$
declare
    nome_tabela text;
begin
    foreach nome_tabela in array array[
        'fontes',
        'regras',
        'configuracao_pesos',
        'usuarios',
        'comunidades',
        'situacao_municipal',
        'alertas',
        'recursos',
        'abrigos',
        'pessoas_afetadas',
        'acoes',
        'planos_contingencia',
        'assinaturas_alerta'
    ]
    loop
        execute format(
            'drop trigger if exists cidc_auditoria_%I on public.%I',
            nome_tabela,
            nome_tabela
        );
        execute format(
            'create trigger cidc_auditoria_%I after insert or update or delete on public.%I '
            'for each row execute function public.cidc_registrar_auditoria()',
            nome_tabela,
            nome_tabela
        );
    end loop;
end
$$;

revoke all on function public.cidc_registrar_auditoria() from public;
