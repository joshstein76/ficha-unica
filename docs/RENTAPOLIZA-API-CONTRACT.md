# Contrato Ficha Única ⇄ RentaPóliza (borrador 2026-10-17)

Contract only. RentaPóliza is on hold (restart ~10-19): nothing here touches its code or accounts. Our side is `llave/eco.py` (`handle_rentapoliza_webhook`, `verify_webhook`).

## A. Ficha Única → RentaPóliza: botón "Solicitar póliza" (deep link, GET)
`https://<rentapoliza-domain>/solicitar?<params>` (final path set by RentaPóliza). All params URL-encoded, all optional except marked.

| Param | Example | Notes |
|---|---|---|
| `src` (required) | `fichaunica` | fixed |
| `listing_ref` (required) | `VIVE-0001` | our folio |
| `colonia` | `Polanco` | |
| `municipio` | `Miguel Hidalgo` | |
| `renta_mensual` | `25000` | pesos, integer |
| `moneda` | `MXN` | |
| `agent_email` | `ana@vive.mx` | identity used to credit the agent |
| `agent_whatsapp` | `+525512345678` | E.164 |
| `return_url` | `https://app.fichaunica.mx/servicios` | https only, our domain only |

No tenant or owner data in the link, ever. Params are a convenience; RentaPóliza validates its own.

## B. RentaPóliza → Ficha Única: signed webhook
`POST https://<fichaunica>/api/eco/rentapoliza` (endpoint wired later by Josh)

Headers: `Content-Type: application/json`, `X-Eco-Timestamp: <unix seconds>`, `X-Eco-Signature: sha256=<hex>`.
Signature = HMAC-SHA256(secret, `"<X-Eco-Timestamp>." + raw_body_bytes`), hex lowercase. Shared secret per brand, set out of band in the server env, never in a repo. Replay window: 5 minutes either side of our clock, else 401.

```json
{
  "event": "poliza.emitida",
  "folio": "RP-2026-000123",
  "agent_email": "ana@vive.mx",
  "agent_phone": "+525512345678",
  "listing_ref": "VIVE-0001",
  "emitted_at": "2026-10-20T15:04:05-06:00"
}
```
Required: `event`, `folio`, and `agent_email` or `agent_phone`. `listing_ref`, `emitted_at` optional. A valid signature IS the confirmation: +30 credits to the agency of that agent (rule `rentapoliza.poliza_emitida`).

## C. Responses and errors
| HTTP | body `code` | Meaning | Retry? |
|---|---|---|---|
| 200 | `confirmado` | credited | no |
| 200 | `duplicado` | same `folio` already processed, nothing credited again | no |
| 400 | `evento_no_soportado` / `folio_requerido` | bad payload | no, fix |
| 401 | `firma_invalida` / `timestamp_fuera_de_ventana` | signature or replay window | no, fix |
| 404 | `asesor_no_encontrado` | no Ficha Única agent with that email/WhatsApp | no (agent not registered; nothing is stored) |
| 5xx | | our side | yes, exponential backoff, same body is safe |

**Idempotency:** key is `folio`. Sending the same folio any number of times credits once. **PII:** only folio + agent identity + listing ref cross. We ignore any other field (tenant name, owner, ID numbers, amounts); RentaPóliza must not send them. Agent email/phone are used only to find the account and are not stored in the event (`meta` keeps `listing_ref`, `emitted_at`). Folio refund/cancellation event (`poliza.cancelada`) is not defined yet: until it is, reversals are manual by an admin (negative ledger row).
