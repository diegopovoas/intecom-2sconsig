-- ═══════════════════════════════════════════════════════════════════
-- 2S CONSIG — GESTÃO · Setup completo do Supabase
-- Rodar no SQL Editor do projeto "2S Consig - Gestão"
-- ═══════════════════════════════════════════════════════════════════

-- ── Cache do painel (HTML completo protegido) ────────────────────────
create table if not exists painel_cache (
  escopo         text primary key,          -- 'painel'
  html           text not null,
  atualizado_em  timestamptz default now()
);
alter table painel_cache enable row level security;

-- ── Perfis de acesso ─────────────────────────────────────────────────
create table if not exists perfis (
  id     uuid primary key default gen_random_uuid(),
  login  text unique not null,
  nome   text,
  role   text not null default 'user' check (role in ('admin', 'user'))
);
alter table perfis enable row level security;

-- Usuário lê o próprio perfil
drop policy if exists "perfil proprio" on perfis;
create policy "perfil proprio" on perfis
  for select to authenticated
  using (login = auth.jwt()->>'email');

-- Qualquer usuário logado (e só logado) lê o painel
drop policy if exists "painel autenticado" on painel_cache;
create policy "painel autenticado" on painel_cache
  for select to authenticated
  using (exists (select 1 from perfis p where p.login = auth.jwt()->>'email'));

-- ── Funções administrativas ──────────────────────────────────────────
create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.perfis
    where login = (auth.jwt()->>'email') and role = 'admin'
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
    order by p.role, p.login;
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
  if p_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'E-mail inválido: %', p_email; end if;
  if length(coalesce(p_senha, '')) < 6 then raise exception 'A senha precisa ter pelo menos 6 caracteres'; end if;
  if p_role not in ('admin', 'user') then raise exception 'Papel inválido: %', p_role; end if;
  if exists (select 1 from auth.users where email = lower(p_email)) then
    raise exception 'Já existe usuário com o e-mail %', p_email;
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
  if p_role not in ('admin', 'user') then raise exception 'Papel inválido: %', p_role; end if;
  update public.perfis set nome = p_nome, role = p_role where login = lower(alvo);
  if not found then raise exception 'Usuário % não encontrado', alvo; end if;
end $$;

create or replace function public.admin_reset_senha(alvo text, nova text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  if length(nova) < 6 then raise exception 'A senha precisa ter pelo menos 6 caracteres'; end if;
  update auth.users set encrypted_password = extensions.crypt(nova, extensions.gen_salt('bf'))
   where email = lower(alvo);
  if not found then raise exception 'Usuário % não encontrado', alvo; end if;
end $$;

create or replace function public.admin_bloquear(alvo text, bloquear boolean)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  update auth.users
     set banned_until = case when bloquear then '2999-01-01'::timestamptz else null end
   where email = lower(alvo);
  if not found then raise exception 'Usuário % não encontrado', alvo; end if;
end $$;

create or replace function public.admin_excluir(alvo text)
returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Apenas administradores'; end if;
  delete from auth.users where email = lower(alvo);
  delete from public.perfis where login = lower(alvo);
end $$;

-- ── Permissões das funções ───────────────────────────────────────────
revoke execute on function public.is_admin()                          from public, anon;
revoke execute on function public.admin_listar_usuarios()             from public, anon;
revoke execute on function public.admin_criar_usuario(text,text,text,text) from public, anon;
revoke execute on function public.admin_editar_usuario(text,text,text) from public, anon;
revoke execute on function public.admin_reset_senha(text,text)        from public, anon;
revoke execute on function public.admin_bloquear(text,boolean)        from public, anon;
revoke execute on function public.admin_excluir(text)                 from public, anon;
grant  execute on function public.is_admin()                          to authenticated;
grant  execute on function public.admin_listar_usuarios()             to authenticated;
grant  execute on function public.admin_criar_usuario(text,text,text,text) to authenticated;
grant  execute on function public.admin_editar_usuario(text,text,text) to authenticated;
grant  execute on function public.admin_reset_senha(text,text)        to authenticated;
grant  execute on function public.admin_bloquear(text,boolean)        to authenticated;
grant  execute on function public.admin_excluir(text)                 to authenticated;
