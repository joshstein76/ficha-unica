# LLAVE — decisions made while building (Josh delegated product/design calls, 2026-10-17)
Each line: the call, why, how to undo.

1. **Local stack = Python 3.9 stdlib + SQLite + Pillow, server-rendered HTML.** This Mac has no node and the brief said local only. A new Supabase project would mean a new account action. The schema is written to port 1:1 to Supabase Postgres (same family as Cerquito and RentaPóliza), which is the production target. Undo: none needed, port when we go live.
2. **Agent sites are rendered by LLAVE, not WordPress multisite.** One app renders every agent site straight from the listings database. That makes each site a thin layer over our data, the same thing EasyBroker sells. IDX Bloom's multisite is built for WordPress + MLS. We kept its Wix model (free subdomain first, own domain later) and its 3-design idea (Residencia / Ciudad / Costa ≈ Estate / Skyline / Coastal).
3. **One canonical home per listing.** A Bolsa share shows the listing on the sharer's site with the sharer's contact. The canonical points to the owner's page, and the sharer's sitemap leaves it out. This is the RentaPóliza 08-17 ruling and avoids the duplicate-content mistake we saw on EasyBroker agent sites.
4. **AI search built in:** RealEstateListing + Offer JSON-LD, plus `llms.txt` per site. It is the main edge over EasyBroker, whose agent sites ship no structured data (our 08-17 audit).
5. **Portals:** open formats first (Trovit / Mitula style, LLAVE open feed). Mercado Libre goes out as a dry-run payload, because the agent will connect their own account. Every other portal stays a stub that says it needs an agreement. The UI never claims a portal is live. The Trovit/Mitula formats are from public knowledge and marked "confirm with Lifull Connect".
6. **GHL dry-run only.** Each lead plans contact upsert + note + opportunity + agent alert into `outbox`. Nothing is ever addressed to the lead, because the first reply needs a template Josh approves. Live mode raises until a LLAVE sub-account exists (Q5).
7. **Photos:** we strip all EXIF (GPS is personal data), resize to 1600/800/400 in JPEG + WebP, and reject anything under 600 px or banner-shaped. Watermark is optional and OFF by default; we never add a watermark to someone else's photos. Floor plans under 600 px get rejected, so a plan exception is a later tweak.
8. **VIVE demo data:** only Heráclito 331 and Ritz 5203 are public (cleared). The other 6 Ritz units are `pausada`, with Josh's approval note kept internal. 5102 and 5002 have no price (marked "verify"). Only Heráclito is in the Bolsa.
9. **Plans in code:** gratis 10 listings / pro 50 / agencia 200. Matches proposal Q3-A; change `db.PLAN_LIMITS`.
10. **Privacy:** the lead form requires consent to a simplified notice. The notice is marked as a DRAFT for counsel (new 2025 data-protection law).
11. **Code name LLAVE** everywhere internal. The public brand waits for Q1 (Ficha Única / Inmo Abierta / Asesor Libre).

## Open items found while building
- The VIVE GHL token lacks the custom-fields read scope (`locations/customFields.readonly`). Needed before LLAVE fields can be created or checked.
- The first-reply template to leads (Spanish) needs Josh's OK.
- The "LLAVE Leads" pipeline doesn't exist yet. Create it with the sub-account.
