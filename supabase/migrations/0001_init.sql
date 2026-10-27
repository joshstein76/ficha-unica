-- LLAVE (Ficha Unica) core schema. Target: Supabase Postgres 15. Port of llave/schema.sql.
-- DRAFT: NOT executed against any database (no Postgres on the dev Mac). Run in a Supabase branch first.
-- Rules: bigint identity PKs (profiles = auth.users uuid) · timestamptz · money = bigint centavos + currency
-- · jsonb for json · boolean for 0/1 · CHECK on every enum-like text column · RLS lives in 0002.
-- Dropped on purpose: SQLite `sessions` (Supabase Auth replaces it) and users.password_hash.

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

-- ------------------------------------------------------------------ agencies
create table public.agencies (
  id                 bigint generated always as identity primary key,
  slug               text not null unique,
  name               text not null,
  tagline            text,
  whatsapp           text,                      -- E.164
  email              text,
  email_public       boolean not null default false,  -- NEW: email appears in public_agencies only if true
  city               text,
  logo_path          text,
  design             text not null default 'ciudad',
  accent             text not null default '#1f4e79',
  about              text,
  custom_domain      text unique,
  domain_verified_at timestamptz,
  plan               text not null default 'gratis',
  plan_until         date,                      -- pilot: plan given free until this date
  ghl_location_id    text,                      -- internal, never public
  first_reply        text,
  first_reply_noname text,
  is_demo            boolean not null default false,
  created_at         timestamptz not null default now(),
  constraint agencies_design_chk check (design in ('ciudad','costa','residencia')),
  constraint agencies_plan_chk   check (plan in ('gratis','pro','agencia')),
  constraint agencies_slug_chk   check (slug ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'),
  constraint agencies_accent_chk check (accent ~ '^#[0-9a-fA-F]{6}$')
);

-- ------------------------------------------------------------------ profiles (was users)
create table public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  agency_id  bigint not null references public.agencies(id) on delete cascade,
  name       text not null,
  email      text not null unique,
  whatsapp   text,
  photo_path text,
  role       text not null default 'owner',
  novedades_seen date,
  created_at timestamptz not null default now(),
  constraint profiles_role_chk check (role in ('owner','agent'))
);
create index ix_profiles_agency on public.profiles(agency_id);

-- ------------------------------------------------------------------ listings
create table public.listings (
  id                  bigint generated always as identity primary key,
  agency_id           bigint not null references public.agencies(id) on delete cascade,
  agent_id            uuid references public.profiles(id) on delete set null,
  ref                 text not null,
  slug                text not null,
  status              text not null default 'borrador',
  operation           text not null default 'venta',
  property_type       text not null default 'departamento',
  title               text not null,
  description         text,
  price_cents         bigint,                   -- NULL = precio a consultar
  currency            text not null default 'MXN',
  price_date          date,
  maintenance_cents   bigint,
  m2_built            numeric(10,2),
  m2_land             numeric(10,2),
  bedrooms            integer,
  bathrooms           numeric(3,1),
  parking             integer,
  floor               text,
  year_built          integer,
  furnished           boolean not null default false,
  pets                boolean not null default false,
  amenities           jsonb not null default '[]'::jsonb,
  street              text,
  ext_number          text,
  colonia             text,
  municipio           text,
  estado              text,
  cp                  text,
  lat                 double precision,
  lng                 double precision,
  show_exact_location boolean not null default false,
  source_url          text,
  share_in_bolsa      boolean not null default false,
  share_split_pct     integer not null default 50,
  commission_pct      numeric(5,2),             -- PRIVATE
  rentapoliza_offer   boolean not null default false,
  internal_note       text,                     -- PRIVATE
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint listings_agency_slug_uq unique (agency_id, slug),
  constraint listings_agency_ref_uq  unique (agency_id, ref),
  constraint listings_status_chk   check (status in ('borrador','activa','apartada','vendida','rentada','pausada')),
  constraint listings_operation_chk check (operation in ('venta','renta')),
  constraint listings_type_chk     check (property_type in ('departamento','casa','terreno','oficina','local','bodega')),
  constraint listings_currency_chk check (currency in ('MXN','USD')),
  constraint listings_price_chk    check (price_cents is null or price_cents >= 0),
  constraint listings_maint_chk    check (maintenance_cents is null or maintenance_cents >= 0),
  constraint listings_split_chk    check (share_split_pct between 0 and 100),
  constraint listings_commission_chk check (commission_pct is null or commission_pct between 0 and 100),
  constraint listings_amenities_chk check (jsonb_typeof(amenities) = 'array')
);
create index ix_listings_agency on public.listings(agency_id, status);
create index ix_listings_bolsa  on public.listings(share_in_bolsa, status);

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger trg_listings_updated_at before update on public.listings
  for each row execute function public.set_updated_at();

-- ------------------------------------------------------------------ photos
create table public.photos (
  id         bigint generated always as identity primary key,
  listing_id bigint not null references public.listings(id) on delete cascade,
  position   integer not null default 0,
  sha256     text not null,
  width      integer,
  height     integer,
  sizes      jsonb not null,                    -- {"1600": "<sha2>/<sha>/1600.jpg", ...} = storage keys
  alt        text,
  created_at timestamptz not null default now(),
  constraint photos_listing_sha_uq unique (listing_id, sha256),
  constraint photos_sizes_chk check (jsonb_typeof(sizes) = 'object')
);
create index ix_photos_listing on public.photos(listing_id, position, id);

-- ------------------------------------------------------------------ photo_jobs (NEW: async pipeline queue)
create table public.photo_jobs (
  id         bigint generated always as identity primary key,
  listing_id bigint not null references public.listings(id) on delete cascade,
  url        text not null,
  status     text not null default 'pendiente',
  error      text,
  photo_id   bigint references public.photos(id) on delete set null,
  created_at timestamptz not null default now(),
  constraint photo_jobs_status_chk check (status in ('pendiente','procesando','listo','error'))
);
create index ix_photo_jobs_status on public.photo_jobs(status, id);

-- ------------------------------------------------------------------ portal_publications
create table public.portal_publications (
  listing_id   bigint not null references public.listings(id) on delete cascade,
  portal       text not null,
  enabled      boolean not null default false,
  status       text not null default 'pendiente',
  external_id  text,
  last_sync_at timestamptz,
  last_error   text,
  primary key (listing_id, portal),
  constraint portal_status_chk check (status in ('pendiente','en_feed','publicada','error','sin_convenio'))
);

-- ------------------------------------------------------------------ shares (Bolsa)
create table public.shares (
  id                bigint generated always as identity primary key,
  listing_id        bigint not null references public.listings(id) on delete cascade,
  sharing_agency_id bigint not null references public.agencies(id) on delete cascade,
  split_pct         integer not null default 50,
  status            text not null default 'activa',
  created_at        timestamptz not null default now(),
  constraint shares_listing_agency_uq unique (listing_id, sharing_agency_id),
  constraint shares_status_chk check (status in ('activa','retirada')),
  constraint shares_split_chk  check (split_pct between 0 and 100)
);
create index ix_shares_agency on public.shares(sharing_agency_id, status);

-- ------------------------------------------------------------------ leads
create table public.leads (
  id              bigint generated always as identity primary key,
  agency_id       bigint not null references public.agencies(id) on delete cascade,  -- receiver
  owner_agency_id bigint references public.agencies(id),                              -- listing owner
  listing_id      bigint references public.listings(id) on delete set null,
  name            text,
  phone           text,
  email           text,
  message         text,
  source          text not null default 'sitio',
  consent         boolean not null default false,
  status          text not null default 'nuevo',
  ghl_status      text not null default 'pendiente',
  ghl_contact_id  text,
  follow_up_on    date,                                                               -- 'Seguimiento' reminder day (CDMX)
  created_at      timestamptz not null default now(),
  constraint leads_source_chk check (source in ('sitio','bolsa','whatsapp') or source ~ '^portal:[a-z0-9_.-]+$'),
  constraint leads_status_chk check (status in ('nuevo','contactado','cita','cerrado','descartado')),
  constraint leads_ghl_chk    check (ghl_status in ('pendiente','dry_run','enviado','error')),
  constraint leads_len_chk    check (char_length(coalesce(message,'')) <= 4000 and char_length(coalesce(name,'')) <= 200)
);
create index ix_leads_agency on public.leads(agency_id, created_at);
create index ix_leads_phone_recent on public.leads(phone, created_at) where phone is not null;  -- rate limit

-- ------------------------------------------------------------------ outbox (service role only)
create table public.outbox (
  id         bigint generated always as identity primary key,
  kind       text not null,
  ref        text,
  payload    jsonb not null,
  status     text not null default 'dry_run',
  response   text,
  created_at timestamptz not null default now(),
  constraint outbox_status_chk check (status in ('dry_run','pending','sent','error'))
);
create index ix_outbox_status on public.outbox(status, id);

-- ------------------------------------------------------------------ audit (service role only)
create table public.audit (
  id     bigint generated always as identity primary key,
  at     timestamptz not null default now(),
  actor  text,
  action text not null,
  detail text
);

-- ------------------------------------------------------------------ ml_accounts (NEW: Mercado Libre OAuth)
-- Tokens are NEVER stored here. Each *_secret_id points at vault.secrets(id); only service role reads vault.
create table public.ml_accounts (
  id                       bigint generated always as identity primary key,
  agency_id                bigint not null references public.agencies(id) on delete cascade,
  profile_id               uuid references public.profiles(id) on delete set null,
  ml_user_id               text not null,
  access_token_secret_id   uuid,                -- vault.secrets.id
  refresh_token_secret_id  uuid,                -- vault.secrets.id
  token_expires_at         timestamptz,
  status                   text not null default 'activa',
  created_at               timestamptz not null default now(),
  constraint ml_accounts_uq unique (agency_id, ml_user_id),
  constraint ml_accounts_status_chk check (status in ('activa','expirada','revocada'))
);
