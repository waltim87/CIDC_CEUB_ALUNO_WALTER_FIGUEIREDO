-- 10 CONTAS DE TESTE (fictícias), uma para cada tipo de uso do CIDC.
-- E-mails terminam em @cidc-teste.example (domínio reservado, não recebe e-mail) e os
-- nomes começam com "[TESTE]". Apagar depois com: db/testes/limpar_usuarios_teste.sql
--
-- ANTES DE RODAR: troque TROQUE_ESTA_SENHA (linha abaixo) por uma senha forte, com pelo
-- menos 8 caracteres. Todas as 10 contas usam essa senha. Não use senha fácil: as contas
-- de coordenação e saúde veem os dados (fictícios) das famílias abrigadas.
-- Rodar no SQL Editor do Supabase DEPOIS de dados_teste_abrigos_familias_relatos.sql.

do $$
declare
    senha constant text := 'TROQUE_ESTA_SENHA';
    -- e-mail, nome, perfil, município (IBGE; null = sem município)
    contas text[][] := array[
        ['coordenacao.labrea',  'Coordenação Municipal Lábrea',  'coordenador_municipal',   '1302405'],
        ['monitoramento.labrea','Operador de Monitoramento Lábrea','operador_monitoramento', '1302405'],
        ['campo.labrea',        'Agente de Campo Lábrea',        'agente_campo',            '1302405'],
        ['saude.labrea',        'Saúde e Assistência Lábrea',    'saude_assistencia',       '1302405'],
        ['logistica.labrea',    'Logística Lábrea',              'logistica_abastecimento', '1302405'],
        ['coordenacao.boca',    'Coordenação Municipal (2º município)', 'coordenador_municipal', '1300706'],
        ['estadual.am',         'Gestor Estadual AM',            'gestor_estadual',         '1302603'],
        ['pesquisa',            'Pesquisador',                   'pesquisador',             null],
        ['voluntario1',         'Voluntária Lábrea',             'voluntario',              '1302405'],
        ['voluntario2',         'Voluntário (2º município)',     'voluntario',              '1300706']
    ];
    conta text[];
    v_email text;
    v_auth uuid;
    v_usuario uuid;
    v_abrigo uuid;
begin
    if senha = 'TROQUE_ESTA_SENHA' or length(senha) < 8 then
        raise exception 'Troque TROQUE_ESTA_SENHA por uma senha forte (8+ caracteres) antes de rodar';
    end if;

    foreach conta slice 1 in array contas loop
        v_email := conta[1] || '@cidc-teste.example';
        if conta[4] is not null and not exists (select 1 from public.municipios where id_ibge = conta[4]) then
            raise exception 'Município % não existe na tabela municipios', conta[4];
        end if;

        select id into v_auth from auth.users where email = v_email;
        if v_auth is null then
            v_auth := gen_random_uuid();
            insert into auth.users (
                instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                confirmation_token, email_change, email_change_token_new, recovery_token
            ) values (
                '00000000-0000-0000-0000-000000000000', v_auth, 'authenticated', 'authenticated', v_email,
                extensions.crypt(senha, extensions.gen_salt('bf')), now(),
                '{"provider":"email","providers":["email"]}', jsonb_build_object('teste_cidc', true),
                now(), now(), '', '', '', ''
            );
            insert into auth.identities (id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
            values (gen_random_uuid(), v_auth, v_auth::text,
                    jsonb_build_object('sub', v_auth::text, 'email', v_email, 'email_verified', true),
                    'email', now(), now(), now());
        else
            update auth.users set encrypted_password = extensions.crypt(senha, extensions.gen_salt('bf')),
                   updated_at = now() where id = v_auth;
        end if;

        insert into public.usuarios (nome, perfil, municipio_id, auth_id)
        values ('[TESTE] ' || conta[2], conta[3], conta[4], v_auth)
        on conflict (auth_id) do update set nome = excluded.nome, perfil = excluded.perfil,
                                            municipio_id = excluded.municipio_id
        returning id into v_usuario;

        if conta[3] = 'voluntario' then
            insert into public.voluntarios (usuario_id, nome, telefone, municipio_id, habilidades,
                                            possui_embarcacao, disponibilidade, termo_versao, termo_aceito_em)
            values (v_usuario, '[TESTE] ' || conta[2], '(97) 90000-000' || right(conta[1], 1), conta[4],
                    array['primeiros socorros', 'conhecimento local de rios'], conta[1] = 'voluntario1',
                    'emergências', 'v1-2026-10-14', now())
            on conflict (usuario_id) do nothing;
        end if;
    end loop;

    -- O agente de campo de Lábrea coordena o 1º abrigo de teste; a voluntária ajuda no apoio.
    select id into v_abrigo from public.abrigos where nome like '[TESTE]%' and municipio_id = '1302405'
     order by nome limit 1;
    if v_abrigo is not null then
        insert into public.abrigo_responsaveis (abrigo_id, usuario_id, funcao, criado_por)
        select v_abrigo, u.id, f.funcao, null
          from (values ('campo.labrea', 'coordenador'), ('voluntario1', 'apoio')) f(conta, funcao)
          join auth.users a on a.email = f.conta || '@cidc-teste.example'
          join public.usuarios u on u.auth_id = a.id
        on conflict (abrigo_id, usuario_id) do update set funcao = excluded.funcao;
    end if;
end $$;

select a.email as login, u.nome, u.perfil,
       coalesce(m.nome, '—') as municipio,
       (select string_agg(r.funcao || ' de ' || ab.nome, '; ') from public.abrigo_responsaveis r
          join public.abrigos ab on ab.id = r.abrigo_id where r.usuario_id = u.id) as abrigo
  from public.usuarios u
  join auth.users a on a.id = u.auth_id
  left join public.municipios m on m.id_ibge = u.municipio_id
 where a.email like '%@cidc-teste.example'
 order by a.email;
