-- Parity with the live SQLite app (2026-10-27). Columns and tables the app adds at runtime
-- (llave/db.py init, lead_watch, alerts_buyers, ml_oauth, ai/budget, eco, web/server) that 0001 never got.
-- DRAFT: NOT executed against any database. Run in a Supabase branch first, after 0001–0004.
-- New tables: RLS on, no policies and no grants = server (service role) only. Guard: tests/test_pg_parity.py.

-- ------------------------------------------------------------------ columns
alter table public.agencies add column if not exists referred_by bigint references public.agencies(id) on delete set null;  -- agent referral loop
alter table public.agencies add column if not exists stripe_customer_id text;      -- llave/billing.py, internal
alter table public.agencies add column if not exists stripe_subscription_id text;  -- llave/billing.py, internal

alter table public.profiles add column if not exists slug  text;  -- agent public profile /asesor/<slug>
alter table public.profiles add column if not exists bio   text;
alter table public.profiles add column if not exists zones text;
create unique index if not exists ux_profiles_agency_slug on public.profiles(agency_id, slug) where slug is not null;

alter table public.ml_accounts add column if not exists nickname text;  -- tokens stay in vault (0001), never plain columns
alter table public.ml_accounts add column if not exists scope    text;

alter table public.leads add column if not exists first_response_at timestamptz;  -- speed-to-lead (lead_watch)
alter table public.leads add column if not exists reminded_at       timestamptz;

-- ------------------------------------------------------------------ stats + billing
create table if not exists public.listing_views (
  listing_id bigint not null references public.listings(id) on delete cascade,
  day        date   not null,
  views      integer not null default 0,
  primary key (listing_id, day)
);

create table if not exists public.stripe_events (  -- one row per processed Stripe event: replays are no-ops
  event_id    text primary key,
  type        text not null,
  outcome     text,
  received_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ buyer alerts (alerts_buyers.py)
create table if not exists public.saved_searches (
  id                 bigint generated always as identity primary key,
  agency_id          bigint not null references public.agencies(id) on delete cascade,
  name               text,
  phone              text not null,
  operation          text,
  property_type      text,
  colonia            text,
  max_price_cents    bigint,
  currency           text default 'MXN',
  min_beds           integer,
  active             boolean not null default true,
  last_match_listing bigint default 0,
  created_at         timestamptz not null default now()
);
create index if not exists ix_saved_searches_agency on public.saved_searches(agency_id);

create table if not exists public.saved_search_matches (
  search_id  bigint references public.saved_searches(id) on delete cascade,
  listing_id bigint references public.listings(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (search_id, listing_id)
);

-- ------------------------------------------------------------------ Mercado Libre OAuth (ml_oauth.py)
create table if not exists public.ml_oauth_states (
  state         text primary key,
  agency_id     bigint references public.agencies(id) on delete cascade,
  code_verifier text,          -- PKCE secret: server only
  created_at    timestamptz
);

-- ------------------------------------------------------------------ AI budget (ai/budget.py)
create table if not exists public.ai_usage (
  month         text primary key,  -- YYYY-MM
  calls         integer not null default 0,
  input_tokens  bigint  not null default 0,
  output_tokens bigint  not null default 0,
  cost_usd      numeric(12,4) not null default 0,
  alerted_80    boolean not null default false
);

-- ------------------------------------------------------------------ ecosystem credits (eco.py)
create table if not exists public.eco_events (
  id           bigint generated always as identity primary key,
  agency_id    bigint references public.agencies(id) on delete cascade,
  brand        text not null,
  kind         text not null,
  ref          text not null,
  status       text not null default 'pendiente',
  credits      integer not null default 0,
  meta         jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  confirmed_at timestamptz,
  constraint eco_events_status_chk check (status in ('pendiente','confirmado','rechazado')),
  unique (brand, ref)
);

create table if not exists public.eco_ledger (  -- append-only: never UPDATE or DELETE
  id         bigint generated always as identity primary key,
  agency_id  bigint not null references public.agencies(id) on delete cascade,
  delta      integer not null,
  reason     text not null,
  event_id   bigint references public.eco_events(id),
  created_at timestamptz not null default now()
);
create index if not exists ix_eco_ledger_agency on public.eco_ledger(agency_id);

create table if not exists public.eco_boosts (  -- listing_id null for agency-level boosts
  id               bigint generated always as identity primary key,
  agency_id        bigint not null references public.agencies(id) on delete cascade,
  listing_id       bigint references public.listings(id) on delete cascade,
  kind             text not null,
  starts_at        timestamptz not null,
  ends_at          timestamptz not null,
  source_ledger_id bigint references public.eco_ledger(id),
  constraint eco_boosts_kind_chk check (kind in ('destacada','extra_listings','prioridad_leads'))
);

-- ------------------------------------------------------------------ web server (sign-up guards, portal requests, team)
create table if not exists public.rate_events (
  kind       text not null,
  ip         text not null,
  created_at timestamptz not null default now()
);
create index if not exists ix_rate_events_kind_ip on public.rate_events(kind, ip, created_at);

create table if not exists public.portal_requests (
  id         bigint generated always as identity primary key,
  name       text,
  phone      text,
  message    text,
  agency_id  bigint references public.agencies(id) on delete set null,
  lead_id    bigint references public.leads(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.team_invites (
  token      text primary key,
  agency_id  bigint not null references public.agencies(id) on delete cascade,
  created_by uuid references public.profiles(id) on delete set null,
  expires_at timestamptz not null,
  used_at    timestamptz
);

-- ------------------------------------------------------------------ RLS: server only
alter table public.listing_views        enable row level security;
alter table public.stripe_events        enable row level security;
alter table public.saved_searches       enable row level security;
alter table public.saved_search_matches enable row level security;
alter table public.ml_oauth_states      enable row level security;
alter table public.ai_usage             enable row level security;
alter table public.eco_events           enable row level security;
alter table public.eco_ledger           enable row level security;
alter table public.eco_boosts           enable row level security;
alter table public.rate_events          enable row level security;
alter table public.portal_requests      enable row level security;
alter table public.team_invites         enable row level security;
