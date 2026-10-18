# Ecosistema Ficha Única (code LLAVE) — 2026-10-17

Josh (verbatim): "if you need a póliza for a rental and you use RentaPóliza within our system, you get free leads. We want to keep everything within our ecosystem. Everything runs through GoHighLevel in an interconnected system: independent companies all working through the same systems, helping each other. I own all of them."

Engine: `llave/eco.py` (tables `eco_events`, `eco_ledger`, `eco_boosts`). Status: engine + tests only; routes/UI not wired; GHL is dry-run (outbox). All numbers below are **Claude's proposal, Josh can change** (they are data in `eco.RULES` / `eco.CATALOG`).

## 1. Rewards (credits)
Credits are granted only when the sister brand **confirms** the event (signed webhook/API) or an admin does. Never on the agent's claim alone. One event per (brand, ref): a repeat changes nothing.

| Event | Credits | Confirmed by |
|---|---|---|
| rentapoliza.poliza_emitida (póliza issued for the agent's rental) | 30 | RentaPóliza signed webhook |
| vive.referido_cerrado | 50 | VIVE (Fernando/Josh). The 50/50 commission is handled by VIVE, not by us |
| vive.referido_enviado | 5 | VIVE acknowledges the referral |
| cerquito.pedido | 5 per order | Cerquito order paid |
| idxbloom.referido_alta | 20 | IDX Bloom signup |
| ciaobella.cliente_alta | 20 | Ciao Bella client signed |
| fichaunica.colega_publica | 10 | Us: invited colleague publishes (ties to the referral loop) |

## 2. Redeem catalog
| Item | Cost | What the agency gets |
|---|---|---|
| destacar_7d | 20 | One listing featured 7 days: priority order in the Bolsa and in the public Ficha Única directory |
| extra_10_listings_30d | 30 | +10 listings above the plan limit for 30 days |
| prioridad_leads_30d | 40 | Priority in routing of GENERAL leads for 30 days |

Boosts of the same kind stack end to end, never overlap. The ledger is append-only (a redeem is a negative row).

## 3. "Free leads": the honest definition
> Los leads gratis vienen únicamente del tráfico propio de Ficha Única (el directorio, los feeds y las consultas generales del portal que no son de una propiedad en particular). Se reparten entre las inmobiliarias con prioridad activa en su zona. No garantizamos un número de leads: depende del tráfico y de la demanda de cada zona.

(Constant `eco.FREE_LEADS_DEFINITION`.) General lead = inquiry not tied to one listing. Router: `eco.priority_agencies(con, colonia, municipio)` returns agencies with an active priority and a listing in that zone, most credits first. A lead tied to a listing always goes to that listing's agency.

## 4. GHL backbone
One GHL account family, one sub-account per company; shared tags so any workflow in any sub-account can read the same story. Planner: `python3 tools/eco_ghl_tags.py` (dry-run, reads no token).

**Tags:** `eco-source-<brand>` (where the contact came from), `eco-referral-<from>-<to>` (who referred whom), `eco-cliente-<brand>` (is a customer of that brand). Brands: fichaunica, vive, rentapoliza, idxbloom, ciaobella, cerquito.

**Cross-referral workflows** (each is a GHL workflow whose last step is the "Webhook" action to `POST https://<fichaunica>/api/eco/<brand>`, signed per the contract; endpoint to be wired by Josh):

| Flow | Trigger | Webhook fired | Receiving company does |
|---|---|---|---|
| Ficha Única → RentaPóliza | Rentals pipeline stage "Póliza" (W8) | RentaPóliza → us on `poliza.emitida` | Agent gets a prefilled "Solicitar póliza" link; on issue, we confirm +30 |
| Ficha Única → VIVE | Agent taps "Referir" (luxury CDMX client/property) | VIVE → us on `referido_enviado` / `referido_cerrado` | Fernando contacts the agent, agrees the 50/50 in writing |
| VIVE → Ficha Única | Closed deal / VIVE broker network | tag `eco-referral-vive-fichaunica` | Broker invited to a free Ficha Única site |
| Ficha Única ⇄ IDX Bloom | Agent sells in Miami | IDX Bloom → us on `referido_alta` | IDX Bloom onboarding; +20 on signup |
| Ficha Única ⇄ Ciao Bella | Agent asks for marketing/SEO | Ciao Bella → us on `cliente_alta` | Ciao Bella follows up; +20 when signed |
| Ficha Única ⇄ Cerquito | Agent orders flyers/merch | Cerquito → us on `pedido` | Cerquito prints; +5 per paid order |

Phase 1 receives the webhook per brand in this order: RentaPóliza (engine done), then VIVE, Cerquito, IDX Bloom, Ciao Bella (same shape: add a handler beside `handle_rentapoliza_webhook`).

**Human approval points:** every message to an outside person is previewed by Josh first (exact words + recipient); reward changes, new templates, and the first real activation of each flow need Josh's yes. Until then, GHL effects are only dry-run outbox rows (`ghl.tag`). Never contacts the Alara group (blocklist honoured via `ghl.is_blocked`).

## 5. Owner dashboard (Josh)
`eco.owner_report(con, days=30)`: per brand events / confirmed / credits; per pair counts (`fichaunica→rentapoliza: n`, …, confirmed only); top 10 agencies by credits earned plus current balance. To add in UI: pending events awaiting confirmation, boosts active, credits outstanding (liability).

## 6. Never promise
- A number of leads, or any lead at all. - That credits are money, cashable or transferable. - Commission outcomes of VIVE referrals (VIVE decides, in writing). - Rankings on Google/AI assistants. - That RentaPóliza is live (on hold: copy says "Próximamente" until it restarts). - Credits for unconfirmed events. - Sharing tenant/owner personal data between companies.
