# Lía — the AI chat on agent sites

"Estás en una visita. Un cliente te escribe. Lía ya le contestó." Lía is a chat panel on an agent's own site (home and listing pages). She answers from the agency's public data, hands off what she cannot know, proposes visits (the agent confirms) and collects contact details through a consent form. WhatsApp comes later; this chat needs no number.

Code: `llave/lia.py` (engine) · `llave/web/lia_ui.py` (widget) · `llave/web/static/lia.js` + `lia.css` · routes in `llave/web/server.py` (`lia_api`) · tests `tests/test_lia.py` · migration `supabase/migrations/0009_lia_chat.sql`.

## Turn her on for one test agency

All four must hold or the page is byte-identical to today's and the three endpoints answer the normal 404:

| Gate | How |
|---|---|
| 1. Server flag | `LLAVE_LIA_LIVE=1` in the app environment (`deploy/app.env.example`) |
| 2. Live AI | `LLAVE_AI_LIVE=1` + a key in `config/anthropic.env` (or `ANTHROPIC_API_KEY`) + room under the monthly cap (`ai/client.enabled`) |
| 3. Plan | Pro + IA: `python3 tools/set_plan.py <slug> ia --reason "Lía test"` |
| 4. The agency's own switch | Mi sitio → "Lía contesta en tu sitio" → Guardar (it only shows when 1 and 3 hold), or `UPDATE agencies SET lia_enabled=1 WHERE slug='<slug>'` |

She is OFF for every agency by default (`agencies.lia_enabled` = 0). Nobody sees the switch until the server flag is on, so the owner sees her first. Turn her off again by removing `LLAVE_LIA_LIVE` (everything vanishes at once) or by flipping the agency's switch.

A contact form for a chat already in progress keeps working when only the AI is paused (budget): the contact endpoint needs gates 1, 3 and 4, not 2.

## What the client sees

- "Pregúntale a Lía" button bottom right, above the mobile bar (phone) or the WhatsApp float (desktop). It opens a full-screen chat on a 375 px phone, a 392 px floating panel from 701 px.
- First message (fixed text, never a model call): "Hola, soy Lía, la asistente de {agency}. Soy una asistente de inteligencia artificial, no una persona." On a listing page it adds "Veo que estás viendo «{title}»" and she gets that property's facts.
- Typing indicator while the answer is on its way. Replies are 1-3 short sentences, one question at most.
- When the model sets `ask_contact` (or on a hand-off, a visit request, a phone typed in the chat, a limit, an after-hours message or any AI failure) a small form appears: name, WhatsApp, required consent checkbox linking the site's own `/aviso-de-privacidad`.
- The chat survives a reload in the same tab (signed thread token in `sessionStorage`, one thread per page context).
- Outside 7:00 a.m.-8:00 p.m. Mexico City time there is no model call; the owner's exact message is shown once, with the agency name, and the form is offered.

## Her rules and where each one is enforced

| Rule | Prompt | Code (the model is never trusted) | Test |
|---|---|---|---|
| Says she is Lía, {agency}'s assistant, and an AI | yes | the first message is fixed text stored as the thread's first row; a reply claiming to be a person is replaced (`HUMAN_RE`, "no soy una persona" still passes) | `test_greeting_is_fixed...`, `test_guard_replaces...` |
| Facts only from the agency's public listings and profile | yes | `facts_for` builds the data from `db.canonical` + `writer.facts` (no internal notes, commissions, emails, phones; an unticked "mascotas" box is not sent as a fact) | `test_stable_prompt...` |
| Any figure not in the facts => not sent | yes (times and dates in words) | writer's `_numbers`/`BANNED`/`EMOJI` reused: such a reply is replaced by the safe hand-off line and the thread becomes `handoff` | `test_number_guard_*` |
| No markdown, emoji, links, emails, promises, superlatives | yes | cleaned (markdown, emoji) or replaced (URL, email, "garantizo", "la mejor") | `test_guard_replaces...` |
| Never confirms a visit | yes | confirmation wording (`confirmada`, `agendé`, `te espero`, `nos vemos`) or a visit reply that never says the agent confirms => fixed line "Anoté tu solicitud de visita... {agent} la confirma contigo; todavía no está confirmada." The requested time is only recorded | `test_a_visit_is_never_confirmed` |
| Three endings | yes | `status` answering / handoff / visit_requested; a thread's status only moves forward; guard, cap, night and AI failure all land on handoff | `test_thread_status_never_goes_backwards` |
| Commissions, discounts, legal, tax, money, other clients, competitors | yes (hand-off line) | `RISKY_RE` blocks promises and negotiating; the topic itself is the model's call | partly |
| Client text is data | yes (rule 17) | client text only ever appears as a `user` turn, never in the system blocks | `test_client_text_is_data...` |
| Hours | n/a | `hours_open` (UTC-6), checked before any model call | `test_hours_*`, `test_after_hours_*` |
| Contact details | yes | phones (10+ digits) and emails typed in the chat are replaced by `[dato de contacto omitido]` before storing or sending to the model; only the form (with consent) calls `leads.create_lead` | `test_a_phone_typed...`, `test_lead_is_created_only...` |

## Limits (all env-tunable, `LLAVE_LIA_<NAME>`)

| Limit | Default | Over it |
|---|---|---|
| `THREAD_REPLIES` model replies per chat | 12 | friendly line + form, no model call |
| `AGENCY_DAILY` model replies per agency, from midnight Mexico City | 80 | same, "hoy ya atendí muchas consultas" |
| `IP_MSG_HOUR` messages per visitor IP per hour | 30 | HTTP 429 with a friendly line + form |
| `IP_THREAD_HOUR` new chats per IP per hour | 5 | same |
| `IP_CONTACT_HOUR` contact-form tries per IP per hour | 6 | 429 |
| Message length | 500 characters | 400, nothing stored |
| Request body | 8 KB | 413 |
| Monthly AI cap | `LLAVE_AI_MONTHLY_CAP_USD` (50) | `budget.allow` stops the call: friendly line + form. Each call reserves its worst case (max_tokens 8000, about US$0.17), so the last cents of the cap are not spendable |

Also: honeypot field `website` (a filled one stores nothing and spends nothing), `Origin` must match the site's own host, `Content-Type: application/json`, thread token = HMAC-SHA256 with the app `SECRET`, scoped to the agency, valid 24 hours. Message text is never written to a log (the request line only; unexpected errors print a class name).

## Claude API call

Raw urllib via `ai/client.py` (extended with `messages`, `max_tokens`, `retries`; defaults unchanged). `claude-opus-5-5`, `output_config.effort: low`, `fallbacks: default`, structured output (`reply`, `status`, `ask_contact`, `summary`, `requested_time`), no prefill, no temperature, `max_tokens` 8000 (thinking counts), 30 s per attempt and one retry. `system` = [stable prompt (cache_control), the agency's facts (cache_control)]; history is append-only (the last user turn carries a third cache_control). `stop_reason` handling is `parse_response`'s: refusal, max_tokens, empty and non-JSON bodies become `AIError`, which becomes the friendly line + form. `budget.allow` runs before and `budget.record` after every call, on the request's own connection.

## Data

`lia_threads` (agency, listing, status, one-line summary, requested time, replies used, night shown, lead) and `lia_messages` (role, kind, body, model_call). Created by `db.init` from `schema.sql`; `agencies.lia_enabled` is added by `db.init` on old databases. The IP is not stored with a chat (only in `rate_events`, kept 2 days, like every other guard). A chat becomes a lead only through the form: `leads.create_lead(..., source='lia', consent=True)` (the consent rule now covers `lia`), so the blocklist, the 10-minute duplicate guard and the GHL queue apply. The lead's `message` holds the status, the summary, the unconfirmed visit request and the transcript (3,800 characters, newest lines kept); Clientes shows the summary, the visit request ("sin confirmar") and the full transcript from the tables, escaped.

## For the lawyer: what the privacy notice must now say

The agent-site notice (`site.privacy`) is still the old draft and says nothing about this. It must now cover, at least:

1. **An AI assistant answers the chat** and says so in her first message. The notice should say that replies are generated automatically, can be wrong, and that a person (the agent) confirms visits and anything she hands off.
2. **What is collected in the chat**: everything the visitor types (free text can include names, family situation, budget or other financial details, which may count as patrimonial data), the property being viewed, timestamps, and the name and WhatsApp typed in the form. Phones and emails typed in the chat are not kept (they are replaced before storing), but other personal data typed freely is.
3. **Who is responsible and who processes**: the agency is the responsable; Ficha Única (Ciao Bella Marketing) is the encargado that hosts the chat.
4. **Third parties and transfers abroad**: the conversation is sent to Anthropic (United States) to generate each reply; a lead created from a chat is copied to GoHighLevel (United States) with the summary and the transcript; hosting. For a Bolsa listing the lead and transcript go to the listing's owner agency. The lawyer must decide how Anthropic's API data terms (retention, no training) are described.
5. **Purposes**: answering the question, passing it to the agent, following up by WhatsApp/phone after the consent checkbox. The checkbox text today is only "Acepto el aviso de privacidad"; decide whether it must also name WhatsApp follow-up.
6. **Retention**: transcripts are kept until deleted. There is no automatic purge yet (open decision: how long, then add a job).
7. **ARCO rights for transcripts**: how to ask the agency, and that deleting a chat today is a manual database action by the platform (no button yet).
8. **Storage on the device**: a signed chat token in the browser's `sessionStorage` (this tab only, no cookie) so a reload keeps the conversation.
9. **Minors and sensitive data**: the chat is open to anyone; the prompt does not ask for sensitive data but cannot stop a visitor typing it.
10. **No automated decisions with legal effect**: she never confirms a visit, quotes a discount, or gives legal, tax or financial advice.

## Cannot be proven without a real key (nothing here ever made a real call)

- That the API accepts the request exactly as built (system as blocks with `cache_control`, content-block messages, `json_schema` with an enum, `effort: low`, the `fallbacks` beta header) and returns `stop_reason: end_turn` inside 8,000 tokens with thinking on.
- Prompt-cache hits (`cache_read_input_tokens` in the usage the budget records). The prompt plus facts may be under the minimum cacheable length for this model.
- Real tone and quality in Mexican Spanish and English: one question at a time, the rules on commissions/legal, off-topic redirection, prompt-injection resistance.
- How often the code guards fire on real replies. Watch `SELECT detail, COUNT(*) FROM audit WHERE action='reply_replaced' GROUP BY detail`: many `cifras` means she writes "$4.5 millones" instead of the full price; many `confirma_visita` means the wording list is too broad; `error` rows in `lia_messages` mean timeouts or `max_tokens`.
- Latency (the typing indicator) and the cost per chat against the US$50 cap.
- Layout, the on-screen keyboard and focus behaviour in a real phone browser (the JS was run against a mock page, not a browser).

## Known gaps

- The fixed lines (fallback, limits, safe hand-off) are Spanish even if the visitor writes English; the night message is the owner's exact Spanish text.
- Anonymous chats that never reach the form are not shown in Clientes (there is no one to answer).
- No retention job and no delete button (see the lawyer list).
- The plans page does not list Lía yet (she is not announced before the owner sees her).
- Migration `0009_lia_chat.sql` may need re-sequencing at merge. It also adds `lia` and `vendedor` to the Postgres `leads_source_chk` (the valuation page already writes `vendedor`).
