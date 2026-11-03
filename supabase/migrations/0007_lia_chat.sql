-- Lía, the AI chat on agent sites (llave/lia.py, docs/LIA.md; 2026-11-03). Mirrors schema.sql and db.init for the Postgres port.
-- DRAFT: NOT executed against any database. Run in a Supabase branch first, after 0001–0006. Guard: tests/test_pg_parity.py.
-- The number 0007 may need re-sequencing when other branches add migrations; the statements do not depend on each other's files.

-- The agent's own switch for Lía. OFF by default: she also needs LLAVE_LIA_LIVE=1 on the server, live AI, and the Pro + IA plan.
alter table public.agencies add column if not exists lia_enabled boolean not null default false;
-- (public_agencies, the only anon-readable agency view, lists its columns by name: this flag is not exposed.)

create table if not exists public.lia_threads (  -- one chat; becomes a lead only through the contact form (lead_id)
  id             bigint generated always as identity primary key,
  agency_id      bigint not null references public.agencies(id) on delete cascade,
  listing_id     bigint references public.listings(id) on delete set null,
  status         text not null default 'answering',  -- the furthest the chat got
  summary        text,                               -- one line for the agent
  requested_time text,                               -- the visit time the client asked for, in their words: never a confirmed visit
  replies        integer not null default 0,         -- model replies used (per-thread cap)
  night_shown    boolean not null default false,     -- the after-hours message was already shown once
  lead_id        bigint references public.leads(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint lia_threads_status_chk check (status in ('answering','handoff','visit_requested'))
);
create index if not exists ix_lia_threads_agency on public.lia_threads(agency_id, created_at);

create table if not exists public.lia_messages (
  id          bigint generated always as identity primary key,
  thread_id   bigint not null references public.lia_threads(id) on delete cascade,
  role        text not null,
  kind        text not null default 'text',
  body        text not null,                         -- phones and emails typed in the chat are replaced before storing
  model_call  boolean not null default false,        -- this reply used a model call (per-agency daily cap)
  created_at  timestamptz not null default now(),
  constraint lia_messages_role_chk check (role in ('user','assistant')),
  constraint lia_messages_kind_chk check (kind in ('greeting','text','guard','error','night','cap','contact')),
  constraint lia_messages_len_chk  check (char_length(body) <= 4000)
);
create index if not exists ix_lia_messages_thread on public.lia_messages(thread_id, id);

-- New source for leads created from a Lía chat ('vendedor' is what the valuation page already writes; 0001 never listed it).
alter table public.leads drop constraint if exists leads_source_chk;
alter table public.leads add constraint leads_source_chk
  check (source in ('sitio','bolsa','whatsapp','lia','vendedor') or source ~ '^portal:[a-z0-9_.-]+$');

-- RLS: server only (service role). No policies and no grants: transcripts hold what clients typed.
alter table public.lia_threads  enable row level security;
alter table public.lia_messages enable row level security;
revoke all on public.lia_threads, public.lia_messages from anon, authenticated;
