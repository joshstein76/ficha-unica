"""Stripe billing (llave/billing.py): settings + safety, Checkout/Portal params, webhook signature, events, and the plan screens.
No network: `billing._post` and `urllib.request.urlopen` are always patched; the keys here are fakes."""
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import billing, db  # noqa: E402
from llave.web import server  # noqa: E402
from llave.web.server import Handler  # noqa: E402

# A developer's real config/stripe.env or shell variables must never change what the rest of the suite sees.
for _k in billing.SETTING_KEYS + ('LLAVE_STRIPE_LIVE',):
    os.environ.pop(_k, None)
os.environ['LLAVE_STRIPE_ENV_FILE'] = os.path.join(tempfile.mkdtemp(), 'no-stripe.env')

TMP = tempfile.mkdtemp()
PORT = 8710
HOST = 'app.fichaunica.localhost'
TEST_KEY = 'sk_test_FAKEFAKE'
LIVE_KEY = 'sk_' + 'live_FAKEFAKE'          # built in two parts so the repo secret scan never sees a live-looking literal
WHSEC = 'whsec_FAKEFAKE'
FULL = {'STRIPE_SECRET_KEY': TEST_KEY, 'STRIPE_WEBHOOK_SECRET': WHSEC, 'STRIPE_PRICE_PRO': 'price_pro_x', 'STRIPE_PRICE_IA': 'price_ia_x'}
EMPTY = {k: '' for k in FULL}


def conf(**kw):
    d = dict(FULL)
    d.update(kw)
    return mock.patch.object(billing, 'settings', lambda: dict(d))


def sign(raw, secret=WHSEC, t=None):
    t = int(time.time()) if t is None else t
    return 't=%d,v1=%s' % (t, hmac.new(secret.encode(), b'%d.' % t + raw, hashlib.sha256).hexdigest())


def event(eid, etype, obj):
    return json.dumps({'id': eid, 'object': 'event', 'type': etype, 'data': {'object': obj}}).encode()


def checkout_event(eid, agency_id, plan='pro', cust='cus_1', sub='sub_1', **extra):
    obj = {'object': 'checkout.session', 'mode': 'subscription', 'payment_status': 'paid', 'client_reference_id': str(agency_id),
           'customer': cust, 'subscription': sub, 'metadata': {'agency_id': str(agency_id), 'plan': plan}}
    obj.update(extra)
    return event(eid, 'checkout.session.completed', obj)


def sub_obj(sub='sub_1', status='active', price='price_pro_x'):
    return {'object': 'subscription', 'id': sub, 'status': status, 'customer': 'cus_1', 'items': {'data': [{'price': {'id': price}}]}}


def memory_db():
    con = db.connect(':memory:')
    db.init(con)
    return con


def add_agency(con, slug='casa', plan='gratis'):
    aid = con.execute('INSERT INTO agencies(slug, name, email, plan) VALUES (?,?,?,?)', (slug, 'Casa ' + slug, slug + '@ejemplo.test', plan)).lastrowid
    uid = con.execute('INSERT INTO users(agency_id, name, email, password_hash) VALUES (?,?,?,?)', (aid, 'Ana', slug + '-u@ejemplo.test', 'x')).lastrowid
    con.commit()
    return aid, uid


def plan_of(con, aid):
    return con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0]


def actions(con, action):
    return con.execute('SELECT COUNT(*) FROM audit WHERE action=?', (action,)).fetchone()[0]


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SettingsAndSafety(unittest.TestCase):
    def test_disabled_by_default_and_needs_key_and_both_prices(self):
        with conf(**EMPTY):
            self.assertFalse(billing.enabled())
            self.assertEqual(billing.config_problems(), [])      # nothing configured = nothing to complain about
        with conf():
            self.assertTrue(billing.enabled())
            self.assertEqual(billing.config_problems(), [])
        for missing in ('STRIPE_SECRET_KEY', 'STRIPE_PRICE_PRO', 'STRIPE_PRICE_IA'):
            with conf(**{missing: ''}):
                self.assertFalse(billing.enabled(), missing)
        with conf(STRIPE_SECRET_KEY='pk_test_FAKEFAKE'):         # a publishable key is not a secret key
            self.assertFalse(billing.enabled())

    def test_live_key_refused_without_explicit_yes(self):
        with conf(STRIPE_SECRET_KEY=LIVE_KEY), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LLAVE_STRIPE_LIVE', None)
            self.assertFalse(billing.enabled())
            self.assertTrue(any('LLAVE_STRIPE_LIVE=1' in p for p in billing.config_problems()))
            with mock.patch('urllib.request.urlopen', side_effect=AssertionError('network touched')):
                with self.assertRaises(billing.BillingError) as cm:
                    billing._post('/checkout/sessions', {'mode': 'subscription'})
            self.assertEqual(cm.exception.code, 'no_configurado')
            self.assertNotIn(LIVE_KEY, str(cm.exception))
            with mock.patch.dict(os.environ, {'LLAVE_STRIPE_LIVE': '1'}):
                self.assertTrue(billing.enabled())
                self.assertEqual(billing.config_problems(), [])
            with mock.patch.dict(os.environ, {'LLAVE_STRIPE_LIVE': 'yes'}):   # only the exact "1" counts
                self.assertFalse(billing.enabled())

    def test_half_configured_is_reported(self):
        with conf(STRIPE_PRICE_IA='', STRIPE_WEBHOOK_SECRET=''):
            problems = ' '.join(billing.config_problems())
            self.assertIn('STRIPE_PRICE_IA', problems)
            self.assertIn('STRIPE_WEBHOOK_SECRET', problems)
        with conf(STRIPE_PRICE_PRO='prod_123'):                  # product id pasted instead of price id
            self.assertIn('price id', ' '.join(billing.config_problems()))

    def test_settings_from_file_with_env_override(self):
        path = os.path.join(TMP, 'stripe.env')
        with open(path, 'w') as fh:
            fh.write('# comment\nSTRIPE_SECRET_KEY="%s"\nSTRIPE_PRICE_PRO=price_file_pro\nSTRIPE_PRICE_IA = price_file_ia\n\nSTRIPE_WEBHOOK_SECRET=\n' % TEST_KEY)
        with mock.patch.dict(os.environ, {'LLAVE_STRIPE_ENV_FILE': path, 'STRIPE_PRICE_PRO': 'price_env_pro'}):
            s = billing.settings()
            self.assertEqual((s['STRIPE_SECRET_KEY'], s['STRIPE_PRICE_IA'], s['STRIPE_WEBHOOK_SECRET']), (TEST_KEY, 'price_file_ia', ''))
            self.assertEqual(s['STRIPE_PRICE_PRO'], 'price_env_pro')   # real env wins over the file
            self.assertTrue(billing.enabled())
        self.assertFalse(billing.enabled())                          # the isolated empty file again

    def test_post_request_shape_and_error_scrubbing(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen.update(req=req, timeout=timeout)
            return FakeResponse(b'{"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}')

        with conf(), mock.patch('urllib.request.urlopen', fake_urlopen):
            out = billing._post('/checkout/sessions', {'mode': 'subscription', 'line_items[0][quantity]': 1, 'skipped': None}, idem_key='k-1')
        req = seen['req']
        h = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(out['id'], 'cs_1')
        self.assertEqual(req.full_url, 'https://api.stripe.com/v1/checkout/sessions')
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(seen['timeout'], 20)
        self.assertEqual(h['authorization'], 'Bearer ' + TEST_KEY)
        self.assertEqual(h['stripe-version'], billing.STRIPE_VERSION)
        self.assertEqual(h['idempotency-key'], 'k-1')
        self.assertEqual(h['content-type'], 'application/x-www-form-urlencoded')
        self.assertEqual(urllib.parse.parse_qs(req.data.decode()), {'mode': ['subscription'], 'line_items[0][quantity]': ['1']})

        def stripe_says_no(req, timeout=None):
            body = json.dumps({'error': {'type': 'invalid_request_error', 'code': 'api_key_invalid',
                                         'message': 'Invalid API Key provided: ' + TEST_KEY}}).encode()
            raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, __import__('io').BytesIO(body))

        with conf(), mock.patch('urllib.request.urlopen', stripe_says_no):
            with self.assertRaises(billing.BillingError) as cm:
                billing._post('/checkout/sessions', {})
        self.assertEqual((cm.exception.status, cm.exception.code), (401, 'api_key_invalid'))
        self.assertNotIn(TEST_KEY, str(cm.exception))

        def down(req, timeout=None):
            raise urllib.error.URLError('unreachable ' + TEST_KEY)

        with conf(), mock.patch('urllib.request.urlopen', down):
            with self.assertRaises(billing.BillingError) as cm:
                billing._post('/checkout/sessions', {})
        self.assertEqual(cm.exception.code, 'red')
        self.assertNotIn(TEST_KEY, str(cm.exception))
        self.assertNotIn(TEST_KEY, repr(cm.exception.__cause__))   # `from None`: the original error is not chained


class CheckoutAndPortal(unittest.TestCase):
    def setUp(self):
        self.con = memory_db()
        self.aid, self.uid = add_agency(self.con)
        self.calls = []

        def fake_post(path, params, idem_key=None):
            self.calls.append((path, params))
            return {'url': 'https://pay.stripe.test/' + path.strip('/').replace('/', '-')}

        self.patches = [conf(), mock.patch.object(billing, '_post', fake_post)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.con.close()

    def rows(self):
        return (self.con.execute('SELECT * FROM agencies WHERE id=?', (self.aid,)).fetchone(),
                self.con.execute('SELECT * FROM users WHERE id=?', (self.uid,)).fetchone())

    def test_checkout_params_per_plan(self):
        a, u = self.rows()
        app = db.origin('app')
        for plan, price in (('pro', 'price_pro_x'), ('ia', 'price_ia_x')):
            self.calls.clear()
            url = billing.checkout_url(self.con, a, u, plan)
            self.assertEqual(url, 'https://pay.stripe.test/checkout-sessions')
            (path, p), = self.calls
            self.assertEqual(path, '/checkout/sessions')
            self.assertEqual(p['mode'], 'subscription')
            self.assertEqual((p['line_items[0][price]'], p['line_items[0][quantity]']), (price, 1))
            self.assertEqual(p['locale'], 'es')
            self.assertEqual(p['client_reference_id'], self.aid)
            self.assertEqual((p['metadata[agency_id]'], p['metadata[plan]']), (self.aid, plan))
            self.assertEqual((p['subscription_data[metadata][agency_id]'], p['subscription_data[metadata][plan]']), (self.aid, plan))
            self.assertEqual(p['customer_email'], 'casa-u@ejemplo.test')
            self.assertNotIn('customer', p)
            self.assertEqual(p['allow_promotion_codes'], 'true')
            self.assertEqual(p['success_url'], app + '/plan?pago=ok')
            self.assertEqual(p['cancel_url'], app + '/plan?pago=cancelado')

    def test_checkout_reuses_the_stored_customer(self):
        self.con.execute("UPDATE agencies SET stripe_customer_id='cus_known' WHERE id=?", (self.aid,))
        self.con.commit()
        a, u = self.rows()
        stale = dict(a, stripe_customer_id=None)                 # the passed row may be stale: the database wins
        billing.checkout_url(self.con, stale, u, 'ia')
        p = self.calls[0][1]
        self.assertEqual(p['customer'], 'cus_known')
        self.assertNotIn('customer_email', p)

    def test_checkout_rejects_free_and_unknown_plans(self):
        a, u = self.rows()
        for plan in ('gratis', 'agencia', ''):
            with self.assertRaises(billing.BillingError):
                billing.checkout_url(self.con, a, u, plan)
        self.assertEqual(self.calls, [])

    def test_portal_params(self):
        a, _ = self.rows()
        with self.assertRaises(billing.BillingError) as cm:
            billing.portal_url(a)
        self.assertEqual(cm.exception.code, 'sin_cliente')
        self.assertEqual(self.calls, [])
        self.assertEqual(billing.portal_url(dict(a, stripe_customer_id='cus_9')), 'https://pay.stripe.test/billing_portal-sessions')
        path, p = self.calls[0]
        self.assertEqual(path, '/billing_portal/sessions')
        self.assertEqual(p, {'customer': 'cus_9', 'return_url': db.origin('app') + '/plan'})


class WebhookSignature(unittest.TestCase):
    def setUp(self):
        self.con = memory_db()
        self.aid, _ = add_agency(self.con)
        self.raw = checkout_event('evt_sig', self.aid)

    def test_valid_signature_applies_the_event(self):
        with conf():
            res = billing.handle_event(self.con, self.raw, sign(self.raw))
        self.assertEqual(res['status'], 'handled')
        self.assertEqual(plan_of(self.con, self.aid), 'pro')

    def test_rotating_secret_header_with_two_v1_values(self):
        t, good = sign(self.raw).split(',v1=')
        with conf():
            res = billing.handle_event(self.con, self.raw, '%s,v1=%s,v1=%s,v0=old' % (t, '0' * 64, good))   # one old, one current
        self.assertEqual(res['status'], 'handled')

    def test_bad_signatures_change_nothing(self):
        other = event('evt_sig', 'checkout.session.completed', {'client_reference_id': str(self.aid)})
        t = int(time.time())
        cases = {
            'wrong secret': sign(self.raw, 'whsec_OTHER'),
            'tampered body': sign(other),
            'no header': '',
            'garbage': 'hello',
            'no v1': 't=%d' % t,
            'no t': 'v1=' + 'a' * 64,
            'non-digit t': 't=12x,v1=' + 'a' * 64,
            'unicode digits': 't=１２,v1=' + 'a' * 64,
        }
        with conf():
            for name, hdr in cases.items():
                with self.assertRaises(billing.BadSignature, msg=name) as cm:
                    billing.handle_event(self.con, self.raw, hdr)
                self.assertEqual(cm.exception.code, 'firma_invalida', name)
        self.assertEqual(plan_of(self.con, self.aid), 'gratis')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM stripe_events').fetchone()[0], 0)

    def test_stale_and_future_timestamps_are_rejected(self):
        now = 1_800_000_000
        with conf():
            for t in (now - 301, now + 301):
                with self.assertRaises(billing.BadSignature) as cm:
                    billing.handle_event(self.con, self.raw, sign(self.raw, t=t), now=now)
                self.assertEqual(cm.exception.code, 'firma_vencida')
            self.assertEqual(plan_of(self.con, self.aid), 'gratis')
            self.assertEqual(billing.handle_event(self.con, self.raw, sign(self.raw, t=now - 299), now=now)['status'], 'handled')

    def test_no_webhook_secret_means_not_configured(self):
        with conf(STRIPE_WEBHOOK_SECRET=''):
            with self.assertRaises(billing.BillingError) as cm:
                billing.handle_event(self.con, self.raw, sign(self.raw, ''))
        self.assertEqual(cm.exception.code, 'no_configurado')
        self.assertNotIsInstance(cm.exception, billing.BadSignature)
        self.assertEqual(plan_of(self.con, self.aid), 'gratis')

    def test_signed_but_not_json_or_wrong_shape(self):
        with conf():
            for raw in (b'not json', b'[]', b'{"id": 1, "type": "x", "data": {"object": {}}}', b'{"id": "e", "type": "checkout.session.completed"}'):
                with self.assertRaises(billing.BillingError) as cm:
                    billing.handle_event(self.con, raw, sign(raw))
                self.assertEqual(cm.exception.code, 'json_invalido', raw)


class WebhookEvents(unittest.TestCase):
    def setUp(self):
        self.con = memory_db()
        self.aid, _ = add_agency(self.con)
        self.p = conf()
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.con.close()

    def feed(self, raw):
        return billing.handle_event(self.con, raw, sign(raw))

    def agency(self):
        return self.con.execute('SELECT * FROM agencies WHERE id=?', (self.aid,)).fetchone()

    def test_checkout_completed_upgrades_and_stores_ids(self):
        res = self.feed(checkout_event('evt_1', self.aid, 'ia', 'cus_77', 'sub_77'))
        self.assertEqual(res, {'status': 'handled', 'outcome': 'plan:ia'})
        a = self.agency()
        self.assertEqual((a['plan'], a['stripe_customer_id'], a['stripe_subscription_id']), ('ia', 'cus_77', 'sub_77'))
        self.assertEqual(actions(self.con, 'plan_change_paid'), 1)
        detail = self.con.execute("SELECT actor, detail FROM audit WHERE action='plan_change_paid'").fetchone()
        self.assertEqual(detail['actor'], 'stripe')
        self.assertIn('gratis -> ia', detail['detail'])
        self.assertTrue(billing.is_paying(a))

    def test_agency_found_by_metadata_or_known_customer(self):
        self.feed(event('evt_m', 'checkout.session.completed', {'mode': 'subscription', 'payment_status': 'paid', 'customer': 'cus_m',
                                                                 'subscription': 'sub_m', 'metadata': {'agency_id': str(self.aid), 'plan': 'pro'}}))
        self.assertEqual(self.agency()['plan'], 'pro')
        self.con.execute("UPDATE agencies SET plan='gratis' WHERE id=?", (self.aid,))
        self.con.commit()
        self.feed(event('evt_c', 'checkout.session.completed', {'mode': 'subscription', 'payment_status': 'paid', 'customer': 'cus_m',
                                                                 'subscription': 'sub_n', 'metadata': {'plan': 'ia'}}))
        self.assertEqual((self.agency()['plan'], self.agency()['stripe_subscription_id']), ('ia', 'sub_n'))

    def test_replayed_event_is_a_noop(self):
        raw = checkout_event('evt_dup', self.aid)
        self.assertEqual(self.feed(raw)['status'], 'handled')
        self.con.execute("UPDATE agencies SET plan='gratis', stripe_subscription_id=NULL WHERE id=?", (self.aid,))  # state moved on
        self.con.commit()
        self.assertEqual(self.feed(raw)['status'], 'duplicate')
        self.assertEqual(self.agency()['plan'], 'gratis')
        self.assertEqual(actions(self.con, 'plan_change_paid'), 1)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM stripe_events').fetchone()[0], 1)

    def test_subscription_deleted_downgrades_and_keeps_listings(self):
        self.feed(checkout_event('evt_1', self.aid, 'ia'))
        for i in range(8):
            self.con.execute("INSERT INTO listings(agency_id, ref, slug, title, colonia, municipio, estado) VALUES (?,?,?,?,?,?,?)",
                             (self.aid, 'P-%d' % i, 'p-%d' % i, 'Propiedad %d' % i, 'Roma', 'Cuauhtémoc', 'CDMX'))
        self.con.commit()
        res = self.feed(event('evt_2', 'customer.subscription.deleted', sub_obj(status='canceled')))
        self.assertEqual(res['outcome'], 'plan:gratis')
        a = self.agency()
        self.assertEqual((a['plan'], a['stripe_subscription_id'], a['stripe_customer_id']), ('gratis', None, 'cus_1'))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=?', (self.aid,)).fetchone()[0], 8)
        self.assertEqual(actions(self.con, 'plan_change_downgrade'), 1)
        self.assertFalse(billing.is_paying(a))
        # Stripe also sends subscription.updated(canceled) for the same cancellation: nothing left to change, no noise
        self.assertEqual(self.feed(event('evt_3', 'customer.subscription.updated', sub_obj(status='canceled')))['outcome'], 'sin_vincular')
        self.assertEqual(actions(self.con, 'plan_change_downgrade'), 1)

    def test_subscription_updated_maps_price_and_status(self):
        self.feed(checkout_event('evt_1', self.aid, 'pro'))
        up = self.feed(event('evt_up', 'customer.subscription.updated', sub_obj(price='price_ia_x')))
        self.assertEqual((up['outcome'], self.agency()['plan']), ('plan:ia', 'ia'))
        self.assertEqual(self.feed(event('evt_same', 'customer.subscription.updated', sub_obj(price='price_ia_x')))['outcome'], 'sin_cambio')
        down = self.feed(event('evt_dn', 'customer.subscription.updated', sub_obj(status='trialing', price='price_pro_x')))
        self.assertEqual((down['outcome'], self.agency()['plan']), ('plan:pro', 'pro'))
        for i, status in enumerate(('past_due', 'incomplete', 'paused')):   # Stripe still retrying: keep the plan
            self.feed(event('evt_s%d' % i, 'customer.subscription.updated', sub_obj(status=status)))
            self.assertEqual(self.agency()['plan'], 'pro', status)
        self.feed(event('evt_unknown', 'customer.subscription.updated', sub_obj(price='price_other')))
        self.assertEqual(self.agency()['plan'], 'pro')
        self.assertEqual(actions(self.con, 'stripe_event_unmatched'), 1)
        for i, status in enumerate(('unpaid', 'incomplete_expired')):
            self.feed(checkout_event('evt_re%d' % i, self.aid, 'pro'))
            self.feed(event('evt_end%d' % i, 'customer.subscription.updated', sub_obj(status=status)))
            self.assertEqual(self.agency()['plan'], 'gratis', status)

    def test_old_subscription_events_never_touch_the_new_one(self):
        self.feed(checkout_event('evt_a', self.aid, 'pro', sub='sub_A'))
        self.feed(event('evt_a_del', 'customer.subscription.deleted', sub_obj('sub_A', 'canceled')))
        self.feed(checkout_event('evt_b', self.aid, 'ia', sub='sub_B'))
        self.feed(event('evt_a_late', 'customer.subscription.deleted', sub_obj('sub_A', 'canceled')))     # arrives late
        self.feed(event('evt_a_active', 'customer.subscription.updated', sub_obj('sub_A', 'active')))    # a stale "active" too
        a = self.agency()
        self.assertEqual((a['plan'], a['stripe_subscription_id']), ('ia', 'sub_B'))

    def test_cancelled_agent_cannot_be_regranted_by_a_late_active_event(self):
        self.feed(checkout_event('evt_a', self.aid, 'pro', sub='sub_A'))
        self.feed(event('evt_del', 'customer.subscription.deleted', sub_obj('sub_A', 'canceled')))
        self.feed(event('evt_late', 'customer.subscription.updated', sub_obj('sub_A', 'active')))
        self.assertEqual(self.agency()['plan'], 'gratis')

    def test_unpaid_checkout_saves_ids_but_not_the_plan(self):
        res = self.feed(checkout_event('evt_u', self.aid, 'pro', payment_status='unpaid'))
        self.assertEqual(res['outcome'], 'sin_pago')
        a = self.agency()
        self.assertEqual((a['plan'], a['stripe_subscription_id']), ('gratis', 'sub_1'))
        self.assertEqual(actions(self.con, 'plan_change_paid'), 0)
        self.assertEqual(actions(self.con, 'stripe_checkout_unpaid'), 1)
        self.assertEqual(self.feed(checkout_event('evt_p', self.aid, 'pro', payment_status='no_payment_required'))['outcome'], 'plan:pro')

    def test_unmatched_or_odd_checkouts_are_acknowledged_not_applied(self):
        self.assertEqual(self.feed(checkout_event('evt_x', 99999))['outcome'], 'sin_agencia')
        self.assertEqual(self.feed(checkout_event('evt_y', self.aid, 'agencia'))['outcome'], 'plan_invalido')
        self.assertEqual(self.feed(checkout_event('evt_z', self.aid, mode='payment'))['outcome'], 'ignorado:modo')
        self.assertEqual(self.agency()['plan'], 'gratis')
        self.assertEqual(actions(self.con, 'stripe_event_unmatched'), 2)

    def test_second_subscription_is_flagged(self):
        self.feed(checkout_event('evt_1', self.aid, 'pro', sub='sub_1'))
        self.feed(checkout_event('evt_2', self.aid, 'ia', sub='sub_2'))
        self.assertEqual(actions(self.con, 'stripe_duplicate_subscription'), 1)
        self.assertEqual(self.agency()['stripe_subscription_id'], 'sub_2')

    def test_other_event_types_are_ignored_and_not_recorded(self):
        raw = event('evt_inv', 'invoice.paid', {'id': 'in_1'})
        self.assertEqual(self.feed(raw)['status'], 'ignored')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM stripe_events').fetchone()[0], 0)

    def test_a_failure_rolls_everything_back_so_the_retry_works(self):
        raw = checkout_event('evt_boom', self.aid)
        with mock.patch.object(billing, '_checkout_completed', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.feed(raw)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM stripe_events').fetchone()[0], 0)
        self.assertEqual(self.feed(raw)['status'], 'handled')
        self.assertEqual(self.agency()['plan'], 'pro')

    def test_atomic_even_on_an_autocommit_connection(self):
        path = os.path.join(TMP, 'auto.db')
        con = db.connect(path)
        db.init(con)
        aid, _ = add_agency(con, 'auto')
        con.close()
        con = db.connect(path)
        con.isolation_level = None                                 # autocommit: no implicit transaction to lean on
        raw = checkout_event('evt_auto', aid)
        with mock.patch.object(billing, '_checkout_completed', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.feed_to(con, raw)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM stripe_events').fetchone()[0], 0)
        self.assertEqual(self.feed_to(con, raw)['status'], 'handled')
        self.assertEqual(plan_of(con, aid), 'pro')
        con.close()

    def feed_to(self, con, raw):
        return billing.handle_event(con, raw, sign(raw))

    def test_the_same_event_delivered_in_parallel_applies_once(self):
        path = os.path.join(TMP, 'race.db')
        con = db.connect(path)
        db.init(con)
        aid, _ = add_agency(con, 'race')
        con.close()
        raw = checkout_event('evt_race', aid, 'ia')
        results, errors = [], []

        def deliver():
            c = db.connect(path)
            try:
                results.append(self.feed_to(c, raw)['status'])
            except Exception as ex:  # noqa: BLE001
                errors.append(repr(ex))
            finally:
                c.close()

        threads = [threading.Thread(target=deliver) for _ in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), ['duplicate'] * 5 + ['handled'])
        con = db.connect(path)
        self.assertEqual((plan_of(con, aid), actions(con, 'plan_change_paid')), ('ia', 1))
        con.close()


def http(path, data=None, cookie=None, headers=None, host=HOST):
    h = {'Host': host}
    h.update(headers or {})
    if cookie:
        h['Cookie'] = cookie
    if isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        r = OPENER.open(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=data, headers=h))
        return r.status, r.read().decode('utf-8', 'replace'), r.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode('utf-8', 'replace'), ex.headers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class PlanScreensAndRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'billing.db'), os.path.join(TMP, 'media'), PORT
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def setUp(self):
        type(self).n += 1
        self.email = 'agente%d@ejemplo.test' % self.n
        s, _, h = http('/registro', {'name': 'Rosa Pérez', 'agency': 'Casa Rosa %d' % self.n, 'whatsapp': '55 7777 8888',
                                     'email': self.email, 'password': 'segura1234', 'terms': '1'})
        self.assertEqual(s, 303)
        self.cookie = h['Set-Cookie'].split(';')[0]
        _, body, _ = http('/perfil', cookie=self.cookie)
        self.csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)
        con = db.connect()
        self.aid = con.execute('SELECT agency_id FROM users WHERE email=?', (self.email,)).fetchone()[0]
        con.close()
        self.calls = []

        def fake_post(path, params, idem_key=None):
            self.calls.append((path, params))
            return {'url': 'https://pay.stripe.test/' + path.strip('/').replace('/', '-')}

        self.fake_post = fake_post

    def q(self, sql, *args):
        con = db.connect()
        try:
            return con.execute(sql, args).fetchone()
        finally:
            con.close()

    def plan(self):
        return self.q('SELECT plan FROM agencies WHERE id=?', self.aid)[0]

    def webhook(self, raw, header=None):
        return http('/stripe/webhook', raw, headers={'Stripe-Signature': header if header is not None else sign(raw),
                                                      'Content-Type': 'application/json'})

    def test_disabled_keeps_test_mode_exactly(self):
        with conf(**EMPTY):
            s, page, _ = http('/plan/pro', cookie=self.cookie)
            self.assertIn('MODO PRUEBA', page)
            self.assertIn('Confirmar cambio (prueba)', page)
            s, page, _ = http('/plan?pago=ok', cookie=self.cookie)
            self.assertNotIn('Gracias: tu plan se activa', page)
            self.assertIn('Precios en pesos mexicanos con IVA. Sin plazo forzoso', page)
            self.assertNotIn('Administrar mi pago', page)
            s, page, _ = http('/plan/pro', {'csrf': self.csrf}, self.cookie)
            self.assertIn('modo prueba, sin cobro', page)
            self.assertEqual(self.plan(), 'pro')
            self.assertEqual(self.q("SELECT COUNT(*) FROM audit WHERE action='plan_change_test_mode'")[0] >= 1, True)
            s, _, _ = http('/plan/portal', {'csrf': self.csrf}, self.cookie)
            self.assertEqual(s, 404)
            s, body, _ = self.webhook(b'{}')                       # no webhook secret = not configured
            self.assertEqual(s, 503)
        self.assertEqual(self.calls, [])

    def test_enabled_screens_say_pay_by_card_and_hide_the_test_notice(self):
        with conf():
            for path in ('/plan', '/plan/pro', '/plan/ia', '/plan/gratis'):
                s, page, _ = http(path, cookie=self.cookie)
                self.assertEqual(s, 200, path)
                self.assertNotIn('MODO PRUEBA', page, path)
                self.assertNotIn('(prueba)', page, path)
            s, page, _ = http('/plan/pro', cookie=self.cookie)
            self.assertIn('Pagar con tarjeta', page)
            self.assertIn('procesado por Stripe para Ciao Bella Marketing', page)
            self.assertIn('IVA incluido', page)
            self.assertIn('MXN', page)
            self.assertIn('Cancelas cuando quieras', page)
            self.assertIn('$499 MXN', page)
            s, page, _ = http('/plan/ia', cookie=self.cookie)
            self.assertIn('$999 MXN', page)
            s, page, _ = http('/plan', cookie=self.cookie)
            self.assertIn('procesado por Stripe para Ciao Bella Marketing', page)
            self.assertNotIn('Administrar mi pago', page)           # nothing to manage until they pay

    def test_pay_buttons_redirect_to_checkout_and_never_change_the_plan(self):
        with conf(), mock.patch.object(billing, '_post', self.fake_post):
            for key, price in (('pro', 'price_pro_x'), ('ia', 'price_ia_x')):
                self.calls.clear()
                s, _, h = http('/plan/' + key, {'csrf': self.csrf}, self.cookie)
                self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/checkout-sessions'))
                (path, p), = self.calls
                self.assertEqual((path, p['line_items[0][price]'], p['metadata[plan]'], p['client_reference_id']), ('/checkout/sessions', price, key, self.aid))
                self.assertEqual(p['customer_email'], self.email)
                self.assertEqual(self.plan(), 'gratis')              # only the signed webhook upgrades
            s, _, _ = http('/plan/pro', {'csrf': 'bad'}, self.cookie)
            self.assertEqual(s, 403)                                 # CSRF still enforced on the panel routes

    def test_return_banners(self):
        with conf():
            s, page, _ = http('/plan?pago=ok', cookie=self.cookie)
            self.assertIn('Gracias: tu plan se activa en unos segundos', page)
            s, page, _ = http('/plan?pago=cancelado', cookie=self.cookie)
            self.assertIn('No se hizo ningún cobro', page)
            self.assertNotIn('Gracias: tu plan se activa', page)
            s, page, _ = http('/plan', cookie=self.cookie)
            self.assertNotIn('Gracias', page)
            self.assertNotIn('No se hizo ningún cobro', page)

    def test_stripe_failure_shows_a_calm_error(self):
        def boom(path, params, idem_key=None):
            raise billing.BillingError('Invalid API Key provided', 'api_key_invalid', 401)

        with conf(), mock.patch.object(billing, '_post', boom):
            s, page, _ = http('/plan/pro', {'csrf': self.csrf}, self.cookie)
            self.assertEqual(s, 502)
            self.assertIn('No pudimos abrir el pago', page)
            self.assertNotIn('Invalid API Key', page)
        self.assertEqual(self.plan(), 'gratis')

    def test_paying_agent_manages_in_the_portal_and_cannot_buy_twice(self):
        raw = checkout_event('evt_http_%d' % self.n, self.aid, 'pro', 'cus_h%d' % self.n, 'sub_h%d' % self.n)
        with conf(), mock.patch.object(billing, '_post', self.fake_post):
            s, body, _ = self.webhook(raw)                           # no session, no CSRF: only the signature
            self.assertEqual((s, json.loads(body)), (200, {'ok': True, 'status': 'handled'}))
            self.assertEqual(self.plan(), 'pro')
            s, page, _ = http('/plan', cookie=self.cookie)
            self.assertIn('Administrar mi pago', page)
            s, page, _ = http('/plan/ia', cookie=self.cookie)
            self.assertIn('Administrar mi pago', page)
            self.assertNotIn('Pagar con tarjeta', page)
            for key in ('ia', 'gratis'):                             # change plan / cancel = Stripe's portal, never a 2nd subscription
                self.calls.clear()
                s, _, h = http('/plan/' + key, {'csrf': self.csrf}, self.cookie)
                self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/billing_portal-sessions'), key)
                self.assertEqual(self.calls, [('/billing_portal/sessions', {'customer': 'cus_h%d' % self.n, 'return_url': db.origin('app') + '/plan'})])
            self.calls.clear()
            s, _, h = http('/plan/portal', {'csrf': self.csrf}, self.cookie)
            self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/billing_portal-sessions'))
            s, _, h = http('/plan/pro', {'csrf': self.csrf}, self.cookie)   # already on Pro: nothing to do
            self.assertEqual((s, h['Location']), (303, '/plan'))
            s, _, h = http('/plan/portal', cookie=self.cookie)
            self.assertEqual((s, h['Location']), (303, '/plan'))
            self.assertEqual(len(self.calls), 1)
            # the portal's own cancellation comes back as a webhook
            s, _, _ = self.webhook(event('evt_del_%d' % self.n, 'customer.subscription.deleted', sub_obj('sub_h%d' % self.n, 'canceled')))
            self.assertEqual((s, self.plan()), (200, 'gratis'))
            s, page, _ = http('/plan', cookie=self.cookie)
            self.assertNotIn('Administrar mi pago', page)

    def test_downgrade_over_the_limit_is_blocked_even_for_payers(self):
        con = db.connect()
        for i in range(3):
            con.execute("INSERT INTO listings(agency_id, ref, slug, title, colonia, municipio, estado) VALUES (?,?,?,?,?,?,?)",
                        (self.aid, 'B-%d' % i, 'b-%d' % i, 'Propiedad %d' % i, 'Roma', 'Cuauhtémoc', 'CDMX'))
        con.commit()
        con.close()
        raw = checkout_event('evt_lim_%d' % self.n, self.aid, 'pro', 'cus_l%d' % self.n, 'sub_l%d' % self.n)
        with conf(), mock.patch.object(billing, '_post', self.fake_post):
            self.webhook(raw)
            s, page, _ = http('/plan/gratis', {'csrf': self.csrf}, self.cookie)
            self.assertEqual(s, 400)
            self.assertIn('Marca algunas como vendidas', page)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.plan(), 'pro')

    def test_agent_without_a_subscription_can_step_down_to_gratis(self):
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (self.aid,))   # granted by hand, no Stripe subscription
        con.commit()
        con.close()
        with conf(), mock.patch.object(billing, '_post', self.fake_post):
            s, page, _ = http('/plan/gratis', {'csrf': self.csrf}, self.cookie)
            self.assertEqual(s, 200)
            self.assertIn('Listo: ahora tienes el plan Gratis', page)
            self.assertEqual(self.plan(), 'gratis')
            self.assertEqual(self.q("SELECT COUNT(*) FROM audit WHERE action='plan_change_downgrade'")[0] >= 1, True)
        self.assertEqual(self.calls, [])

    def test_webhook_http_contract(self):
        with conf():
            raw = checkout_event('evt_c_%d' % self.n, self.aid, 'ia', 'cus_c%d' % self.n, 'sub_c%d' % self.n)
            s, body, _ = self.webhook(raw, 't=1,v1=' + '0' * 64)
            self.assertEqual((s, json.loads(body)['code']), (400, 'firma_invalida'))
            s, body, _ = self.webhook(raw, sign(raw, t=int(time.time()) - 1000))
            self.assertEqual((s, json.loads(body)['code']), (400, 'firma_vencida'))
            s, _, _ = self.webhook(raw, '')
            self.assertEqual(s, 400)
            self.assertEqual(self.plan(), 'gratis')
            s, body, _ = self.webhook(raw)
            self.assertEqual((s, json.loads(body)['status']), (200, 'handled'))
            s, body, _ = self.webhook(raw)
            self.assertEqual((s, json.loads(body)['status']), (200, 'duplicate'))
            other = event('evt_o_%d' % self.n, 'invoice.paid', {'id': 'in_1'})
            s, body, _ = self.webhook(other)
            self.assertEqual((s, json.loads(body)['status']), (200, 'ignored'))
            s, body, _ = self.webhook(b'not json')
            self.assertEqual(s, 400)
            s, _, h = http('/stripe/webhook', cookie=self.cookie)
            self.assertEqual((s, h['Allow']), (405, 'POST'))
            s, _, _ = http('/stripe/webhook', raw, headers={'Stripe-Signature': sign(raw)}, host='casa-rosa-1.fichaunica.localhost')
            self.assertEqual(s, 404)                                 # app host only
        self.assertEqual(self.plan(), 'ia')


class ProductionGuard(unittest.TestCase):
    def test_startup_refuses_unsafe_stripe_settings_in_production(self):
        from llave.web import common
        old = (db.ENV, db.SCHEME, db.PUBLIC_PORT, db.BASE_DOMAIN, common.SECRET)
        try:
            db.ENV, db.BASE_DOMAIN, common.SECRET, db.SCHEME, db.PUBLIC_PORT = 'production', 'fichaunica.mx', 'x' * 48, 'https', None
            with conf(**EMPTY):
                self.assertEqual(server.check_production_config(), [])        # Stripe off is allowed
            with conf(STRIPE_SECRET_KEY=LIVE_KEY), mock.patch.dict(os.environ, {}):
                os.environ.pop('LLAVE_STRIPE_LIVE', None)
                self.assertTrue(any('LLAVE_STRIPE_LIVE=1' in p for p in server.check_production_config()))
                with mock.patch.dict(os.environ, {'LLAVE_STRIPE_LIVE': '1'}):
                    self.assertEqual(server.check_production_config(), [])
            with conf(STRIPE_WEBHOOK_SECRET=''):
                self.assertTrue(any('STRIPE_WEBHOOK_SECRET' in p for p in server.check_production_config()))
            with conf():
                self.assertEqual(server.check_production_config(), [])
        finally:
            db.ENV, db.SCHEME, db.PUBLIC_PORT, db.BASE_DOMAIN, common.SECRET = old

    def test_migration_adds_columns_and_table_to_an_old_database(self):
        import sqlite3
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        with open(os.path.join(db.ROOT, 'llave', 'schema.sql'), encoding='utf-8') as fh:
            con.executescript(fh.read())                                       # a database from before billing
        self.assertNotIn('stripe_customer_id', [r[1] for r in con.execute('PRAGMA table_info(agencies)')])
        db.init(con)
        db.init(con)                                                           # idempotent
        cols = [r[1] for r in con.execute('PRAGMA table_info(agencies)')]
        self.assertIn('stripe_customer_id', cols)
        self.assertIn('stripe_subscription_id', cols)
        self.assertEqual([r[1] for r in con.execute('PRAGMA table_info(stripe_events)')][:2], ['event_id', 'type'])


if __name__ == '__main__':
    unittest.main()
