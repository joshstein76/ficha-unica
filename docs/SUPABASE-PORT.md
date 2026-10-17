# LLAVE: SQLite to Supabase port (reviewed draft, nothing executed)
Files: `supabase/migrations/0001_init.sql` (tables), `0002_rls.sql` (policies), `0003_views_functions.sql` (public views, `submit_lead`). Check column parity with `python3 tools/check_sql_parity.py`.

## 1. Type mapping
| SQLite | Postgres | Notes |
|---|---|---|
| `INTEGER PRIMARY KEY` | `bigint generated always as identity` | ids are re-numbered unless imported with `overriding system value` (see cut-over) |
| `users.id` INTEGER | `profiles.id uuid` = `auth.users.id` | `listings.agent_id` becomes uuid |
| `TEXT` datetime / `datetime('now')` | `timestamptz default now()` | `price_date` is `date`; SQLite values are UTC, import as UTC |
| `TEXT` json (amenities, sizes, payload) | `jsonb` + CHECK array/object | `outbox.payload` jsonb |
| `INTEGER` 0/1 | `boolean` | all flags, `consent`, `is_demo` |
| `price_cents`, `maintenance_cents` | `bigint` | centavos stay; Python `//100` unchanged |
| `REAL` m2 / bathrooms / commission | `numeric(10,2)` / `(3,1)` / `(5,2)` | `lat`, `lng` stay `double precision` |
| enum-like TEXT | `text` + named CHECK | same values; `leads.source` also allows `portal:<name>` |
| `UNIQUE`, indexes | same names and columns | + `ix_profiles_agency`, `ix_shares_agency`, phone index for rate limit |
| `sessions`, `password_hash` | dropped | Supabase Auth |
| (new) | `photo_jobs`, `ml_accounts`, `agencies.email_public` | tokens only as vault secret ids |

## 2. What moves where
- **Moves to SQL:** tenancy (RLS, `current_agency_id()`), public/Bolsa visibility (views), lead intake rules (`submit_lead`: consent, public-for-this-site check, own/bolsa source, 10-min dedupe, 5 per phone per hour, honeypot), `updated_at` trigger, field guards on `profiles` and `leads`.
- **Stays in Python (service role):** photo pipeline and resizing (writes `photos`, `photo_jobs`), portal feeds and `canonical()`, GHL queue and `outbox` writes, blocklist (`is_blocked`), `whatsapp.norm_phone`, site rendering. Worker polls `leads.ghl_status='pendiente'`.
- `canonical()` keeps reading base tables with the service key; the website renderer reads only the `public_*` views with the anon key.

## 3. Cut-over
1. Create a Supabase branch project; apply 0001-0003 in order; run the tests in section 4.
2. Freeze writes on SQLite (local MVP only, no real agents yet).
3. Export each table: `sqlite3 -header -csv llave.db "select ..." > table.csv`. Convert 0/1 to `t/f`, datetimes to ISO UTC; `amenities` and `sizes` are already JSON strings (CSV-quote them).
4. Create auth users first (admin API, no passwords: send invite/reset), build `users.id -> uuid` map, and write `profiles.csv` with the uuid.
5. `\copy` in dependency order: agencies, profiles, listings, photos, portal_publications, shares, leads, outbox, audit. Use `overriding system value` so ids and FKs survive, then `select setval(pg_get_serial_sequence('public.<t>','id'), max(id)) from public.<t>` per table.
6. Upload photos to bucket `listing-photos` under `<agency_id>/<sha[:2]>/<sha>/<size>.jpg`; update `photos.sizes` keys to the new prefix.
7. Compare row counts and `sum(price_cents)` per agency; run `canonical()` on 5 listings against both DBs and diff.
8. Flip Python to the Supabase connection (psycopg); keep `LLAVE_GHL_LIVE` off until Josh says.

## 4. Test plan (pgTAP or plain `do $$ assert ... $$`, run in a branch)
- RLS on for all 11 tables (`pg_class.relrowsecurity`); `outbox`, `audit` have zero policies and anon/authenticated have no grants.
- Two agencies A, B with users. As A: sees only A listings, photos, leads; cannot insert a listing with `agency_id = B`; cannot update B rows (0 rows affected).
- Anon: `select` on `listings`, `leads`, `agencies` raises permission denied; `public_listings` returns only activa/apartada and has no `internal_note`/`commission_pct` column; exact lat/lng null when `show_exact_location` is false.
- `public_agencies`: no `ghl_location_id`; email null unless `email_public`; custom_domain null until verified.
- Bolsa: A's `bolsa_listings` has B's `share_in_bolsa` listings only; A can insert a share for B's shared listing; cannot for its own listing, for a non-shared one, or as agency B; cannot re-point an existing share to a non-shared listing.
- `submit_lead`: no consent fails; bad slug fails; listing of another agency without share fails; with active share inserts `source='bolsa'`, `owner_agency_id` = owner; own listing `source='sitio'`; 6th lead from one phone in an hour fails; honeypot returns ok and inserts nothing; duplicate in 10 minutes returns same id; anon direct `insert into leads` fails.
- Profile guard: agent cannot change own `role` or `agency_id`; lead guard: member can change only `status`.
- Storage: member of A cannot write under prefix of B; anon can read an object URL but cannot list.

## 5. Open questions
- Does `show_exact_location=false` also apply to `source_url`/feeds (currently only the site views blank the address)?
- Does the listing owner see Bolsa leads (policy says yes) and should the sharing agency see the owner's `phone`/`email` for Bolsa leads sent to it? Who updates status?
- `ml_accounts`: use column-level grants to hide `*_secret_id` from owners, or move reads fully to an RPC?
- Signup: who creates agency + profile atomically? Needs a service-role edge function or `handle_new_user` trigger (not in this draft).
- Public views run as owner (not `security_invoker`) by design; confirm Supabase advisor warnings are acceptable, or switch to RPCs.
- `is_demo` agencies are visible in `public_agencies`; hide before real agents sign up?
- Wildcard/custom domain lookup needs a view by `custom_domain`: `public_agencies` already exposes it once verified.
- Rate limit is per phone only; add per-IP via an edge function in front of the RPC (RPC cannot see IP reliably).
- `norm_phone` is only approximated in SQL; port exactly or normalise in the edge function before calling.
