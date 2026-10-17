-- LLAVE RLS. DRAFT, not executed. Principle: deny by default; clients act only inside their agency.
-- Service role (workers, import, GHL, feeds) bypasses RLS. anon gets NOTHING on base tables (see 0003 views).

-- ------------------------------------------------------------------ helpers
create or replace function public.current_agency_id() returns bigint
language sql stable security definer set search_path = public as $$
  select agency_id from public.profiles where id = auth.uid()
$$;

create or replace function public.current_role_name() returns text
language sql stable security definer set search_path = public as $$
  select role from public.profiles where id = auth.uid()
$$;

-- Lookups that must NOT be filtered by the caller's own RLS (e.g. another agency's listing).
create or replace function public.listing_agency_id(p_listing bigint) returns bigint
language sql stable security definer set search_path = public as $$
  select agency_id from public.listings where id = p_listing
$$;

create or replace function public.listing_is_shareable_by_others(p_listing bigint) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.listings l
                  where l.id = p_listing and l.share_in_bolsa
                    and l.agency_id <> public.current_agency_id()
                    and l.status in ('activa','apartada'))
$$;

revoke all on function public.current_agency_id(), public.current_role_name(),
  public.listing_agency_id(bigint), public.listing_is_shareable_by_others(bigint) from public;
grant execute on function public.current_agency_id(), public.current_role_name(),
  public.listing_agency_id(bigint), public.listing_is_shareable_by_others(bigint) to authenticated;

-- ------------------------------------------------------------------ enable RLS everywhere
alter table public.agencies            enable row level security;
alter table public.profiles            enable row level security;
alter table public.listings            enable row level security;
alter table public.photos              enable row level security;
alter table public.photo_jobs          enable row level security;
alter table public.portal_publications enable row level security;
alter table public.shares              enable row level security;
alter table public.leads               enable row level security;
alter table public.outbox              enable row level security;
alter table public.audit               enable row level security;
alter table public.ml_accounts         enable row level security;

-- Belt and braces: no table privileges for anon; authenticated gets only what policies can use.
revoke all on all tables in schema public from anon;
revoke all on all tables in schema public from authenticated;
grant select, update                 on public.agencies            to authenticated;
grant select, update                 on public.profiles            to authenticated;
grant select, insert, update, delete on public.listings            to authenticated;
grant select, insert, update, delete on public.photos              to authenticated;
grant select, insert, update, delete on public.portal_publications to authenticated;
grant select, insert, update, delete on public.shares              to authenticated;
grant select, update                 on public.leads               to authenticated;   -- NO insert: submit_lead() only
grant select, insert                 on public.photo_jobs          to authenticated;
grant select, delete                 on public.ml_accounts         to authenticated;   -- tokens never exposed anyway
-- outbox, audit: no grants at all.

-- ------------------------------------------------------------------ agencies
create policy agencies_select_own on public.agencies for select to authenticated
  using (id = public.current_agency_id());
create policy agencies_update_owner on public.agencies for update to authenticated
  using (id = public.current_agency_id() and public.current_role_name() = 'owner')
  with check (id = public.current_agency_id());
-- insert/delete: service role only (onboarding RPC / support).

-- ------------------------------------------------------------------ profiles
create policy profiles_select_agency on public.profiles for select to authenticated
  using (agency_id = public.current_agency_id());
create policy profiles_update_self_or_owner on public.profiles for update to authenticated
  using (agency_id = public.current_agency_id()
         and (id = auth.uid() or public.current_role_name() = 'owner'))
  with check (agency_id = public.current_agency_id());
-- agency_id / role cannot be changed from the client (prevents self-promotion and cross-agency jumps):
create or replace function public.protect_profile_fields() returns trigger
language plpgsql as $$
begin
  if auth.role() = 'service_role' or auth.uid() is null then return new; end if;
  if new.agency_id is distinct from old.agency_id or new.id is distinct from old.id then
    raise exception 'agency_id and id are immutable';
  end if;
  if new.role is distinct from old.role and public.current_role_name() <> 'owner' then
    raise exception 'only an owner can change roles';
  end if;
  return new;
end $$;
create trigger trg_profiles_protect before update on public.profiles
  for each row execute function public.protect_profile_fields();

-- ------------------------------------------------------------------ listings
create policy listings_agency_all on public.listings for all to authenticated
  using (agency_id = public.current_agency_id())
  with check (agency_id = public.current_agency_id());
-- Other agencies never read this table directly: Bolsa goes through view bolsa_listings (0003).

-- ------------------------------------------------------------------ photos / portal_publications / photo_jobs
create policy photos_agency_all on public.photos for all to authenticated
  using (public.listing_agency_id(listing_id) = public.current_agency_id())
  with check (public.listing_agency_id(listing_id) = public.current_agency_id());

create policy portal_pub_agency_all on public.portal_publications for all to authenticated
  using (public.listing_agency_id(listing_id) = public.current_agency_id())
  with check (public.listing_agency_id(listing_id) = public.current_agency_id());

create policy photo_jobs_agency_select on public.photo_jobs for select to authenticated
  using (public.listing_agency_id(listing_id) = public.current_agency_id());
create policy photo_jobs_agency_insert on public.photo_jobs for insert to authenticated
  with check (public.listing_agency_id(listing_id) = public.current_agency_id());
-- status/error/photo_id updates: worker (service role).

-- ------------------------------------------------------------------ shares (Bolsa)
-- Sharing agency sees its shares; listing owner sees who shares its listings.
create policy shares_select on public.shares for select to authenticated
  using (sharing_agency_id = public.current_agency_id()
         or public.listing_agency_id(listing_id) = public.current_agency_id());
-- Insert: only as itself, only for another agency's listing that is opted into the Bolsa.
create policy shares_insert_own on public.shares for insert to authenticated
  with check (sharing_agency_id = public.current_agency_id()
              and public.listing_is_shareable_by_others(listing_id));
-- Update: only own rows; the check re-validates so a row cannot be re-pointed at a non-shared listing.
create policy shares_update_own on public.shares for update to authenticated
  using (sharing_agency_id = public.current_agency_id())
  with check (sharing_agency_id = public.current_agency_id()
              and (status = 'retirada' or public.listing_is_shareable_by_others(listing_id)));
create policy shares_delete_own on public.shares for delete to authenticated
  using (sharing_agency_id = public.current_agency_id());
-- Guard (review 2026-10-17): the split always comes from the listing owner (share_split_pct), never from the
-- sharing agency, and a share can never be re-pointed at another listing (even when status = 'retirada').
create or replace function public.shares_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'UPDATE' and new.listing_id <> old.listing_id then
    raise exception 'listing_id is immutable on shares';
  end if;
  select 100 - coalesce(l.share_split_pct, 50) into new.split_pct from public.listings l where l.id = new.listing_id;
  return new;
end $$;
create trigger shares_guard before insert or update on public.shares
  for each row execute function public.shares_guard();

-- ------------------------------------------------------------------ leads
-- Receiver and listing owner can read; only receiver (or owner) updates status. No client INSERT.
create policy leads_select on public.leads for select to authenticated
  using (agency_id = public.current_agency_id() or owner_agency_id = public.current_agency_id());
create policy leads_update on public.leads for update to authenticated
  using (agency_id = public.current_agency_id() or owner_agency_id = public.current_agency_id())
  with check (agency_id = public.current_agency_id() or owner_agency_id = public.current_agency_id());
-- Column guard: clients may only change `status`; ghl_* and identity fields are worker-owned.
create or replace function public.protect_lead_fields() returns trigger
language plpgsql as $$
begin
  if auth.role() = 'service_role' or auth.uid() is null then return new; end if;
  if (new.agency_id, new.owner_agency_id, new.listing_id, new.name, new.phone, new.email, new.message,
      new.source, new.consent, new.ghl_status, new.ghl_contact_id, new.created_at)
     is distinct from
     (old.agency_id, old.owner_agency_id, old.listing_id, old.name, old.phone, old.email, old.message,
      old.source, old.consent, old.ghl_status, old.ghl_contact_id, old.created_at) then
    raise exception 'only lead status can be changed from the client';
  end if;
  return new;
end $$;
create trigger trg_leads_protect before update on public.leads
  for each row execute function public.protect_lead_fields();

-- ------------------------------------------------------------------ ml_accounts
create policy ml_accounts_select on public.ml_accounts for select to authenticated
  using (agency_id = public.current_agency_id() and public.current_role_name() = 'owner');
create policy ml_accounts_delete on public.ml_accounts for delete to authenticated
  using (agency_id = public.current_agency_id() and public.current_role_name() = 'owner');
-- Even with select, token columns hold only vault ids; vault.* is not exposed to clients.
-- (Better: grant column-level select excluding *_secret_id; see SUPABASE-PORT.md open questions.)

-- ------------------------------------------------------------------ outbox / audit
-- RLS enabled, zero policies, zero grants: reachable only with the service role.
