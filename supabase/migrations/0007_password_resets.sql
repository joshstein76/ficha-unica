-- Password reset for the Python app (llave/password_reset.py, 2026-11-03): one row per emailed link.
-- Only the SHA-256 of the token is stored, never the token. Single use (used_at), 60-minute expiry (expires_at).
-- Mirrors the CREATE TABLE in llave/db.py init. When the app moves onto Supabase Auth, its own recovery flow replaces this table.
-- DRAFT: NOT executed against any database. Run in a Supabase branch first, after 0001–0006. RLS on, no policies, no grants = server (service role) only.
-- Guard: tests/test_pg_parity.py + tests/test_password_reset.py.

create table if not exists public.password_resets (
  token_hash text primary key,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  expires_at timestamptz not null,
  used_at    timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists ix_password_resets_user on public.password_resets(user_id) where used_at is null;

alter table public.password_resets enable row level security;
