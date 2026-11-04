"""LLAVE_ECO_LIVE: the credits side of Servicios (balance, 'Cómo ganas créditos', the redeem catalog, /servicios/canjear) is off by default,
because no sister company can confirm anything yet. Plus: 'Invita a un colega' drops the "one more listing" promise for plans without a limit.
Real routes over a local server (tests/web_harness.py)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import db, eco  # noqa: E402
import web_harness  # noqa: E402

CARDS = ('Póliza jurídica para rentas', 'VIVE Polanco', 'IDX Bloom', 'Ciao Bella Marketing')
CREDIT_WORDS = ('crédito', 'Crédito', 'Canjea', 'Cómo ganas', 'Ecosistema', 'leads gratis')
PROMISE = 'más</b> en tu plan'


class Base(unittest.TestCase):
    def setUp(self):
        self.web = web_harness.LocalServer('ecolive')
        self.addCleanup(self.web.close)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('LLAVE_ECO_LIVE', None)
        os.environ.pop('LLAVE_PLANS_V2', None)

    def sql(self, query, *args):
        con = db.connect()
        try:
            con.execute(query, args)
            con.commit()
        finally:
            con.close()

    def plan(self, u, plan):
        self.sql('UPDATE agencies SET plan=? WHERE id=?', plan, u['aid'])

    def credits(self, u):
        """Give the agency 80 confirmed credits the way the webhook would, so a redeem would succeed if the page allowed it."""
        con = db.connect()
        try:
            eco.ensure_tables(con)
            eco.record_event(con, 'vive', 'referido_cerrado', 'T-1', u['aid'], confirmed=True)
            eco.record_event(con, 'rentapoliza', 'poliza_emitida', 'T-2', u['aid'], confirmed=True)
            return eco.balance(con, u['aid'])
        finally:
            con.close()

    def get(self, u, path):
        return self.web.req(path, cookie=u['cookie'])

    def post(self, u, path, data=None):
        d = {'csrf': u['csrf']}
        d.update(data or {})
        return self.web.req(path, d, u['cookie'])


class ServicesCredits(Base):
    def test_flag_is_off_by_default_and_only_exactly_1_turns_it_on(self):
        self.assertFalse(eco.live())
        for v, want in (('1', True), ('0', False), ('true', False), ('', False)):
            os.environ['LLAVE_ECO_LIVE'] = v
            self.assertEqual(eco.live(), want, v)

    def test_off_page_is_servicios_a_short_line_and_the_four_cards(self):
        u = self.web.signup()
        self.assertEqual(self.credits(u), 80)             # even with a real balance in the ledger, nothing about it is shown
        s, page, _ = self.get(u, '/servicios')
        self.assertEqual(s, 200)
        self.assertIn('<h1>Servicios</h1>', page)
        self.assertIn('Otras empresas de la familia de Ficha Única, por si te sirven.', page)
        for c in CARDS:
            self.assertIn(c, page)
        self.assertEqual(page.count('<div class="card"><span class="small muted">'), 4)
        for w in CREDIT_WORDS:
            self.assertNotIn(w, page, w)
        self.assertNotIn('/servicios/canjear', page)
        self.assertNotIn('Tus créditos', page)

    def test_on_page_is_the_full_credits_page_again(self):
        u = self.web.signup()
        self.credits(u)
        os.environ['LLAVE_ECO_LIVE'] = '1'
        s, page, _ = self.get(u, '/servicios')
        self.assertEqual(s, 200)
        for t in ('Servicios y Ecosistema', 'Úsalas y gana créditos', 'Tus créditos', 'Cómo ganas créditos', 'Canjea tus créditos',
                  '/servicios/canjear/destacar_7d', 'Sobre los leads gratis'):
            self.assertIn(t, page, t)
        for c in CARDS:
            self.assertIn(c, page)

    def test_redeem_route_fails_politely_when_off_and_writes_nothing(self):
        u = self.web.signup()
        self.credits(u)
        before = self.web.q('SELECT COUNT(*) FROM eco_ledger')[0][0], self.web.q('SELECT COUNT(*) FROM eco_boosts')[0][0]
        for item in ('extra_10_listings_30d', 'prioridad_leads_30d', 'destacar_7d', 'no_existe'):
            s, page, _ = self.post(u, '/servicios/canjear/' + item)
            self.assertEqual(s, 400, item)
            self.assertIn('Por ahora no hay créditos para canjear.', page, item)
            self.assertIn('<h1>Servicios</h1>', page, item)        # the normal page, not a bare error or a traceback
            self.assertNotIn('Traceback', page)
        after = self.web.q('SELECT COUNT(*) FROM eco_ledger')[0][0], self.web.q('SELECT COUNT(*) FROM eco_boosts')[0][0]
        self.assertEqual(before, after)
        con = db.connect()
        try:
            self.assertEqual(eco.balance(con, u['aid']), 80)
        finally:
            con.close()

    def test_redeem_still_works_when_on(self):
        u = self.web.signup()
        self.credits(u)
        os.environ['LLAVE_ECO_LIVE'] = '1'
        s, page, _ = self.post(u, '/servicios/canjear/extra_10_listings_30d')
        self.assertEqual(s, 200)
        self.assertIn('canjeado', page)
        con = db.connect()
        try:
            self.assertEqual(eco.balance(con, u['aid']), 50)
        finally:
            con.close()

    def test_engine_and_webhook_route_are_still_there(self):
        """The engine and its routes stay: the signed webhook answers (503 = no secret set) with the flag off."""
        s, body, _ = self.web.req('/api/eco/rentapoliza', {'x': '1'})
        self.assertEqual(s, 503)
        self.assertIn('no_configurado', body)
        self.assertTrue(eco.CATALOG and eco.RULES)


class InviteWithoutALimit(Base):
    def test_limited_plans_keep_the_listing_promise(self):
        u = self.web.signup()                              # gratis, 1 propiedad today
        s, page, _ = self.get(u, '/invitar')
        self.assertIn('te damos <b>1 propiedad más</b> en tu plan, para siempre.', page)
        self.assertIn('Propiedades extra ganadas', page)
        s, home, _ = self.get(u, '/')
        self.assertIn('Invita a un colega · +1 propiedad</h2>', home)
        self.assertIn('Por cada colega que publique con tu enlace.', home)

    def test_limited_plans_under_plans_v2_keep_it_too(self):
        os.environ['LLAVE_PLANS_V2'] = '1'
        u = self.web.signup()
        self.plan(u, 'pro')                                # 25 under the new plans: still a limit
        s, page, _ = self.get(u, '/invitar')
        self.assertIn('te damos <b>1 propiedad más</b> en tu plan', page)

    def test_unlimited_plan_keeps_the_invitation_and_drops_the_promise(self):
        os.environ['LLAVE_PLANS_V2'] = '1'
        u = self.web.signup()
        self.plan(u, 'ia')
        con = db.connect()
        try:
            self.assertTrue(db.is_unlimited(db.listing_limit(con, con.execute('SELECT * FROM agencies WHERE id=?', (u['aid'],)).fetchone())))
        finally:
            con.close()
        s, page, _ = self.get(u, '/invitar')
        self.assertEqual(s, 200)
        self.assertNotIn(PROMISE, page)
        self.assertNotIn('te damos', page)
        self.assertNotIn('Propiedades extra ganadas', page)
        self.assertNotIn('para siempre', page)
        self.assertIn('Pasa tu enlace a otros asesores.', page)
        self.assertIn('/registro?ref=', page)              # the invitation itself: link, WhatsApp share, copy
        self.assertIn('Compartir por WhatsApp', page)
        self.assertIn('Copiar enlace', page)
        self.assertIn('Colegas invitados', page)
        self.assertIn('Ya publicaron', page)
        s, home, _ = self.get(u, '/')
        self.assertIn('Invita a un colega</h2>', home)
        self.assertNotIn('Invita a un colega · +', home)
        self.assertNotIn('Por cada colega que publique con tu enlace.', home)
        self.assertIn('Comparte tu enlace con otros asesores.', home)

    def test_unlimited_plan_still_lists_who_signed_up(self):
        os.environ['LLAVE_PLANS_V2'] = '1'
        u = self.web.signup(agency='Invita Mucho')
        self.plan(u, 'ia')
        s, _, _ = self.web.req('/registro', {'name': 'Luis Ramos', 'agency': 'Hogares Norte', 'whatsapp': '55 1111 2222',
                                             'email': 'luis@ejemplo.test', 'password': 'segura1234', 'terms': '1', 'ref': 'invita-mucho'})
        self.assertEqual(s, 303)
        s, page, _ = self.get(u, '/invitar')
        self.assertIn('Hogares Norte', page)
        self.assertIn('aún sin publicar', page)


if __name__ == '__main__':
    unittest.main()
