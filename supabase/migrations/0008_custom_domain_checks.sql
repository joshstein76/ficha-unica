-- Own domain (Pro), DNS check + certificate state (llave/domains.py, tools/domain_check_run.py). Mirrors the SQLite columns added in llave/db.py init.
-- DRAFT: NOT executed against any database. Run in a Supabase branch first, after 0001-0006. Guard: tests/test_pg_parity.py.
-- If another branch also took number 0007, renumber one of them at merge (no statement here depends on the number).
alter table public.agencies add column if not exists domain_claimed_at  timestamptz;  -- when saved; an unverified claim older than 14 days can be taken by another agency
alter table public.agencies add column if not exists domain_checked_at  timestamptz;  -- last DNS check (button or cron)
alter table public.agencies add column if not exists domain_check       jsonb;         -- what www / the bare name resolved to at the last check
alter table public.agencies add column if not exists domain_fail_count  integer not null default 0;  -- consecutive failed cron checks while verified (3 = unverified)
alter table public.agencies add column if not exists domain_lost_at     timestamptz;   -- a verified domain stopped resolving and went back to the free address
alter table public.agencies add column if not exists domain_tls         text;          -- null unknown/ready · 'ok' certificate confirmed · 'espera' verified, certificate not confirmed yet
alter table public.agencies drop constraint if exists agencies_domain_tls_chk;
alter table public.agencies add constraint agencies_domain_tls_chk check (domain_tls is null or domain_tls in ('ok','espera'));

-- Only the server (service role) decides that a domain is verified. 0002 lets an owner UPDATE their whole agencies row, which would let a
-- client mark its own domain verified (and make Caddy request a certificate for it); freeze these columns for client roles, and drop the
-- verification whenever a client changes the domain name.
create or replace function public.protect_agency_domain_fields() returns trigger
language plpgsql as $$
begin
  if auth.role() = 'service_role' or auth.uid() is null then return new; end if;
  if new.custom_domain is distinct from old.custom_domain then
    new.domain_verified_at := null;
    new.domain_claimed_at  := now();
    new.domain_checked_at  := null;
    new.domain_check       := null;
    new.domain_fail_count  := 0;
    new.domain_lost_at     := null;
    new.domain_tls         := null;
  else
    new.domain_verified_at := old.domain_verified_at;
    new.domain_claimed_at  := old.domain_claimed_at;
    new.domain_checked_at  := old.domain_checked_at;
    new.domain_check       := old.domain_check;
    new.domain_fail_count  := old.domain_fail_count;
    new.domain_lost_at     := old.domain_lost_at;
    new.domain_tls         := old.domain_tls;
  end if;
  return new;
end $$;
drop trigger if exists trg_agencies_protect_domain on public.agencies;
create trigger trg_agencies_protect_domain before update on public.agencies
  for each row execute function public.protect_agency_domain_fields();
