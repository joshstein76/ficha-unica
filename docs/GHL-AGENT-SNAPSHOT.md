# Snapshot "Ficha Única Agente" (LLAVE) - spec 2026-10-17

Legend: **API** = scriptable by `tools/ghl_snapshot_setup.py` (or documented API) | **UI** = built by hand in GHL, then saved as the snapshot (snapshot creation itself is UI-only). All texts: Spanish, "usted", short, human. Nothing is sent to anyone until Josh switches workflows on.

## 1. Pipelines (API: POST /opportunities/pipelines, verified in GHL docs)
- **Compradores**: Nuevo > Contactado > Cita agendada > Visitó > Oferta > Cerrado ganado / Cerrado perdido
- **Vendedores/Captación**: Nuevo > Valuación > Firma de exclusiva > Publicado > Vendido / Perdido
- **Rentas**: Nuevo > Contactado > Visita > Solicitud > Póliza (RentaPóliza) > Firmado / Perdido

## 2. Custom fields (API, contact model)
fu_listing_ref, fu_listing_url, fu_listing_price (number), fu_operation (venta/renta/compra), fu_colonia, fu_budget (number), fu_source, fu_agent.

## 3. Tags (API)
fu-lead, fu-web, fu-bolsa, fu-compra, fu-renta, fu-venta, fu-no-contactar. `fu-portal-<name>` is created on demand per portal (API, at first lead from that portal). Saved-search tags for alerts: `fu-alerta-<colonia>` (on demand).

## 4. Workflows (UI-only: no create API; read-only list via API)
Every workflow: exits on tag `fu-no-contactar` or DND; sends only in contact's language (Spanish); WhatsApp first, SMS fallback if WhatsApp fails/undelivered in 2 min, then email.

**W1 Primer respuesta instantánea.** Trigger: tag `fu-lead` added / form submitted / inbound portal lead. Steps: set pipeline Nuevo > send WhatsApp > if not delivered wait 2 min > SMS > if no phone, email.
- Con nombre: "Hola {{contact.first_name}}, gracias por escribir sobre {{custom_values.propiedad}}. Soy {{user.first_name}} de {{custom_values.inmobiliaria}}. ¿Le comparto más fotos y detalles por aquí o prefiere agendar una visita?"
- Sin nombre: "Hola, gracias por escribir sobre {{custom_values.propiedad}}. Soy {{user.first_name}} de {{custom_values.inmobiliaria}}. ¿Le comparto más fotos y detalles por aquí o prefiere agendar una visita?"
- Email subject: "{{contact.first_name}}, sobre {{custom_values.propiedad}}" (name + 2-5 words); same body.

**W2 Alerta 5 minutos.** Trigger: W1 sent. Wait 5 min; if no inbound reply and no agent outbound: internal notification (WhatsApp/SMS/email to agent): "Lead sin respuesta hace 5 min: {{contact.name}} - {{contact.phone}} - {{custom_values.propiedad}}." Move to Contactado only when agent replies.

**W3 Seguimiento (máx. 2).** Trigger: W1 sent and no reply. Wait 1 day > touch 1: "Hola {{contact.first_name}}, ¿pudo ver la información de {{custom_values.propiedad}}? Con gusto le ayudo." Wait 2 days (day 3) > touch 2: "Hola {{contact.first_name}}, le escribo una última vez por {{custom_values.propiedad}}. Si le interesa, aquí estoy." Then STOP, tag `fu-seguimiento-cerrado`. No third touch ever. Any inbound reply cancels the workflow.

**W4 No gracias / baja.** Trigger: reply contains "no gracias", "no me interesa", "ya no" (Conversation AI intent / keyword). Steps: send "¡Gracias a usted! Aquí estamos si más adelante le interesa." > add DND (all channels) + tag `fu-no-contactar` > move to Cerrado perdido. Opt-out words (STOP, BAJA, CANCELAR, "no me escriban", "no más") = DND immediately, no reply beyond the closing line; never a follow-up.

**W5 Agendar visita.** Trigger: reply "visita"/"agendar" or tag `fu-quiere-visita`. Send calendar link ("Visitas"): "Con gusto. Elija el día y la hora aquí: {{calendar.link}}". On booking: pipeline Cita agendada; confirmation message with address; reminder night before (8 p.m.): "Le recordamos su visita mañana a las {{appointment.start_time}}. ¿Nos confirma?"; reminder 1 h before: "Su visita es en 1 hora. ¿Nos confirma?". If no confirmation reply to either: cancel appointment, remove from agent calendar, message "Cancelamos su visita por falta de confirmación; con gusto la reagendamos.", notify agent. Minimum notice 24 h (agent sets).

**W6 Cierre ganado.** Trigger: stage Cerrado ganado. Day 1: review request (Google link, see 10). Day 30: referral ask: "Hola {{contact.first_name}}, ¿conoce a alguien que busque comprar, vender o rentar? Con gusto lo atiendo igual."

**W7 Alertas de propiedades (semanal).** Trigger: weekly schedule (Mon 10 a.m.) for contacts with `fu-alerta-*` and not DND. Sends up to 3 new listings link. Weekly max 1 message.

**W8 Póliza (Rentas).** Trigger: stage Póliza (RentaPóliza). Sends RentaPóliza link; internal alert to agent.

## 5. Calendars (UI-only in this spec; calendar create endpoint UNKNOWN, not verified)
"Visitas": 1 h slot, 30 min buffer before/after, min notice 24 h, Mon-Fri 9:30-17:30 default (agent edits), Google Calendar sync, confirmation + reminders via W5.

## 6. Email templates (UI; builder endpoint exists but not scripted here)
Leads: subject = first name + 2-5 words ("María, sobre Polanco 3 rec"). Transactional (confirmación de visita, recordatorio): plain subject, no name ("Confirmación de su visita"). Plain-text look, no heavy design.

## 7. Social planner kit (UI/semi-API; drafts only, never scheduled without agent's yes)
Weekly: 3 listing posts (Ficha Única cards/carousels), 1 market-data card, 1 tip. Status always draft.

## 8. Newsletter template (UI)
Monthly; subject has no first name; 3 listings + 1 market note; unsubscribe footer.

## 9. Reputation (UI)
Review request (Google): "Hola {{contact.first_name}}, fue un gusto ayudarle. ¿Nos regala una reseña? Le toma 1 minuto: {{reputation.google_link}}".

## 10. Conversation AI bot "Asistente de {asesor}" (UI)
Prompt (Spanish): "Eres el Asistente de {asesor}, de {inmobiliaria}. Hablas en español, de usted, corto, cálido y humano (1-3 líneas). Nunca inventas datos, precios, medidas ni disponibilidad: si no lo sabes, dices que {asesor} lo confirma. Recoges nombre, teléfono, presupuesto, zona y operación (compra/renta/venta), una pregunta a la vez. Para visitas, negociación, precio final o cualquier duda legal, pasas la conversación a {asesor}. Si dicen 'no gracias' o piden no recibir mensajes, respondes '¡Gracias a usted!' y te detienes. Nunca presionas ni insistes." Handoff: tag `fu-humano`, internal alert.

## 11. Trigger links (UI)
Ver ficha (listing URL), Agendar visita (calendar), WhatsApp directo, Pedir valuación (Vendedores). Click adds tag `fu-clic-<tipo>`.

## 12. Dashboard (UI)
Widgets: leads nuevos (7 d), tiempo a primera respuesta, leads sin respuesta >5 min, citas esta semana, oportunidades por pipeline, cerrados ganados (mes).

## Matrix
| Element | Mode |
|---|---|
| Pipelines, custom fields, tags, custom values | API |
| Calendars, email templates, social posts, forms | API exists in part; UNKNOWN/unverified here; treat as UI |
| Workflows W1-W8, Conversation AI, triggers, reputation, dashboard, trigger links | UI-only |
| Snapshot creation | UI-only (API: list, share link) |
