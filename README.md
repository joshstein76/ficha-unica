# LLAVE (code name) — Mexican agent platform, local MVP

Free website for every real estate agent in Mexico + listings typed once that reach Google, AI assistants and the portals + every client on WhatsApp → GoHighLevel. Lane: `josh-command-center/clients/mx-broker-platform/`.

**Status 2026-10-17:** local only. Nothing public, no domain bought, no payments, no outreach, GHL in dry-run (no writes).

## Run it
```bash
python3 seed/seed_vive.py --reset      # demo: VIVE Polanco (8 listings, 2 public) + Agencia Ejemplo (Bolsa test)
python3 -m llave.web.server            # panel: http://app.fichaunica.localhost:8640 · VIVE site: http://vive-polanco.fichaunica.localhost:8640
python3 -m unittest discover -s tests  # 91 tests
```
Demo logins are in `seed/DEMO-CREDENTIALS.local.md` (gitignored). `*.localhost` resolves to 127.0.0.1 in Chrome/Safari.

## What's in it
| Area | Where | Notes |
|---|---|---|
| Data model | `llave/schema.sql`, `llave/db.py` | SQLite now, written to port 1:1 to Supabase Postgres. Money = integer centavos. `db.canonical()` is the one listing contract every module reads |
| Agent accounts | `llave/auth.py`, `web/server.py` | pbkdf2 passwords, HttpOnly session cookie, CSRF on every POST, plan limits (gratis 10 / pro 50 / agencia 200) |
| Listings + photos | `web/panel.py`, `llave/photos.py` | mobile-first editor; photos auto-rotated, EXIF/GPS stripped, 1600/800/400 JPEG + WebP, banners/logos/too-small rejected, watermark optional and off by default |
| Free agent website | `web/site.py`, `web/styles.py` | `<slug>.<base>` (Wix model; own domain on Pro), 3 designs (Residencia / Ciudad / Costa), RealEstateListing JSON-LD, canonical, sitemap, robots, **llms.txt**, WhatsApp button, lead form with privacy consent |
| Portal syndication | `llave/feeds/` | Trovit-style + Mitula-style XML, LLAVE open XML/JSON, Mercado Libre item payload (dry-run to outbox), stubs for Propiedades / Proppit / Lamudi / Inmuebles24 / Vivanuncios / Casas y Terrenos until partner terms exist |
| Leads → GHL | `llave/leads.py`, `llave/ghl.py`, `llave/whatsapp.py` | contact upsert + note + opportunity + agent WhatsApp alert planned per lead, written to `outbox` as `dry_run`; never messages the lead; blocklist honoured; live mode raises until built |
| Bolsa (agent-to-agent) | `web/server.py` `/bolsa` | share a listing with the network, set your split (default 50/50); a sharer's page canonicals to the owner; Bolsa leads alert both agencies |
| RentaPóliza hook | `leads.rentapoliza_offer` | rentals can show the póliza line (no link, no price) |
| VIVE GHL check | `tools/ghl_dryrun_vive.py` | read-only GETs only; report in `docs/` |

## Decisions log
`docs/DECISIONS.md`
