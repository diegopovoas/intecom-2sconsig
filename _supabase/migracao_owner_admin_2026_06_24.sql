-- 2S CONSIG - migracao de hierarquia de acesso
-- Objetivo:
-- 1. criar papel owner acima de admin;
-- 2. trocar o e-mail/login do Diego;
-- 3. deixar Diego como owner e os demais usuarios atuais como admin.
--
-- Antes de rodar, ajuste o valor de v_novo_email se o e-mail correto nao for este.

do $$
declare
  v_email_antigo text := 'diego@2sconsig.com.br';
  v_novo_email   text := 'diego.povoas@novapromotora.com';
  v_user_id      uuid;
begin
  alter table public.perfis drop constraint if exists perfis_role_check;
  alter table public.perfis add constraint perfis_role_check
    check (role in ('owner', 'admin', 'user'));

  select id into v_user_id
  from auth.users
  where email = lower(v_email_antigo);

  if v_user_id is null then
    select id into v_user_id
    from auth.users
    where email = lower(v_novo_email);
  end if;

  if v_user_id is null then
    raise exception 'Usuario Diego nao encontrado em auth.users: % / %', v_email_antigo, v_novo_email;
  end if;

  if exists (
    select 1 from auth.users
    where email = lower(v_novo_email) and id <> v_user_id
  ) then
    raise exception 'Ja existe outro usuario com o novo e-mail: %', v_novo_email;
  end if;

  if lower(v_email_antigo) <> lower(v_novo_email) then
    update auth.users
       set email = lower(v_novo_email),
           updated_at = now()
     where id = v_user_id;

    update auth.identities
       set identity_data = jsonb_set(identity_data, '{email}', to_jsonb(lower(v_novo_email))),
           updated_at = now()
     where user_id = v_user_id;
  end if;

  update public.perfis
     set login = lower(v_novo_email),
         nome = coalesce(nome, 'Diego Povoas'),
         role = 'owner'
   where login in (lower(v_email_antigo), lower(v_novo_email));

  if not found then
    insert into public.perfis (login, nome, role)
    values (lower(v_novo_email), 'Diego Povoas', 'owner');
  end if;

  update public.perfis
     set role = 'admin'
   where login in ('dinho@2sconsig.com.br', 'dudu@2sconsig.com.br', 'rodrigo@2sconsig.com.br');
end $$;

create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.perfis
    where login = (auth.jwt()->>'email') and role in ('owner', 'admin')
  );
$$;

create or replace function public.is_owner()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.perfis
    where login = (auth.jwt()->>'email') and role = 'owner'
  );
$$;

create or replace function public.admin_listar_usuarios()
returns table(login text, nome text, role text, bloqueado boolean)
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  return query
    select p.login, p.nome, p.role,
           coalesce(u.banned_until > now(), false) as bloqueado
    from public.perfis p
    left join auth.users u on u.email = p.login
    order by case p.role when 'owner' then 0 when 'admin' then 1 else 2 end, p.login;
end $$;

create or replace function public.admin_criar_usuario(
  p_email text, p_senha text, p_nome text, p_role text default 'user')
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  uid uuid := gen_random_uuid();
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if p_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'E-mail invalido: %', p_email; end if;
  if length(coalesce(p_senha, '')) < 6 then raise exception 'A senha precisa ter pelo menos 6 caracteres'; end if;
  if p_role not in ('owner', 'admin', 'user') then raise exception 'Papel invalido: %', p_role; end if;
  if p_role = 'owner' and not public.is_owner() then raise exception 'Apenas owner pode criar outro owner'; end if;
  if exists (select 1 from auth.users where email = lower(p_email)) then
    raise exception 'Ja existe usuario com o e-mail %', p_email;
  end if;

  insert into auth.users (instance_id, id, aud, role, email, encrypted_password,
    email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
    confirmation_token, recovery_token, email_change, email_change_token_new, email_change_token_current)
  values ('00000000-0000-0000-0000-000000000000', uid, 'authenticated', 'authenticated',
    lower(p_email), extensions.crypt(p_senha, extensions.gen_salt('bf')),
    now(), '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb, now(), now(),
    '', '', '', '', '');

  insert into auth.identities (id, user_id, provider_id, identity_data, provider,
    last_sign_in_at, created_at, updated_at)
  values (gen_random_uuid(), uid, uid::text,
    jsonb_build_object('sub', uid::text, 'email', lower(p_email), 'email_verified', true),
    'email', now(), now(), now());

  insert into public.perfis (login, nome, role)
  values (lower(p_email), p_nome, p_role);
end $$;

create or replace function public.admin_editar_usuario(alvo text, p_nome text, p_role text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if p_role not in ('owner', 'admin', 'user') then raise exception 'Papel invalido: %', p_role; end if;
  if (p_role = 'owner' or exists (select 1 from public.perfis where login = lower(alvo) and role = 'owner'))
     and not public.is_owner() then
    raise exception 'Apenas owner pode alterar perfil owner';
  end if;
  update public.perfis set nome = p_nome, role = p_role where login = lower(alvo);
  if not found then raise exception 'Usuario % nao encontrado', alvo; end if;
end $$;

create or replace function public.admin_bloquear(alvo text, bloquear boolean)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if exists (select 1 from public.perfis where login = lower(alvo) and role = 'owner')
     and not public.is_owner() then
    raise exception 'Apenas owner pode bloquear owner';
  end if;
  update auth.users
     set banned_until = case when bloquear then '2999-01-01'::timestamptz else null end
   where email = lower(alvo);
  if not found then raise exception 'Usuario % nao encontrado', alvo; end if;
end $$;

create or replace function public.admin_reset_senha(alvo text, nova text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if length(nova) < 6 then raise exception 'A senha precisa ter pelo menos 6 caracteres'; end if;
  if exists (select 1 from public.perfis where login = lower(alvo) and role = 'owner')
     and not public.is_owner() then
    raise exception 'Apenas owner pode resetar senha de owner';
  end if;
  update auth.users set encrypted_password = extensions.crypt(nova, extensions.gen_salt('bf'))
   where email = lower(alvo);
  if not found then raise exception 'Usuario % nao encontrado', alvo; end if;
end $$;

create or replace function public.admin_excluir(alvo text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if exists (select 1 from public.perfis where login = lower(alvo) and role = 'owner')
     and not public.is_owner() then
    raise exception 'Apenas owner pode excluir owner';
  end if;
  delete from auth.users where email = lower(alvo);
  delete from public.perfis where login = lower(alvo);
end $$;

revoke execute on function public.is_admin() from public, anon;
revoke execute on function public.is_owner() from public, anon;
grant execute on function public.is_admin() to authenticated;
grant execute on function public.is_owner() to authenticated;
