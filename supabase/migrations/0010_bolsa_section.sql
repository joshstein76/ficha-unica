-- "Más propiedades de la Bolsa" on an agent site (llave/db.py pool_listing_ids; docs/DECISIONS.md #74). Mirrors schema.sql and db.init for the Postgres port.
-- DRAFT: NOT executed against any database. Guard: tests/test_pg_parity.py.

-- The agency's own switch. OFF by default; the section also needs LLAVE_PLANS_V2=1 on the server and a plan that includes the Bolsa.
alter table public.agencies add column if not exists bolsa_section boolean not null default false;
-- (public_agencies, the only anon-readable agency view, lists its columns by name: this flag is not exposed.)
-- Not ported yet: the site section itself. It reads the same rows as the Bolsa catalogue (public.bolsa_listings, 0003) and must keep
-- the same rules as pool_listing_ids: owner opted in, public under the owner's plan, no split or owner contact in any public view.
-- Found while writing this: public_listings and public_shared_listings (0003) select share_split_pct / split_pct, i.e. the commission split
-- would be readable by anon. Take them out of those views before the port goes live.
