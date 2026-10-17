# Ficha Única: go-live checklist (nothing here has been done; it's the path once Josh says go)
Owner: Ciao Bella Marketing · Code: this repo · Deploy kit: `deploy/` (dry-run by default)

## Hosting choice (Josh is upgrading Hostinger next week)
**Recommendation: a Hostinger VPS (KVM), not Cloud hosting.**
- Ficha Única is its own Python app that needs a reverse proxy on 80/443, one wildcard certificate for `*.fichaunica.mx` (every free agent site), and on-demand certificates for agents' own domains (Pro). All of that needs root (Caddy + systemd).
- Hostinger Cloud/shared plans don't give you that. The kit still supports it (`TARGET_KIND=cloud`: setsid daemon + cron watchdog, the same pattern the VIVE watcher uses), but custom domains and wildcard TLS would need workarounds there.
- Size to start: 2 vCPU / 8 GB is plenty for the pilot. The app itself is small; photos are the main disk cost (~1–2 MB per listing across all sizes).

## Before the first deploy
| # | Step | Who | Status |
|---|---|---|---|
| 1 | Buy fichaunica.com + fichaunica.mx (Porkbun or Cloudflare) | Josh | 📋 |
| 2 | DNS: `A @`, `A app`, `A *` → server IP (`www` CNAME to @). If wildcard TLS goes through Cloudflare DNS, create an API token scoped to DNS edit for this zone only | Josh clicks, Claude lists the records | 📋 |
| 3 | Server user `fichaunica`, folders `/srv/fichaunica` (code) and `/srv/fichaunica-data` (db, media, backups, logs; never web-served) | Claude via SSH, Josh's yes | 📋 |
| 4 | `deploy/target.env` (from `.example`) + `$DATA_DIR/app.env` (from `deploy/app.env.example`, chmod 600) with a fresh `LLAVE_SECRET` | Claude | 📋 |
| 5 | Caddy (with the DNS module for the wildcard) using `deploy/Caddyfile`; systemd unit `deploy/fichaunica.service` | Claude | 📋 |
| 6 | Cron from `deploy/crontab.example` (daily backups, the 1-minute lead watch, the weekly price check) | Claude | 📋 |
| 7 | Off-site copy of backups (e.g. `--offsite-cmd "rclone copy {file} remote:fichaunica-backups"` to a bucket or Drive) | Josh picks the destination | 📋 |
| 8 | Error alerts: `LLAVE_ALERT_WEBHOOK` (a GHL inbound webhook → internal contact → WhatsApp to Samantha's alert line) and/or email | Samantha | 📋 |
| 9 | Lawyer-reviewed privacy notice + terms replace the drafts (`/aviso-de-privacidad`, `/terminos`, `/privacidad`) | Josh | 📋 |
| 10 | GHL "Ficha Única" sub-account + token; keep `LLAVE_GHL_LIVE` off until a 10-lead dry run is reviewed | Josh/Samantha | 📋 |

## Deploy (each time)
1. `deploy/deploy.sh` (dry run). Read what it would do.
2. `deploy/deploy.sh --go`: tests, then a server backup, upload of the release, symlink switch, restart, and a health check, with an automatic rollback if `/healthz` fails.
3. Smoke test: sign up a test agency, run the 3-step wizard with one listing, check the public page, feed, card and ficha, send a test lead from our own phone, and confirm it shows in Clientes and reaches the alert.

## The app refuses to start in production if
- `LLAVE_SECRET` is missing or the dev default (`check_production_config`).
- `LLAVE_BASE_DOMAIN` is still `*.localhost`.
- `LLAVE_GHL_LIVE=1` without `LLAVE_GHL_APPROVED_BY_JOSH`.

## Monitoring
- `/healthz` (DB ok, free disk, hours since the last backup). Point an uptime monitor at `https://app.fichaunica.mx/healthz`.
- Errors: rotating `errors.log`, plus at most one alert per error type every 15 min, with secrets/phones/emails redacted.
- Admin view `/admin` (role admin: `python3 tools/make_admin.py <email>`): clients waiting >5 min across all agencies.

## Restore (drill once before the pilot)
`python3 tools/backup.py --verify-latest`, then stop the service, gunzip the chosen `llave-*.db.gz` over `$LLAVE_DB`, untar the media archives in order, and start the service. Full steps: `llave.backup.restore_instructions()`.
