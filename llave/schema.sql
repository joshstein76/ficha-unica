-- LLAVE schema v1 (2026-10-17). SQLite for the local MVP; written to port 1:1 to Supabase Postgres
-- (INTEGER PK -> bigint identity, TEXT json -> jsonb, 0/1 -> boolean). Money = integer centavos + currency.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS agencies (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,              -- free address: <slug>.llave.localhost (prod: <slug>.<brand>.mx)
  name TEXT NOT NULL,
  tagline TEXT,
  whatsapp TEXT,                          -- E.164, e.g. +525578358858
  email TEXT,
  city TEXT,
  logo_path TEXT,
  design TEXT NOT NULL DEFAULT 'ciudad',  -- ciudad | costa | residencia
  accent TEXT NOT NULL DEFAULT '#1f4e79',
  about TEXT,
  custom_domain TEXT UNIQUE,              -- Pro: own domain (Wix model)
  domain_verified_at TEXT,
  plan TEXT NOT NULL DEFAULT 'gratis',    -- gratis | pro | ia  (10-19; agencia/pro_crm retired → ia)
  plan_until TEXT,                        -- pilot: plan given free until this date (YYYY-MM-DD), NULL = paid or Gratis
  ghl_location_id TEXT,                   -- set only when a GHL sub-account exists for the agency
  first_reply TEXT,                       -- NULL = default approved by Josh 10-17 (llave/replies.py)
  first_reply_noname TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  whatsapp TEXT,
  photo_path TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'owner',     -- owner | agent
  novedades_seen TEXT,                    -- last Novedades date opened (YYYY-MM-DD)
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY,
  agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
  agent_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  ref TEXT NOT NULL,                      -- folio shown to clients, e.g. VIVE-0001
  slug TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'borrador',-- borrador | activa | apartada | vendida | rentada | pausada
  operation TEXT NOT NULL DEFAULT 'venta',-- venta | renta
  property_type TEXT NOT NULL DEFAULT 'departamento', -- departamento | casa | terreno | oficina | local | bodega
  title TEXT NOT NULL,
  description TEXT,
  price_cents INTEGER,                    -- NULL = "precio a consultar"
  currency TEXT NOT NULL DEFAULT 'MXN',   -- MXN | USD
  price_date TEXT,                        -- date the price was confirmed (shown next to it)
  maintenance_cents INTEGER,
  m2_built REAL, m2_land REAL,
  bedrooms INTEGER, bathrooms REAL, parking INTEGER,
  floor TEXT, year_built INTEGER,
  furnished INTEGER NOT NULL DEFAULT 0, pets INTEGER NOT NULL DEFAULT 0,
  amenities TEXT NOT NULL DEFAULT '[]',   -- json array of strings
  street TEXT, ext_number TEXT, colonia TEXT, municipio TEXT, estado TEXT, cp TEXT,
  lat REAL, lng REAL,
  show_exact_location INTEGER NOT NULL DEFAULT 0,
  source_url TEXT,                        -- the agency's own page for this listing, if any
  share_in_bolsa INTEGER NOT NULL DEFAULT 0,  -- agent-to-agent network
  share_split_pct INTEGER NOT NULL DEFAULT 50,
  commission_pct REAL,
  rentapoliza_offer INTEGER NOT NULL DEFAULT 0, -- rentals: offer RentaPóliza (hook only)
  internal_note TEXT,                     -- never shown publicly, never fed to portals
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (agency_id, slug), UNIQUE (agency_id, ref)
);

CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL,
  width INTEGER, height INTEGER,
  sizes TEXT NOT NULL,                    -- json {"1600": "media/<sha>/1600.jpg", "800": ..., "400": ..., "1600w": ".webp"...}
  alt TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (listing_id, sha256)
);

CREATE TABLE IF NOT EXISTS portal_publications (
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  portal TEXT NOT NULL,                   -- see llave/feeds/registry
  enabled INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | en_feed | publicada | error | sin_convenio
  external_id TEXT,
  last_sync_at TEXT,
  last_error TEXT,
  PRIMARY KEY (listing_id, portal)
);

-- Bolsa: agency `sharing_agency_id` shows listing `listing_id` (owned by another agency) on its own site.
CREATE TABLE IF NOT EXISTS shares (
  id INTEGER PRIMARY KEY,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  sharing_agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
  split_pct INTEGER NOT NULL DEFAULT 50,  -- the sharing agency's share of the commission
  status TEXT NOT NULL DEFAULT 'activa',  -- activa | retirada
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (listing_id, sharing_agency_id)
);

CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY,
  agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,   -- who received it
  owner_agency_id INTEGER REFERENCES agencies(id),                       -- listing owner (differs for Bolsa leads)
  listing_id INTEGER REFERENCES listings(id) ON DELETE SET NULL,
  name TEXT, phone TEXT, email TEXT, message TEXT,
  source TEXT NOT NULL DEFAULT 'sitio',   -- sitio | bolsa | portal:<name> | whatsapp
  consent INTEGER NOT NULL DEFAULT 0,     -- accepted the privacy notice
  status TEXT NOT NULL DEFAULT 'nuevo',   -- nuevo | contactado | cita | cerrado | descartado
  ghl_status TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | dry_run | enviado | error
  ghl_contact_id TEXT,
  follow_up_on TEXT,                      -- 'Seguimiento' reminder day (YYYY-MM-DD, CDMX)
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Operaciones: one row per deal an agent is working (venta or renta), plus its checklist.
CREATE TABLE IF NOT EXISTS deals (
  id INTEGER PRIMARY KEY,
  agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
  listing_id INTEGER REFERENCES listings(id) ON DELETE SET NULL,
  client_name TEXT NOT NULL,
  client_phone TEXT,
  kind TEXT NOT NULL DEFAULT 'venta',      -- venta | renta
  stage TEXT NOT NULL DEFAULT 'interesado',-- interesado | visita | oferta | apartado | firma | cerrada | perdida
  amount_cents INTEGER,                    -- agreed or offered amount, NULL = not set
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS deal_tasks (
  id INTEGER PRIMARY KEY,
  deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0
);

-- Outbox for every outside call (GHL, portals). Dry-run writes here and stops.
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                     -- ghl.contact_upsert | ghl.opportunity | ghl.message | portal.<name>.<op>
  ref TEXT,                               -- e.g. lead:12, listing:3
  payload TEXT NOT NULL,                  -- json
  status TEXT NOT NULL DEFAULT 'dry_run', -- dry_run | pending | sent | error
  response TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL DEFAULT (datetime('now')),
  actor TEXT, action TEXT NOT NULL, detail TEXT
);

CREATE INDEX IF NOT EXISTS ix_listings_agency ON listings(agency_id, status);
CREATE INDEX IF NOT EXISTS ix_listings_bolsa ON listings(share_in_bolsa, status);
CREATE INDEX IF NOT EXISTS ix_leads_agency ON leads(agency_id, created_at);
CREATE INDEX IF NOT EXISTS ix_deals_agency ON deals(agency_id, stage);
CREATE INDEX IF NOT EXISTS ix_deal_tasks_deal ON deal_tasks(deal_id, position);
