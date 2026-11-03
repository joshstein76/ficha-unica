"""Test-key lock (2026-11-03): production runs a Stripe TEST key with open sign-up, so anyone could pay with card 4242 and get
Pro free. While the key is a test key in production, paid plans are closed for everyone except LLAVE_STRIPE_TEST_EMAILS.
Enforced on the server routes (checkout, portal, plan switch). Live keys and local runs behave as before. No network."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import billing, db  # noqa: E402
import web_harness  # noqa: E402

for _k in billing.SETTING_KEYS + ('LLAVE_STRIPE_LIVE', 'LLAVE_STRIPE_TEST_EMAILS'):
    os.environ.pop(_k, None)
os.environ['LLAVE_STRIPE_ENV_FILE'] = os.path.join(tempfile.mkdtemp(), 'no-stripe.env')

TEST_KEY = 'sk_test_FAKEFAKE'
LIVE_KEY = 'sk_' + 'live_FAKEFAKE'
FULL = {'STRIPE_SECRET_KEY': TEST_KEY, 'STRIPE_WEBHOOK_SECRET': 'whsec_FAKEFAKE', 'STRIPE_PRICE_PRO': 'price_pro_x', 'STRIPE_PRICE_IA': 'price_ia_x'}


def conf(**kw):
    d = dict(FULL)
    d.update(kw)
    return mock.patch.object(billing, 'settings', lambda: dict(d))


class production:
    """db.ENV = 'production' for a block (restored after)."""
    def __enter__(self):
        self.old = db.ENV
        db.ENV = 'production'

    def __exit__(self, *a):
        db.ENV = self.old


class Pure(unittest.TestCase):
    def test_lock_only_in_production_with_a_test_key(self):
        for env, key, want in (('production', TEST_KEY, True), ('production', LIVE_KEY, False), ('production', '', False),
                               ('local', TEST_KEY, False), ('local', LIVE_KEY, False)):
            old, db.ENV = db.ENV, env
            try:
                with conf(STRIPE_SECRET_KEY=key):
                    self.assertEqual(billing.test_lock_active(), want, (env, key[:8]))
            finally:
                db.ENV = old

    def test_allowed_emails_parse_loose_input(self):
        with mock.patch.dict(os.environ, {'LLAVE_STRIPE_TEST_EMAILS': ' Josh@Ejemplo.test ,ana@ejemplo.test;;  luis@ejemplo.test '}):
            self.assertEqual(billing.test_emails(), {'josh@ejemplo.test', 'ana@ejemplo.test', 'luis@ejemplo.test'})
        with mock.patch.dict(os.environ, {'LLAVE_STRIPE_TEST_EMAILS': ''}):
            self.assertEqual(billing.test_emails(), set())

    def test_paid_closed_for_everyone_but_the_list(self):
        with production(), conf(), mock.patch.dict(os.environ, {'LLAVE_STRIPE_TEST_EMAILS': 'josh@ejemplo.test'}):
            self.assertTrue(billing.paid_closed('rosa@ejemplo.test'))
            self.assertTrue(billing.paid_closed(''))
            self.assertTrue(billing.paid_closed(None))
            self.assertFalse(billing.paid_closed('JOSH@ejemplo.test '))
        with production(), conf(STRIPE_SECRET_KEY=LIVE_KEY), mock.patch.dict(os.environ, {'LLAVE_STRIPE_LIVE': '1'}):
            self.assertFalse(billing.paid_closed('rosa@ejemplo.test'))     # live keys behave as before
        with conf():
            self.assertFalse(billing.paid_closed('rosa@ejemplo.test'))     # local / dev behave as before


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('lock')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()
        self.calls = []

        def fake_post(path, params, idem_key=None):
            self.calls.append((path, params))
            return {'url': 'https://pay.stripe.test/' + path.strip('/').replace('/', '-')}

        self.fake_post = fake_post

    def plan(self):
        return self.web.one('SELECT plan FROM agencies WHERE id=?', self.u['aid'])[0]

    def post(self, path):
        return self.web.req(path, {'csrf': self.u['csrf']}, self.u['cookie'])

    def test_stranger_cannot_start_a_paid_plan(self):
        with production(), conf(), mock.patch.object(billing, '_post', self.fake_post), mock.patch.dict(os.environ, {'LLAVE_STRIPE_TEST_EMAILS': 'otro@ejemplo.test'}):
            for key in ('pro', 'ia'):
                s, page, _ = self.web.req('/plan/' + key, cookie=self.u['cookie'])
                self.assertEqual(s, 200, key)
                self.assertIn('llega muy pronto', page)
                self.assertNotIn('Pagar con tarjeta', page)
                s, page, h = self.post('/plan/' + key)
                self.assertEqual(s, 503, key)                       # the server refuses, not just the page
                self.assertNotIn('Location', h)
                self.assertIn('llega muy pronto', page)
            s, page, _ = self.post('/plan/portal')
            self.assertEqual(s, 503)
            s, page, _ = self.web.req('/plan', cookie=self.u['cookie'])
            self.assertEqual(s, 200)
            self.assertNotIn('procesado por Stripe', page)           # the plan page stops promising card payments
            self.assertNotIn('Administrar mi pago', page)
            s, page, _ = self.web.req('/plan?pago=ok', cookie=self.u['cookie'])
            self.assertNotIn('Gracias: tu plan se activa', page)
        self.assertEqual(self.calls, [])                             # Stripe was never called
        self.assertEqual(self.plan(), 'gratis')

    def test_the_owner_email_can_still_run_a_test_purchase(self):
        env = {'LLAVE_STRIPE_TEST_EMAILS': 'nadie@ejemplo.test, %s' % self.u['email'].upper()}
        with production(), conf(), mock.patch.object(billing, '_post', self.fake_post), mock.patch.dict(os.environ, env):
            s, page, _ = self.web.req('/plan/pro', cookie=self.u['cookie'])
            self.assertIn('Pagar con tarjeta', page)
            s, _, h = self.post('/plan/pro')
            self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/checkout-sessions'))
            self.assertEqual(self.calls[0][0], '/checkout/sessions')
            self.assertEqual(self.plan(), 'gratis')                  # only the signed webhook upgrades
            s, page, _ = self.web.req('/plan?pago=ok', cookie=self.u['cookie'])
            self.assertIn('Gracias: tu plan se activa', page)

    def test_a_live_key_is_not_locked(self):
        with production(), conf(STRIPE_SECRET_KEY=LIVE_KEY), mock.patch.object(billing, '_post', self.fake_post), \
                mock.patch.dict(os.environ, {'LLAVE_STRIPE_LIVE': '1'}):
            s, _, h = self.post('/plan/ia')
            self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/checkout-sessions'))

    def test_local_with_a_test_key_behaves_as_today(self):
        with conf(), mock.patch.object(billing, '_post', self.fake_post):   # db.ENV is 'local' here
            s, _, h = self.post('/plan/pro')
            self.assertEqual((s, h['Location']), (303, 'https://pay.stripe.test/checkout-sessions'))

    def test_stripe_off_in_production_is_the_same_closed_state(self):
        with production(), conf(STRIPE_SECRET_KEY=''):
            s, page, _ = self.post('/plan/pro')
            self.assertEqual(s, 503)
            self.assertIn('llega muy pronto', page)
        self.assertEqual(self.plan(), 'gratis')

    def test_a_stranger_with_a_test_subscription_can_still_step_down(self):
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro', stripe_subscription_id='sub_t', stripe_customer_id='cus_t' WHERE id=?", (self.u['aid'],))
        con.commit()
        con.close()
        with production(), conf(), mock.patch.object(billing, '_post', self.fake_post), mock.patch.dict(os.environ, {'LLAVE_STRIPE_TEST_EMAILS': ''}):
            s, page, _ = self.web.req('/plan/gratis', cookie=self.u['cookie'])
            self.assertEqual(s, 200)
            self.assertIn('Pasar a Gratis', page)
            self.assertNotIn('Administrar mi pago', page)            # no portal while the lock is on
            s, page, _ = self.post('/plan/gratis')
            self.assertEqual(s, 200)
            self.assertIn('Listo: ahora tienes el plan Gratis', page)
        row = self.web.one('SELECT plan, stripe_subscription_id FROM agencies WHERE id=?', self.u['aid'])
        self.assertEqual((row['plan'], row['stripe_subscription_id']), ('gratis', None))
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
