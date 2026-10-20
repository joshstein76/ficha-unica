# Stripe setup for Ficha Única (LLAVE): the exact clicks

Merchant: **Ciao Bella Marketing**. Plans: **Pro MXN 499/month** and **Pro + IA MXN 999/month**, IVA included. Gratis is MXN 0 and never touches Stripe.
Code: `llave/billing.py` (written 2026-10-19, never run against the real Stripe: the first test-mode purchase is its first real test).
Status: nothing here has been done. No Stripe account was created and no Stripe call was made while building this.

**Do it in TEST mode first.** Nothing is charged in test mode. Live mode needs Josh's explicit yes (Part 8).
**Never paste a key in chat.** Paste it into the file in Part 6 yourself, then just tell Claude "done".

## How it works (so the clicks make sense)
1. An agent opens `/plan`, picks Pro or Pro + IA, taps **Pagar con tarjeta**. The app asks Stripe for a Checkout page and sends the agent there. Card data goes to Stripe, never to our server.
2. When the payment succeeds Stripe calls `https://app.fichaunica.mx/stripe/webhook`. **Only that signed call changes the plan** (the page the agent lands on afterwards, `/plan?pago=ok`, only says thanks).
3. Agents who already pay use **Administrar mi pago** (Stripe's Billing Portal) to change plan, update the card or cancel. Stripe tells us, and the plan follows.
4. Cancelled or unpaid subscriptions go back to Gratis. **Listings are never deleted**; Gratis simply allows no new listing over its limit (1).

Until `config/stripe.env` is filled, none of this is active and plan changes stay in free TEST MODE exactly as before.

## Part 1. Stripe account and test mode
1. Sign in at dashboard.stripe.com with the **Ciao Bella Marketing** account (if it does not exist yet: create it under the company's legal name, EIN and bank account; Josh does this himself).
2. Switch to **Test mode** (toggle at the top right). If Stripe shows **Sandbox** instead of "Test mode", use the sandbox: its keys also start with `sk_test_`.
3. Everything below (products, webhook, portal) lives *per mode*: test and live are separate and nothing carries over.

## Part 2. The two products and prices
1. **Product catalog** → **Add product**.
2. Name: `Ficha Única Pro`. Pricing model: **Recurring**. Amount: `499.00`. Currency: **MXN**. Billing period: **Monthly**.
3. Open **More pricing options** (or the tax section) and set **Tax behavior = Inclusive** (the price already includes IVA). Save the product.
4. Open the product → under **Pricing** copy the **Price ID** (starts with `price_`). It is **not** the product ID (`prod_`).
5. Repeat for `Ficha Única Pro + IA`: **999.00 MXN**, monthly, tax behavior inclusive. Copy its `price_` ID.

## Part 3. The secret key
1. **Developers** → **API keys**.
2. **Secret key** → **Reveal test key** (starts with `sk_test_`). Copy it for Part 6. (Do not use the Publishable key; the app refuses it.)

## Part 4. The webhook
1. **Developers** → **Webhooks** → **Add endpoint**.
2. Endpoint URL: `https://app.fichaunica.mx/stripe/webhook` (the domain must already point to the server; before that, see the local-test note in Part 6).
3. Select exactly these 3 events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`. Add endpoint.
4. On the endpoint page → **Signing secret** → **Reveal** (starts with `whsec_`). Copy it for Part 6.

## Part 5. The Customer Portal
1. **Settings** (gear) → **Billing** → **Customer portal**. Make sure you are still in test mode.
2. Turn on:
   - **Customers can update payment methods**.
   - **Customers can cancel subscriptions**, with **Cancel at end of billing period** (so they keep what they paid for).
   - **Customers can switch plans**: add both products (Ficha Única Pro and Ficha Única Pro + IA), proration **on**. This is how a paying agent goes Pro ↔ Pro + IA (the app sends payers to the portal instead of selling a second subscription).
3. Business information: link the privacy policy `https://app.fichaunica.mx/privacidad` and terms `https://app.fichaunica.mx/terminos` (both are drafts until the lawyer reviews them). Save.

## Part 6. Put the settings in the file (never in chat)
On this Mac: copy `config/stripe.env.example` to `config/stripe.env` (it is gitignored) and fill the 4 lines:
```
STRIPE_SECRET_KEY=<the sk_test_ key from Part 3>
STRIPE_WEBHOOK_SECRET=<the whsec_ secret from Part 4>
STRIPE_PRICE_PRO=<price_ id of Ficha Única Pro>
STRIPE_PRICE_IA=<price_ id of Ficha Única Pro + IA>
```
On the server: the same file at `/srv/fichaunica-data/stripe.env` (`chmod 600`, outside the release folder so deploys do not erase it), and in `app.env` set `LLAVE_STRIPE_ENV_FILE=/srv/fichaunica-data/stripe.env`. Restart the service.

Check without printing any secret (prints only `True/False` and the names of problems):
```
python3 -c "from llave import billing; print(billing.enabled()); print(billing.config_problems())"
```
`True` and `[]` means ready. In production the app **refuses to start** with a live key but no `LLAVE_STRIPE_LIVE=1`, or with a missing price/webhook secret, and prints which one. If the file is empty it just warns that plan changes are still free test mode.

Local test of the webhook before the server is live (optional, unverified): install the Stripe CLI and run `stripe listen --forward-to http://app.fichaunica.localhost:8640/stripe/webhook`; it prints a temporary `whsec_` to use as `STRIPE_WEBHOOK_SECRET`.

## Part 7. Test it (test mode, no real money)
1. Sign up a test agent, open **Tu plan**, choose **Pro**, tap **Pagar con tarjeta**.
2. On Stripe's page use card `4242 4242 4242 4242`, any future date, any CVC, any name. Declined test: `4000 0000 0000 0002`.
3. You land on `/plan?pago=ok` ("Gracias: tu plan se activa en unos segundos"). Within seconds the card shows **Tu plan = Pro** and the page shows **Administrar mi pago**.
4. Check: Stripe **Developers → Webhooks → your endpoint** lists the events with **200**. In the app database, the table `audit` has a `plan_change_paid` row (actor `stripe`), and `agencies` has the `stripe_customer_id` / `stripe_subscription_id`.
5. Tap **Administrar mi pago** → switch to Pro + IA → back to Pro → **Cancel**. Each change shows up in the app a few seconds later (`customer.subscription.updated` / `.deleted`). With "cancel at end of period" the plan stays until the period ends; to see that quickly use Stripe **Billing → Test clocks**.
6. A promotion code (Stripe **Product catalog → Coupons**) works on the Checkout page; a 100% code still activates the plan.

## Part 8. Going live (only with Josh's explicit yes)
1. In Stripe: finish **Activate your account** (business details, bank account, identity). Without it live charges are blocked.
2. Switch to **Live mode** and repeat Part 2 (products + prices), Part 4 (webhook with the same URL and 3 events) and Part 5 (portal). New `price_` IDs and a new `whsec_`.
3. Replace the 4 values in the server's `stripe.env` with the live ones (live secret key: starts with `sk_` and then `live`).
4. In the server's `app.env` set `LLAVE_STRIPE_LIVE=1`. **That line is the explicit yes**: without it the live key is refused and the app will not start. Restart.
5. Josh buys Pro once with his own card, checks the plan flips and the audit row, then refunds himself in Stripe (**Payments → the payment → Refund**) and cancels.

## What the app does with each Stripe event
| Event | Effect |
|---|---|
| `checkout.session.completed` (subscription, paid) | Plan = the one chosen at checkout (from our metadata), saves the Stripe customer and subscription ids, audit `plan_change_paid` |
| `customer.subscription.updated` | `active`/`trialing`: plan follows the price (Pro ↔ Pro + IA). `canceled`/`unpaid`/`incomplete_expired`: Gratis. `past_due`/`incomplete`/`paused`: no change (Stripe is still retrying) |
| `customer.subscription.deleted` | Gratis, subscription id cleared (customer id kept), audit `plan_change_downgrade` |
| anything else | Acknowledged and ignored |

Safety built in: events are verified (HMAC-SHA256, 5-minute window, constant-time compare) and applied once per event id; a failure rolls back so Stripe's retry works; only a subscription linked at checkout can change a plan, so a late or replayed "active" from an old subscription cannot re-grant a paid plan; a second subscription for the same agent is flagged (`stripe_duplicate_subscription` in `audit`) instead of silently accepted.

In Stripe, also set **Settings → Billing → Subscriptions and emails → Manage failed payments** to cancel (or mark unpaid) after the retries: both end in Gratis. Turn on the customer emails for successful and failed payments (so Stripe, not us, sends receipts).

## Not verified, and for the lawyer / accountant
- **Never run against the real Stripe.** The request fields, the API version pin (`2024-06-20` in `llave/billing.py`) and the webhook field names follow Stripe's documentation from memory. The first test-mode purchase is the real check; expect to fix small things.
- **MXN on a US account.** Whether Ciao Bella Marketing's US Stripe account can show MXN prices and charge Mexican cards in MXN, what currency it settles in, and the conversion/FX fees: check in the dashboard and Stripe's pricing page, then confirm with one live purchase. Only card works for subscriptions (no OXXO/SPEI recurring).
- **IVA and facturas (CFDI).** The price says "IVA incluido", but that label does not register or pay any tax. Whether a US company selling a digital service to Mexican agents must register with SAT and collect/remit IVA, and how agents get a CFDI, is a Mexican tax lawyer/accountant question (same gate as Cerquito). Stripe Tax is **not** turned on. Do not promise facturas until this is answered.
- **Terms and cancellation text.** Auto-renewal and cancellation wording in `/terminos` is a draft until the lawyer reviews it.
- **Restricted keys.** The code accepts a restricted key (`rk_`) but the exact permissions it needs (Checkout Sessions: write, Customer portal: write) are untested. Use the normal secret key for the first run.
- **Language.** Checkout uses `locale=es`; Stripe also has `es-419` (Latin American Spanish). Switch if the wording looks off.
- **Not handled:** refunds, disputes and chargebacks do not change the plan (not subscribed); do those by hand in Stripe. No trial, no annual plan, no team seats.
