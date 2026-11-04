"""The checkout page must open whichever seller is chosen, and the setup tool must be safe. No network: Stripe is faked."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from llave import billing, db  # noqa: E402
import stripe_setup  # noqa: E402

TEST_KEY = 'sk_test_FAKEFAKE'
FULL = {'STRIPE_SECRET_KEY': TEST_KEY, 'STRIPE_WEBHOOK_SECRET': 'whsec_FAKEFAKE', 'STRIPE_PRICE_PRO': 'price_pro_x', 'STRIPE_PRICE_IA': 'price_ia_x'}


def conf(**kw):
    return mock.patch.object(billing, 'settings', lambda: dict(FULL, **kw))


def agency_and_user():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    con = db.connect(path)
    db.init(con)
    aid = con.execute("INSERT INTO agencies(slug, name, email, plan) VALUES ('a1','A1','a1@ejemplo.test','gratis')").lastrowid
    uid = con.execute("INSERT INTO users(agency_id, name, email, password_hash) VALUES (?, 'Ana', 'a1-u@ejemplo.test', 'x')", (aid,)).lastrowid
    con.commit()
    return con, con.execute('SELECT * FROM agencies WHERE id=?', (aid,)).fetchone(), con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone(), path


class Seller(unittest.TestCase):
    def setUp(self):
        self.con, self.agency, self.user, path = agency_and_user()
        self.addCleanup(os.unlink, path)
        self.addCleanup(self.con.close)

    def params(self, **setting):
        seen = {}

        def fake(path, params, idem_key=None):
            seen.update(params)
            return {'url': 'https://checkout.stripe.com/x'}
        with conf(**setting), mock.patch.object(billing, '_post', fake):
            self.assertTrue(billing.checkout_url(self.con, self.agency, self.user, 'pro').startswith('https://checkout.stripe.com'))
        return seen

    def test_the_session_always_says_who_sells(self):
        # Stripe refuses a session on this account unless this is explicit: Managed Payments is on by default there.
        self.assertEqual(self.params()['managed_payments[enabled]'], 'false')
        self.assertEqual(self.params(STRIPE_MANAGED_PAYMENTS='0')['managed_payments[enabled]'], 'false')
        self.assertEqual(self.params(STRIPE_MANAGED_PAYMENTS='1')['managed_payments[enabled]'], 'true')

    def test_stripe_as_seller_uses_an_api_version_that_allows_it(self):
        seen = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"url": "https://checkout.stripe.com/x"}'

        def urlopen(req, timeout=None):
            seen['version'] = req.get_header('Stripe-version')
            return Resp()
        with conf(), mock.patch('urllib.request.urlopen', urlopen):
            billing._post('/checkout/sessions', {'managed_payments[enabled]': 'true'})
            self.assertEqual(seen['version'], billing.MANAGED_VERSION)
            billing._post('/checkout/sessions', {'managed_payments[enabled]': 'false'})
            self.assertEqual(seen['version'], billing.STRIPE_VERSION)
            billing._post('/billing_portal/sessions', {'customer': 'cus_1'})
            self.assertEqual(seen['version'], billing.STRIPE_VERSION)


class FakeStripe:
    """Just enough of Stripe for the setup tool."""

    def __init__(self, empty=True):
        self.products, self.prices, self.hooks, self.portals, self.writes = [], [], [], [], []
        if not empty:
            self.products = [{'id': 'prod_p', 'name': 'Ficha Única Pro', 'tax_code': None}, {'id': 'prod_i', 'name': 'Ficha Única Pro + IA', 'tax_code': stripe_setup.TAX_CODE}]
            self.prices = [{'id': 'price_pro_x', 'product': 'prod_p', 'unit_amount': 49900, 'currency': 'mxn', 'recurring': {'interval': 'month'}, 'tax_behavior': 'unspecified'},
                           {'id': 'price_ia_x', 'product': 'prod_i', 'unit_amount': 99900, 'currency': 'mxn', 'recurring': {'interval': 'month'}, 'tax_behavior': 'inclusive'}]
            self.hooks = [{'url': db.origin('app') + '/stripe/webhook', 'enabled_events': list(billing.HANDLED_EVENTS)}]
            self.portals = [{'id': 'bpc_1'}]

    def get(self, path, params=None):
        if path == '/products':
            return {'data': self.products}
        if path == '/prices':
            return {'data': [p for p in self.prices if p['product'] == params['product']]}
        if path == '/webhook_endpoints':
            return {'data': self.hooks}
        return {'data': self.portals}

    def post(self, path, params, idem_key=None):
        self.writes.append((path, params))
        if path == '/products':
            p = {'id': 'prod_%d' % len(self.products), 'name': params['name'], 'tax_code': params['tax_code']}
            self.products.append(p)
            return p
        if path.startswith('/products/'):
            p = next(x for x in self.products if x['id'] == path.split('/')[-1])
            p.update(params)
            return p
        if path == '/prices':
            p = {'id': 'price_new_%d' % len(self.prices), 'product': params['product'], 'unit_amount': params['unit_amount'], 'currency': params['currency'],
                 'recurring': {'interval': params['recurring[interval]']}, 'tax_behavior': params['tax_behavior']}
            self.prices.append(p)
            return p
        if path.startswith('/prices/'):
            p = next(x for x in self.prices if x['id'] == path.split('/')[-1])
            p.update(params)
            return p
        if path == '/webhook_endpoints':
            h = {'url': params['url'], 'enabled_events': [v for k, v in params.items() if k.startswith('enabled_events')], 'secret': 'whsec_NEWSECRET'}
            self.hooks.append(h)
            return h
        self.portals.append({'id': 'bpc_new'})
        return self.portals[-1]


class Setup(unittest.TestCase):
    def run_tool(self, stripe, args, **setting):
        said = []
        fd, path = tempfile.mkstemp(suffix='.env')
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('# nota\nSTRIPE_SECRET_KEY=%s\nSTRIPE_WEBHOOK_SECRET=\nSTRIPE_PRICE_PRO=\n' % TEST_KEY)
        with conf(**setting), mock.patch.object(stripe_setup, '_get', stripe.get), mock.patch.object(billing, '_post', stripe.post), \
                mock.patch.dict(os.environ, {'LLAVE_STRIPE_ENV_FILE': path}):
            code = stripe_setup.main(args, said.append)
        with open(path, encoding='utf-8') as fh:
            return code, said, fh.read(), oct(os.stat(path).st_mode)[-3:]

    def test_dry_run_changes_nothing(self):
        s = FakeStripe()
        code, said, text, _ = self.run_tool(s, [])
        self.assertEqual((code, s.writes), (0, []))
        self.assertNotIn('price_', text)

    def test_empty_account_gets_everything_and_prices_include_tax(self):
        s = FakeStripe()
        code, said, text, mode = self.run_tool(s, ['--go'], STRIPE_WEBHOOK_SECRET='', STRIPE_PRICE_PRO='', STRIPE_PRICE_IA='')
        self.assertEqual(code, 0)
        self.assertEqual([p['tax_code'] for p in s.products], [stripe_setup.TAX_CODE] * 2)
        self.assertEqual([(p['unit_amount'], p['currency'], p['tax_behavior']) for p in s.prices], [(49900, 'mxn', 'inclusive'), (99900, 'mxn', 'inclusive')])
        self.assertEqual(len(s.hooks), 1)
        self.assertEqual(set(s.hooks[0]['enabled_events']), set(billing.HANDLED_EVENTS))
        self.assertEqual(len(s.portals), 1)
        self.assertIn('STRIPE_WEBHOOK_SECRET=whsec_NEWSECRET', text)
        self.assertIn('STRIPE_PRICE_IA=price_new_1', text)
        self.assertIn('# nota', text)
        self.assertEqual(mode, '600')

    def test_it_never_says_a_secret(self):
        s = FakeStripe()
        _, said, _, _ = self.run_tool(s, ['--go'], STRIPE_WEBHOOK_SECRET='', STRIPE_PRICE_PRO='', STRIPE_PRICE_IA='')
        blob = ' '.join(said)
        for secret in ('whsec_', 'sk_test', 'price_new'):
            self.assertNotIn(secret, blob)

    def test_running_twice_creates_nothing_new(self):
        s = FakeStripe()
        self.run_tool(s, ['--go'], STRIPE_WEBHOOK_SECRET='', STRIPE_PRICE_PRO='', STRIPE_PRICE_IA='')
        before = len(s.writes)
        self.run_tool(s, ['--go'], STRIPE_PRICE_PRO=s.prices[0]['id'], STRIPE_PRICE_IA=s.prices[1]['id'])
        self.assertEqual(len(s.writes), before)

    def test_existing_objects_are_fixed_not_duplicated(self):
        s = FakeStripe(empty=False)
        self.run_tool(s, ['--go'])
        self.assertEqual((len(s.products), len(s.prices), len(s.hooks), len(s.portals)), (2, 2, 1, 1))
        self.assertEqual(s.products[0]['tax_code'], stripe_setup.TAX_CODE)
        self.assertEqual(s.prices[0]['tax_behavior'], 'inclusive')

    def test_a_live_key_needs_the_switch(self):
        s = FakeStripe()
        live = 'sk_' + 'live_FAKEFAKE'
        env = {k: v for k, v in os.environ.items() if k != 'LLAVE_STRIPE_LIVE'}
        with mock.patch.dict(os.environ, env, clear=True):
            code, said, _, _ = self.run_tool(s, ['--go'], STRIPE_SECRET_KEY=live)
        self.assertEqual((code, s.writes), (2, []))


if __name__ == '__main__':
    unittest.main()
