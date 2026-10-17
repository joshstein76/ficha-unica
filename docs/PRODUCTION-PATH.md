# LLAVE — from local MVP to production (plan, not started)
Nothing here runs until Josh answers the name, home and GHL questions and says go-live.

## 1. Data → Supabase (same family as Cerquito / RentaPóliza)
- `llave/schema.sql` ports 1:1: INTEGER PK → `bigint generated always as identity`; TEXT json → `jsonb`; 0/1 → `boolean`; `datetime('now')` → `now()`.
- RLS: every table carries `agency_id`. Policy = the user's `agency_id` from `users` matches the row's. Bolsa reads go through a view that exposes only `share_in_bolsa` listings, and never `internal_note` or `commission_pct`.
- Photos → Supabase Storage bucket `listing-photos` (public read) under the same `<sha[:2]>/<sha>/<size>.jpg` keys. Resizing stays in Python (worker) or moves to Storage image transforms.
- Auth → Supabase Auth (email + WhatsApp OTP later). Sessions/CSRF code is replaced, while `auth.hash_password` stays for any import.

## 2. Hosting the agent sites
- One renderer for all sites at `*.<brand>.mx`. Wildcard DNS + wildcard TLS cover the free addresses.
- Own domains (Pro): the agent adds a CNAME `www` → `sites.<brand>.mx` + TXT `llave-verify=<slug>`. We verify, then issue the cert automatically (ACME / Caddy on-demand TLS or Cloudflare for SaaS) and set `domain_verified_at`. Root-domain A records are avoided on purpose (they pin our IP in thousands of DNS zones).
- Caching: the listing pages and feeds are static per `updated_at`, so put a CDN in front and purge on save.

## 3. GoHighLevel
- New sub-account **LLAVE** (Q5-A) with pipeline **LLAVE Leads** (Nuevo → Contactado → Cita → Cerrado), the 3 custom fields, and a token with contacts, opportunities, customFields and conversations scopes.
- Flip `LLAVE_GHL_LIVE=1` only after: the first-reply template is approved by Josh, a 10-lead dry run is reviewed, and a send to Josh's own test contact only goes through.
- Per-agency GHL (agencies that bring their own GHL) is a Pro/Agency feature later: store their location id + token in a vault, never in the DB in plain text.

## 4. Portals
- Lifull Connect (Trovit/Mitula/Nestoria/Nuroa): send them our feed URL and confirm their current spec.
- Mercado Libre: register the app, OAuth per agent, publish/update/pause from `feeds/mercadolibre.py`, and confirm per-listing fees first.
- Propiedades.com, Proppit/Lamudi, Inmuebles24: partner asks, only with Josh's yes.

## 5. Before any real agent signs up
- A lawyer reviews the privacy notice + terms (new 2025 data-protection law; we act as controller and/or processor).
- Billing: Stripe under Ciao Bella (MXN prices with IVA shown; check whether OXXO/SPEI is possible from the US account).
- Abuse limits on signup and lead forms (rate limit + honeypot). Backups and an audit log review.
