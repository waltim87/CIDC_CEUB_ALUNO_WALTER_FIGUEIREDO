-- Avisos por Telegram para responsáveis de tarefas e ocorrências (resposta).
-- Sempre opt-in: só envia para quem se inscreveu no Telegram (assinaturas_alerta
-- ativas) ou tem telegram_chat_id vinculado (voluntários). Nunca usa dados de
-- quem não aderiu.

create table if not exists public.notificacoes_telegram (
    id uuid primary key default gen_random_uuid(),
    municipio_id char(7) not null references public.municipios(id_ibge),
    tipo text not null check (tipo in ('tarefa_plano', 'ocorrencia')),
    entidade_id uuid not null,          -- id da acao (tarefa) ou da ocorrencia
    usuario_id uuid not null references public.usuarios(id) on delete set null,
    chat_id text not null,
    mensagem text not null check (length(trim(mensagem)) > 0),
    enviado_em timestamptz not null default now(),
    status text not null check (status in ('enviado', 'falha')),
    erro text
);
create index if not exists notificacoes_telegram_usuario_idx on public.notificacoes_telegram (usuario_id, enviado_em desc);
create index if not exists notificacoes_telegram_entidade_idx on public.notificacoes_telegram (tipo, entidade_id);

alter table public.notificacoes_telegram enable row level security;

-- Leitura: quem vê o município vê as notificações dele.
drop policy if exists notificacoes_telegram_select on public.notificacoes_telegram;
create policy notificacoes_telegram_select on public.notificacoes_telegram
    for select to authenticated using (public.cidc_pode_ver_municipio(municipio_id));
grant select on public.notificacoes_telegram to authenticated;

-- Inserção: só o sistema (service_role) ou coordenação/admin do município.
create or replace function public.cidc_pode_gerenciar_notificacoes(p_municipio_id char(7))
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
    select coalesce(public.cidc_administrador()
        or (public.cidc_municipio_atual() = p_municipio_id
            and public.cidc_perfil_atual() in ('coordenador_municipal', 'administrador')), false)
$$;

drop policy if exists notificacoes_telegram_insert on public.notificacoes_telegram;
create policy notificacoes_telegram_insert on public.notificacoes_telegram
    for insert to authenticated
    with check (public.cidc_pode_ver_municipio(municipio_id));
grant insert on public.notificacoes_telegram to authenticated;

-- View: últimas notificações por usuário (para mostrar no app).
create or replace view public.notificacoes_telegram_por_usuario
with (security_invoker = true) as
select n.id, n.tipo, n.entidade_id, n.usuario_id, n.chat_id, n.mensagem,
       n.enviado_em, n.status, n.erro,
       u.nome as usuario_nome
  from public.notificacoes_telegram n
  join public.usuarios u on u.id = n.usuario_id;
grant select on public.notificacoes_telegram_por_usuario to authenticated;
