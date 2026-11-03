# Dominio propio (plan Pro): cómo funciona y qué hay que cambiar en el servidor
Branch `b-dominio`. Code: `llave/domains.py`, `tools/domain_check_run.py`, routing in `llave/web/server.py`, card in `llave/web/panel.py` (`domain_card`). Decisions: `docs/DECISIONS.md` #48-#55.
**Nothing in this document has been done on the server.** The server was not touched, and no test makes a network call.

## What the agent sees (Mi sitio > Tu propio dominio)
1. Types `micasa.mx` (we strip `https://`, path, `www.`, port, case; reject our own domains and anything invalid; one agency per domain).
2. Gets plain Spanish steps for any registrar with the exact values from env: **CNAME `www` -> `LLAVE_CNAME_TARGET`** (or an **A** record to `LLAVE_PUBLIC_IP` if the registrar refuses a CNAME), and, optional, **A `@` -> `LLAVE_PUBLIC_IP`** so `micasa.mx` also opens.
3. Presses **Verificar ahora** (max 4 per 5 minutes, 30 per day) or waits: cron checks every 10 minutes.
4. States: **pendiente** (what is missing, per name), **verificado**, **problema** (it stopped working; the site is back on the free address; a notice in Mi sitio and on Inicio).

## What happens in the code
| Moment | What |
|---|---|
| Check | `www.micasa.mx` must resolve ONLY to `LLAVE_PUBLIC_IP` (several IPs allowed, comma separated). Stdlib `socket.getaddrinfo`, IPv4. The bare name is checked too, for the panel and for the certificate warm-up, but never required. If `LLAVE_PUBLIC_IP` is empty, our address is whatever `LLAVE_CNAME_TARGET` resolves to. |
| Verified | `domain_verified_at` is set, `/_tls/ask` starts approving `www.micasa.mx` and `micasa.mx`, and (production + `LLAVE_PUBLIC_IP`) the app opens one TLS connection to its own IP with each name as SNI so Caddy issues the certificate **now**. Until the certificate is confirmed (`domain_tls='espera'`) the free address keeps serving. |
| Serving | `www.micasa.mx` = the agent's site. `micasa.mx` -> 301 -> `https://www.micasa.mx<path>`. Free address -> 301 -> own domain (308 for a POST) once verified + Pro + certificate not pending. Redirects carry `Cache-Control: max-age=3600` so a browser never remembers them for years. Canonical, sitemap, robots, llms.txt, JSON-LD, feeds, photo URLs all come from `db.site_url` = `https://www.micasa.mx`. |
| Gratis | Own domain (either form) -> 302 to the free address, as `gratis-cap` does. Everything stays saved; upgrading brings it back. |
| Lost | 3 cron checks in a row where www has no record or points elsewhere (about 30 min): unverified, `domain_lost_at` set, back on the free address, nothing deleted. A lookup that fails (resolver down) never counts. The button never takes a domain off. When DNS is right again the next check verifies it by itself. |
| `/_tls/ask` | `app.`, the brand domain, `www.` brand, existing agency subdomains, and the www + bare form of a **verified** own domain. Everything else: 404. It shares one lookup with the router (`domains.agency_for_host`). |
| Notice to the agent | Panel only (Mi sitio + Inicio). For the email: `domains.check()` returns `event` `'verified'` / `'lost'` and writes `audit` rows `domain_verified` / `domain_lost` (actor `cron`); hook the mailer there. |

## Production vs the repo Caddyfile (read-only comparison; the live file was NOT read)
Sources: ledger 10-26/10-27 ("Caddy on-demand TLS", DNS on Hostinger, `A app` + `A *` -> 179.197.84.104), `2026-10-21-LIVE-IN-AN-HOUR-RUNBOOK.md` T+25, code inventory section 10.

| | `deploy/Caddyfile` (repo) | What production runs (per ledger + runbook) |
|---|---|---|
| Free sites `*.fichaunica.mx` | one wildcard certificate through the Cloudflare DNS plugin (needs Caddy built with the module, `CF_API_TOKEN`, DNS moved to Cloudflare) | on-demand certificate per subdomain (HTTP-01), DNS stays on Hostinger |
| `fichaunica.mx`, `www.fichaunica.mx` | proxied to the app | WordPress on Hostinger hosting; the app only answers `app.` and `*.` |
| Own domains | `https:// { tls { on_demand } }` catch-all | the same catch-all |
| `ask` | global `on_demand_tls { ask http://127.0.0.1:8640/_tls/ask }` | the same |
| `http://` | none | `http:// { redir https://{host}{uri} permanent }` |

For own domains Caddy needs three things, and production has them as documented: the global `ask`, the `https:// { tls { on_demand } ... reverse_proxy 127.0.0.1:8640 }` catch-all, and the `http://` redirect (so `http://www.micasa.mx` reaches https; ACME HTTP-01 is answered by Caddy before routes). **So no Caddy change is needed, only a check that the live file really has them** (below). The repo `Caddyfile` is the later Cloudflare-wildcard variant: do not copy it onto the server as is (it would send the WordPress hosts to the app and has no `http://` redirect). `deploy/Caddyfile.on-demand` is what production should look like for this feature.

## What must change on the server (in this order; each step is Josh's yes + the usual Hostinger load gate)
1. **Read the live Caddyfile first, change nothing.** `sudo cat /etc/caddy/Caddyfile` and `caddy adapt --config /etc/caddy/Caddyfile | grep -n -A2 on_demand`. It must contain: global `on_demand_tls { ask http://127.0.0.1:8640/_tls/ask }`, an `https:// { tls { on_demand } ... reverse_proxy 127.0.0.1:8640 }` block, and `http:// { redir ... }`. If `ask` is missing, stop: without it Caddy either refuses on-demand TLS or issues certificates for any name pointed at the server. If anything differs, copy it to `Caddyfile.bak-<date>`, align it with `deploy/Caddyfile.on-demand`, `caddy validate --config /etc/caddy/Caddyfile`, `systemctl reload caddy`. Keep it one writer at a time if the box is shared with Lía.
2. **DNS (hPanel, fichaunica.mx zone), no change expected, only verify:** `dig +short sites.fichaunica.mx` must print `179.197.84.104`. It resolves through the wildcard `A *`; if it does not, add `A sites -> 179.197.84.104` (TTL 300). The CNAME every agent creates points there.
3. **`/srv/fichaunica-data/app.env`:** add `LLAVE_PUBLIC_IP=179.197.84.104` (the VPS public IPv4; confirm with `curl -4 ifconfig.me` on the server). Optional: `LLAVE_CNAME_TARGET`, `LLAVE_OWN_DOMAINS` (e.g. `fichaunica.com`), `LLAVE_DOMAIN_WARM=0`. Keep the file `chmod 600`.
4. **Deploy this branch** (`deploy/deploy.sh --go`). The six new `agencies.domain_*` columns are added by `db.init` at start-up (additive; old code ignores them). Startup prints `AVISO: LLAVE_PUBLIC_IP...` to the log when step 3 was skipped.
5. **Cron** for user `fichaunica`: the new line in `deploy/crontab.example` (`*/10 * * * * ... python3 tools/domain_check_run.py >> /srv/fichaunica-data/logs/domain_check.log`). One line per run: `domain_check {...}`.
6. **Self-connection test** (the warm-up needs the server to reach its own public IP on 443): `openssl s_client -connect 179.197.84.104:443 -servername app.fichaunica.mx </dev/null 2>&1 | head -5` as `fichaunica`. If it hangs, set `LLAVE_DOMAIN_WARM=0` (own domains still work; the first visitor then waits 10-30 s for the certificate).
7. **Mi sitio / marketing copy:** the WordPress plans page may still say "muy pronto" next to the domain line; it is outside this repo.

## First real domain (do it with a domain Josh owns, not an agent's)
1. Pro test agency, Mi sitio, type the domain, follow the steps at the registrar, "Verificar ahora".
2. `curl -sI https://www.<domain>/` = 200 on the first try, `curl -sI https://<domain>/` = 301 to www (if the A record was set), `curl -sI https://<slug>.fichaunica.mx/` = 301 to www, `curl -s https://www.<domain>/sitemap.xml` shows www.
3. Remove the `www` record at the registrar, wait 30-40 minutes: the panel must show "dejó de apuntar", the free address must answer 200 again, `https://www.<domain>` stops being served. Put the record back: it verifies by itself within 10 minutes.

## Rollback
- **One domain, right now, no deploy:** `python3 - <<'EOF'` as `fichaunica` with app.env loaded: `from llave import db; c=db.connect(); c.execute("UPDATE agencies SET domain_verified_at=NULL WHERE slug='<slug>'"); c.commit()`. The free address serves at once and `/_tls/ask` stops approving the domain.
- **The checks:** delete the cron line. Verified domains stay verified; nothing is unverified automatically any more.
- **The code:** `deploy.sh` rolls back by itself if `/healthz` fails; by hand `ln -sfn <previous release> /srv/fichaunica/current && sudo systemctl restart fichaunica`. The new columns are harmless to old code. The old code serves only the bare name of a verified domain (www was a 404) and keeps `/_tls/ask` working.
- **The warm-up:** `LLAVE_DOMAIN_WARM=0` in app.env + restart.
- **Caddy**, only if step 1 changed it: restore `Caddyfile.bak-<date>` and `systemctl reload caddy`.

## Limits and what to expect
- **Ownership.** DNS pointing at us proves the agent controls the domain's DNS, not which agency should own it. Rules: one agency per domain; a verified domain, or an unverified claim younger than 14 days, cannot be taken; an older unverified claim can. The first to claim wins; a squatter can block a name for 14 days but cannot serve it until its DNS points at us. A stronger proof (a per-agency TXT/record) needs more than the stdlib resolver: see decision #50.
- Only IPv4 is compared. A domain with an AAAA record elsewhere may send some visitors away; the panel does not detect it.
- Cloudflare with the orange cloud resolves to Cloudflare's IPs, so it fails verification on purpose (the panel tells agents to use grey). A registrar that only offers CNAME on `www` and forwards the bare name is fine.
- Let's Encrypt's 50 certificates per week apply per registered domain, so own domains do not spend the brand domain's quota. One failed order for a bare name that does not point to us costs nothing but a log line; we only warm the bare name when it does point to us.
- The VPS resolver may cache a negative answer for a few minutes: a domain fixed at the registrar can take a couple of cron runs to verify.
