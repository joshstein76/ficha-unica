# LLAVE GHL dry-run vs VIVE (read-only) 2026-10-17

Only GET requests. No secrets, no contact data.

## Custom fields
Total fields in location: 0 (API error: The token is not authorized for this scope.)
- llave_listing_ref: missing
- llave_listing_url: missing
- llave_lead_source: missing

Field names: 

## Pipelines (8)
- VIVE Pipeline 26
- VIVE Advertising
- Desarrolladores
- AI Conversation Outcome
- AI Outreach
- ARCHIVO – Fernando 26 (no usar)
- Lorena Pipeline 26
- VIVE Guide 26

'LLAVE Leads' exists: no (expected no)

## Plan for a fake lead (listing from data/llave.db), NOT sent
- ghl.contact_upsert | body keys: customFields, email, firstName, lastName, locationId, phone, source, tags | tags: llave, llave-vive, op-venta, colonia-polanco-v-seccion
- ghl.note | body keys: body, locationId
- ghl.opportunity | body keys: locationId, monetaryValue, name, pipeline_name, stage
- ghl.agent_alert | body keys: text
- ghl.lead_first_reply | body keys: (none) | status: needs_template

NO WRITES MADE
