"""Stripe subscription billing for Ficha Única (Josh 10-19: the first agents pay).

Merchant: Ciao Bella Marketing. Prices are MXN with IVA included (set on the Stripe prices, see docs/STRIPE-SETUP.md).
Stripe's REST API over urllib (no SDK, no third-party packages). Nothing here runs unless `enabled()`.

Settings come from env vars or `config/stripe.env` (gitignored; production: LLAVE_STRIPE_ENV_FILE=/srv/fichaunica-data/stripe.env):
  STRIPE_SECRET_KEY  STRIPE_WEBHOOK_SECRET  STRIPE_PRICE_PRO  STRIPE_PRICE_IA
Safety: a live key is refused unless LLAVE_STRIPE_LIVE=1 (Josh's explicit yes). Keys are never logged, printed or stored;
card data never touches this server (Stripe Checkout and the Billing Portal are Stripe-hosted pages).

Money flow: the agent pays on Stripe -> Stripe calls POST /stripe/webhook -> `handle_event` changes `agencies.plan`.
Only a verified, signed event changes a plan; the redirect back to /plan?pago=ok never does.
"""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, 'config', 'stripe.env')
API = 'https://api.stripe.com/v1'
STRIPE_VERSION = '2024-06-20'   # pinned; bump on purpose (checked fields: session.url, subscription.items.data[].price.id, status)
TIMEOUT = 20                    # seconds per Stripe call
TOLERANCE = 300                 # webhook timestamps older (or newer) than this are rejected
MAX_WEBHOOK_BYTES = 1024 * 1024

SETTING_KEYS = ('STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET', 'STRIPE_PRICE_PRO', 'STRIPE_PRICE_IA')
PAID_PLANS = ('pro', 'ia')
HANDLED_EVENTS = ('checkout.session.completed', 'customer.subscription.updated', 'customer.subscription.deleted')
ACTIVE_STATUSES = ('active', 'trialing')
ENDED_STATUSES = ('canceled', 'unpaid', 'incomplete_expired')

_KEY_RE = re.compile(r'^(?:sk|rk)_(test|live)_[A-Za-z0-9]+$')
_SECRET_IN_TEXT = re.compile(r'\b(?:sk|rk|whsec)_[A-Za-z0-9_*]+')


class BillingError(Exception):
    """Clean, key-free error. `code` is machine-readable; `status` is the Stripe HTTP status when there was one."""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class BadSignature(BillingError):
    pass


# ---------- settings ----------
def _read_file():
    path = os.environ.get('LLAVE_STRIPE_ENV_FILE') or ENV_FILE
    out = {}
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def settings():
    """-> {STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_PRO, STRIPE_PRICE_IA}; real env vars win over the file.
    Holds secrets: never print or log this dict."""
    f = _read_file()
    return {k: (os.environ.get(k) or f.get(k) or '').strip() for k in SETTING_KEYS}


def key_mode(key):
    """'test' | 'live' | None (not a Stripe secret/restricted key)."""
    m = _KEY_RE.match(key or '')
    return m.group(1) if m else None


def live_allowed():
    return os.environ.get('LLAVE_STRIPE_LIVE') == '1'


def _usable_key(s=None):
    """The secret key if it may be used: test keys always, live keys only with LLAVE_STRIPE_LIVE=1."""
    key = (s or settings())['STRIPE_SECRET_KEY']
    mode = key_mode(key)
    return key if mode == 'test' or (mode == 'live' and live_allowed()) else None


def enabled():
    """True only with a usable key and both price IDs. Otherwise the app keeps its free TEST MODE plan switch."""
    s = settings()
    return bool(_usable_key(s) and s['STRIPE_PRICE_PRO'] and s['STRIPE_PRICE_IA'])


def config_problems():
    """Startup check (server.check_production_config). Empty when Stripe is simply not configured."""
    s = settings()
    if not any(s.values()):
        return []
    out = []
    mode = key_mode(s['STRIPE_SECRET_KEY'])
    if not s['STRIPE_SECRET_KEY']:
        out.append('Stripe is half configured: STRIPE_SECRET_KEY is missing')
    elif mode is None:
        out.append('STRIPE_SECRET_KEY is not a Stripe secret key (it must be a test or live key, never a publishable key)')
    elif mode == 'live' and not live_allowed():
        out.append('STRIPE_SECRET_KEY is a live key: it needs LLAVE_STRIPE_LIVE=1 (Josh\'s explicit yes)')
    for name in ('STRIPE_PRICE_PRO', 'STRIPE_PRICE_IA'):
        if not s[name]:
            out.append('%s is missing (Stripe price id, price_...)' % name)
        elif not s[name].startswith('price_'):
            out.append('%s must be a price id (price_...), not a product id' % name)
    if not s['STRIPE_WEBHOOK_SECRET']:
        out.append('STRIPE_WEBHOOK_SECRET is missing: payments would be taken but plans would never activate')
    return out


def is_paying(agency):
    """A paid plan backed by a Stripe subscription (those agents manage everything in the Billing Portal)."""
    a = dict(agency)
    return bool(a.get('stripe_subscription_id')) and db.plan_of(a) in PAID_PLANS


# ---------- Stripe REST ----------
def _scrub(text, key=''):
    t = str(text)
    if key:
        t = t.replace(key, '[REDACTED]')
    return _SECRET_IN_TEXT.sub('[REDACTED]', t)


def _post(path, params, idem_key=None):
    """Form-encoded POST to https://api.stripe.com/v1<path> -> parsed JSON. Raises BillingError (never carries the key).
    The only function that touches the network: tests monkeypatch it."""
    key = _usable_key()
    if not key:
        raise BillingError('Stripe no está configurado', 'no_configurado')
    body = urllib.parse.urlencode([(k, str(v)) for k, v in params.items() if v is not None]).encode('utf-8')
    req = urllib.request.Request(API + path, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Stripe-Version': STRIPE_VERSION,
        'Idempotency-Key': idem_key or uuid.uuid4().hex,
        'User-Agent': 'FichaUnica-LLAVE/1',
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as ex:
        try:
            err = json.loads(ex.read().decode('utf-8')).get('error') or {}
        except Exception:
            err = {}
        raise BillingError(_scrub(err.get('message') or 'Stripe respondió HTTP %d' % ex.code, key),
                           err.get('code') or err.get('type') or 'http_%d' % ex.code, ex.code) from None
    except (urllib.error.URLError, OSError):
        raise BillingError('No se pudo contactar a Stripe', 'red') from None
    try:
        return json.loads(raw.decode('utf-8'))
    except ValueError:
        raise BillingError('Respuesta inesperada de Stripe', 'respuesta_invalida') from None


def checkout_url(con, agency, user, plan):
    """Stripe Checkout Session (subscription) for pro | ia -> the hosted payment page URL."""
    if plan not in PAID_PLANS:
        raise BillingError('Ese plan no se cobra', 'plan_invalido')
    price = settings()['STRIPE_PRICE_PRO' if plan == 'pro' else 'STRIPE_PRICE_IA']
    if not price:
        raise BillingError('Falta el precio de Stripe para este plan', 'sin_precio')
    a = dict(agency)
    row = con.execute('SELECT stripe_customer_id FROM agencies WHERE id=?', (a['id'],)).fetchone()
    customer = (row['stripe_customer_id'] if row else None) or None
    app = db.origin('app')
    params = {
        'mode': 'subscription',
        'line_items[0][price]': price,
        'line_items[0][quantity]': 1,
        'locale': 'es',
        'client_reference_id': a['id'],
        'metadata[agency_id]': a['id'],
        'metadata[plan]': plan,
        'subscription_data[metadata][agency_id]': a['id'],
        'subscription_data[metadata][plan]': plan,
        'allow_promotion_codes': 'true',
        'success_url': app + '/plan?pago=ok',
        'cancel_url': app + '/plan?pago=cancelado',
    }
    if customer:
        params['customer'] = customer
    else:
        params['customer_email'] = dict(user)['email']
    url = _post('/checkout/sessions', params).get('url')
    if not url:
        raise BillingError('Stripe no devolvió la dirección de pago', 'sin_url')
    return url


def portal_url(agency):
    """Stripe Billing Portal session (update card, change plan, cancel) -> URL. Needs a stored customer."""
    customer = dict(agency).get('stripe_customer_id')
    if not customer:
        raise BillingError('Todavía no tienes un pago activo', 'sin_cliente')
    url = _post('/billing_portal/sessions', {'customer': customer, 'return_url': db.origin('app') + '/plan'}).get('url')
    if not url:
        raise BillingError('Stripe no devolvió la dirección del portal', 'sin_url')
    return url


# ---------- webhook ----------
def verify_signature(raw, header, secret, now=None, tolerance=TOLERANCE):
    """Stripe-Signature: `t=<unix>,v1=<hex>[,v1=<hex>...]`; v1 = HMAC-SHA256("<t>.<raw body>", webhook secret).
    Constant-time compare; also rejects a timestamp more than `tolerance` seconds from now (replay window)."""
    if not secret:
        raise BillingError('El webhook de Stripe no está configurado', 'no_configurado')
    ts, sigs = None, []
    for part in (header or '').split(','):
        k, _, v = part.strip().partition('=')
        if k == 't':
            ts = v
        elif k == 'v1' and v:
            sigs.append(v)
    if not re.fullmatch(r'[0-9]{1,12}', ts or ''):
        raise BadSignature('Firma inválida', 'firma_invalida')
    t = int(ts)
    expected = hmac.new(secret.encode('utf-8'), ts.encode('ascii') + b'.' + raw, hashlib.sha256).hexdigest().encode('ascii')
    ok = False
    for sig in sigs:  # no early exit: keep the work constant whichever signature matches
        ok = hmac.compare_digest(expected, sig.encode('utf-8', 'replace')) or ok
    if not ok:
        raise BadSignature('Firma inválida', 'firma_invalida')
    if abs((time.time() if now is None else now) - t) > tolerance:
        raise BadSignature('Firma vencida', 'firma_vencida')


def handle_event(con, raw_body, sig_header, now=None):
    """Verify, then apply one Stripe event. Raises BadSignature / BillingError (the server answers 400 / 503).
    -> {'status': 'handled' | 'duplicate' | 'ignored', 'outcome': str}. Idempotent per event id (table stripe_events);
    the event row and every change it causes are committed together, so a failure rolls back and Stripe's retry works."""
    raw = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode('utf-8')
    verify_signature(raw, sig_header, settings()['STRIPE_WEBHOOK_SECRET'], now)
    try:
        ev = json.loads(raw.decode('utf-8'))
        eid, etype, obj = ev['id'], ev['type'], ev['data']['object']
        if not (isinstance(eid, str) and isinstance(etype, str) and isinstance(obj, dict)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BillingError('Evento inválido', 'json_invalido') from None
    if etype not in HANDLED_EVENTS:
        return {'status': 'ignored', 'outcome': 'tipo:' + etype}
    try:
        if not con.in_transaction:
            con.execute('BEGIN IMMEDIATE')  # take the write lock first: two deliveries of one event can't both apply
        if con.execute('INSERT OR IGNORE INTO stripe_events(event_id, type) VALUES (?,?)', (eid, etype)).rowcount == 0:
            con.rollback()
            return {'status': 'duplicate', 'outcome': 'repetido'}
        if etype == 'checkout.session.completed':
            outcome = _checkout_completed(con, obj, eid)
        else:
            outcome = _subscription_event(con, obj, eid, etype)
        con.execute('UPDATE stripe_events SET outcome=? WHERE event_id=?', (outcome, eid))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {'status': 'handled', 'outcome': outcome}


def _id(x):
    return x if isinstance(x, str) else ((x or {}).get('id') if isinstance(x, dict) else None)


def _agency_by(con, column, value):
    if not value:
        return None
    assert column in ('id', 'stripe_customer_id', 'stripe_subscription_id')
    if column == 'id':
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
    return con.execute('SELECT * FROM agencies WHERE %s=?' % column, (value,)).fetchone()


def _plan_for_price(price_id):
    s = settings()
    return {s['STRIPE_PRICE_PRO']: 'pro', s['STRIPE_PRICE_IA']: 'ia'}.get(price_id) if price_id else None


def _plan_of_subscription(sub):
    for it in ((sub.get('items') or {}).get('data')) or []:
        plan = _plan_for_price(((it.get('price') or {}).get('id')) or ((it.get('plan') or {}).get('id')))
        if plan:
            return plan
    return None


def _checkout_completed(con, obj, eid):
    if obj.get('mode') != 'subscription':
        return 'ignorado:modo'
    md = obj.get('metadata') or {}
    customer, sub = _id(obj.get('customer')), _id(obj.get('subscription'))
    ag = (_agency_by(con, 'id', obj.get('client_reference_id') or md.get('agency_id'))
          or _agency_by(con, 'stripe_customer_id', customer))
    if not ag:
        db.audit(con, 'stripe', 'stripe_event_unmatched', '%s checkout without a known agency (ref=%s)' % (eid, obj.get('client_reference_id')))
        return 'sin_agencia'
    plan = md.get('plan')
    if plan not in PAID_PLANS:
        db.audit(con, 'stripe', 'stripe_event_unmatched', '%s agency:%d checkout with plan=%r' % (eid, ag['id'], plan))
        return 'plan_invalido'
    prev_sub = ag['stripe_subscription_id']
    paid = obj.get('payment_status') in ('paid', 'no_payment_required')  # no_payment_required = 100% promo code
    con.execute('UPDATE agencies SET stripe_customer_id=COALESCE(?, stripe_customer_id), '
                'stripe_subscription_id=COALESCE(?, stripe_subscription_id)%s WHERE id=?' % (', plan=?' if paid else ''),
                (customer or None, sub or None) + ((plan,) if paid else ()) + (ag['id'],))
    if not paid:  # async payment still pending: ids are saved, the plan waits for the subscription to turn active
        db.audit(con, 'stripe', 'stripe_checkout_unpaid', '%s agency:%d payment_status=%s' % (eid, ag['id'], obj.get('payment_status')))
        return 'sin_pago'
    if prev_sub and sub and prev_sub != sub:
        db.audit(con, 'stripe', 'stripe_duplicate_subscription',
                 'agency:%d now pays %s and still had %s: cancel one in Stripe' % (ag['id'], sub, prev_sub))
    db.audit(con, 'stripe', 'plan_change_paid', 'agency:%d %s -> %s (checkout.session.completed %s)' % (ag['id'], db.plan_of(ag), plan, eid))
    return 'plan:' + plan


def _subscription_event(con, obj, eid, etype):
    # Only a subscription we already linked at checkout can change a plan. An out-of-order or stale event
    # (e.g. an old "active" arriving after a cancellation) must never re-grant a paid plan.
    ag = _agency_by(con, 'stripe_subscription_id', obj.get('id'))
    if not ag:
        return 'sin_vincular'
    status = obj.get('status')
    old = db.plan_of(ag)
    if etype == 'customer.subscription.deleted' or status in ENDED_STATUSES:
        con.execute("UPDATE agencies SET plan='gratis', stripe_subscription_id=NULL WHERE id=?", (ag['id'],))
        db.audit(con, 'stripe', 'plan_change_downgrade', 'agency:%d %s -> gratis (%s %s status=%s)' % (ag['id'], old, etype, eid, status))
        return 'plan:gratis'
    if status in ACTIVE_STATUSES:
        plan = _plan_of_subscription(obj)
        if not plan:
            db.audit(con, 'stripe', 'stripe_event_unmatched', '%s agency:%d subscription with an unknown price' % (eid, ag['id']))
            return 'precio_desconocido'
        if plan == old:
            return 'sin_cambio'
        con.execute('UPDATE agencies SET plan=? WHERE id=?', (plan, ag['id']))
        db.audit(con, 'stripe', 'plan_change_paid', 'agency:%d %s -> %s (%s %s)' % (ag['id'], old, plan, etype, eid))
        return 'plan:' + plan
    return 'sin_cambio:' + str(status)  # past_due / incomplete / paused: Stripe is still retrying, keep the plan
