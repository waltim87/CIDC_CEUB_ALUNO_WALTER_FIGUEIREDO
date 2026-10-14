-- Correção: o upsert (ON CONFLICT) do CNES e do INPE exige restrição única "cheia".
-- Os índices únicos parciais (WHERE ... IS NOT NULL) não são aceitos pelo ON CONFLICT.
-- Restrição UNIQUE comum continua permitindo vários NULL (cadastros manuais sem código).

drop index if exists public.infraestrutura_cnes_unico;
alter table public.infraestrutura drop constraint if exists infraestrutura_cnes_codigo_key;
alter table public.infraestrutura add constraint infraestrutura_cnes_codigo_key unique (cnes_codigo);

drop index if exists public.focos_id_inpe;
alter table public.focos_calor drop constraint if exists focos_calor_id_inpe_key;
alter table public.focos_calor add constraint focos_calor_id_inpe_key unique (id_inpe);
