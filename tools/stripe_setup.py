#!/usr/bin/env python3
"""Sets up Ficha Única's Stripe objects for the mode of the key in stripe.env, so the owner only has to paste one key.
Dry run unless --go. Creates what is missing: 2 products (SaaS tax code), their MXN monthly prices (tax included), the webhook,
the Customer Portal. Writes new price ids and the webhook secret into the stripe.env file. Never prints a secret. Safe to run twice.
Usage: python3 tools/stripe_setup.py            (says what it would do; read-only)
       python3 tools/stripe_setup.py --go       (does it)
A live key is refused unless LLAVE_STRIPE_LIVE=1, like the rest of the app."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import billing, db  # noqa: E402

TAX_CODE = 'txcd_10103001'  # Software as a service, business use: the agents use it for work
PLANS = (('pro', 'STRIPE_PRICE_PRO', 'Ficha Única Pro', 49900), ('ia', 'STRIPE_PRICE_IA', 'Ficha Única Pro + IA', 99900))


def _get(path, params=None):
    """Read from Stripe -> parsed JSON. Raises BillingError, never carrying the key. `billing._post` does the writes."""
    key = billing._usable_key()
    if not key:
        raise billing.BillingError('Stripe no está configurado', 'no_configurado')
    url = billing.API + path + ('?' + urllib.parse.urlencode(params) if params else '')
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key, 'Stripe-Version': billing.STRIPE_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=billing.TIMEOUT) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as ex:
        raise billing.BillingError('Stripe respondió HTTP %d en %s' % (ex.code, path.split('?')[0]), 'http_%d' % ex.code, ex.code) from None
    except (urllib.error.URLError, OSError):
        raise billing.BillingError('No se pudo contactar a Stripe', 'red') from None


def write_settings(new, path=None):
    """Sets KEY=value lines in the stripe.env file, keeping everything else. Atomic, mode 600."""
    path = path or os.environ.get('LLAVE_STRIPE_ENV_FILE') or billing.ENV_FILE
    try:
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    left = dict(new)
    out = []
    for line in lines:
        k = line.split('=', 1)[0].strip()
        if k in left and not line.lstrip().startswith('#'):
            out.append('%s=%s' % (k, left.pop(k)))
        else:
            out.append(line)
    out += ['%s=%s' % kv for kv in left.items()]
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')
    os.replace(tmp, path)


def _product(name, go, say):
    for p in _get('/products', {'active': 'true', 'limit': 100})['data']:
        if p['name'] == name:
            if p.get('tax_code') != TAX_CODE:
                say('%s: fix the tax code' % name)
                if go:
                    p = billing._post('/products/' + p['id'], {'tax_code': TAX_CODE})
            else:
                say('%s: product ok' % name)
            return p
    say('%s: create the product' % name)
    return billing._post('/products', {'name': name, 'tax_code': TAX_CODE}) if go else None


def _price(product, name, cents, go, say):
    if product:
        for p in _get('/prices', {'product': product['id'], 'active': 'true', 'limit': 100})['data']:
            if p['unit_amount'] == cents and p['currency'] == 'mxn' and (p.get('recurring') or {}).get('interval') == 'month':
                if p.get('tax_behavior') == 'unspecified':
                    say('%s: price must include tax' % name)
                    if go:
                        p = billing._post('/prices/' + p['id'], {'tax_behavior': 'inclusive'})
                elif p.get('tax_behavior') == 'exclusive':
                    say('%s: ⚠️ price adds tax on top. Stripe can\'t change that: fix it by hand' % name)
                else:
                    say('%s: price ok' % name)
                return p
    say('%s: create the MXN %d monthly price, tax included' % (name, cents // 100))
    if go and product:
        return billing._post('/prices', {'product': product['id'], 'unit_amount': cents, 'currency': 'mxn', 'recurring[interval]': 'month', 'tax_behavior': 'inclusive'})
    return None


def _webhook(go, say, changes):
    url = db.origin('app') + '/stripe/webhook'
    for h in _get('/webhook_endpoints', {'limit': 100})['data']:
        if h['url'] == url:
            say('webhook ok' if set(billing.HANDLED_EVENTS) <= set(h['enabled_events']) else '⚠️ webhook is missing events: fix it by hand')
            return
    say('create the webhook')
    if go:
        params = {'url': url}
        for i, ev in enumerate(billing.HANDLED_EVENTS):
            params['enabled_events[%d]' % i] = ev
        changes['STRIPE_WEBHOOK_SECRET'] = billing._post('/webhook_endpoints', params)['secret']


def _portal(prices, go, say):
    if _get('/billing_portal/configurations', {'active': 'true', 'limit': 3})['data']:
        say('customer portal ok')
        return
    say('create the customer portal')
    if go and all(prices):
        params = {'business_profile[headline]': 'Ficha Única', 'default_return_url': db.origin('app') + '/plan',
                  'features[payment_method_update][enabled]': 'true', 'features[invoice_history][enabled]': 'true',
                  'features[subscription_cancel][enabled]': 'true', 'features[subscription_cancel][mode]': 'at_period_end',
                  'features[subscription_update][enabled]': 'true', 'features[subscription_update][default_allowed_updates][0]': 'price'}
        for i, p in enumerate(prices):
            params['features[subscription_update][products][%d][product]' % i] = p['product']
            params['features[subscription_update][products][%d][prices][0]' % i] = p['id']
        billing._post('/billing_portal/configurations', params)


def main(args, say=print):
    go = '--go' in args
    s = billing.settings()
    if not billing._usable_key(s):
        say('No hay llave usable en stripe.env (una llave live necesita LLAVE_STRIPE_LIVE=1). No hice nada.')
        return 2
    say('%s, %s' % ('MODO ' + billing.key_mode(s['STRIPE_SECRET_KEY']).upper(), 'haciendo los cambios' if go else 'solo revisando'))
    changes, prices = {}, []
    for _, setting, name, cents in PLANS:
        price = _price(_product(name, go, say), name, cents, go, say)
        prices.append(price)
        if price and price['id'] != s[setting]:
            say('%s: stripe.env needs this price id' % name)
            changes[setting] = price['id']
    _webhook(go, say, changes)
    _portal(prices, go, say)
    if not s['STRIPE_WEBHOOK_SECRET'] and 'STRIPE_WEBHOOK_SECRET' not in changes:
        say('⚠️ falta STRIPE_WEBHOOK_SECRET: revélalo en el panel de Stripe y ponlo en stripe.env')
    if go and changes:
        write_settings(changes)
        say('stripe.env actualizado: %s' % ', '.join(sorted(changes)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
