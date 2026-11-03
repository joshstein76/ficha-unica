"""The Gratis leak: sell a listing, publish another, reopen the first = 2 open on a 1-listing plan.
Reopening past the plan limit is refused with a clear Spanish message and nothing is lost; the other paths that skipped the
limit (direct POST to create, wizard publish) and the places that ignored the plan cap (Bolsa, portals, cards, buyer alerts)
are closed too. Real routes over a local server; direct DB setup only where a route would not reach."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import alerts_buyers, db  # noqa: E402
from llave.web import server  # noqa: E402
import web_harness  # noqa: E402


def form(title, status='activa', **kw):
    d = {'title': title, 'operation': 'venta', 'property_type': 'departamento', 'status': status, 'colonia': 'Roma Norte',
         'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000'}
    d.update(kw)
    return d


class Leak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('leak')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()

    def save(self, path, data):
        d = dict(data)
        d['csrf'] = self.u['csrf']
        return self.web.req(path, d, self.u['cookie'])

    def create(self, title, status='activa'):
        before = {r[0] for r in self.web.q('SELECT id FROM listings WHERE agency_id=?', self.u['aid'])}
        s, page, h = self.save('/propiedades/nueva', form(title, status))
        self.assertEqual(s, 303, page[:300])
        return ({r[0] for r in self.web.q('SELECT id FROM listings WHERE agency_id=?', self.u['aid'])} - before).pop()

    def status(self, lid):
        return self.web.one('SELECT status FROM listings WHERE id=?', lid)[0]

    def public(self):
        con = db.connect()
        try:
            return db.public_listing_ids(con, self.u['aid'])
        finally:
            con.close()

    # ---- the reported case
    def test_reopening_a_sold_listing_past_the_limit_is_refused_without_losing_anything(self):
        a = self.create('Departamento Roma Norte A')
        s, _, _ = self.save('/propiedades/%d' % a, form('Departamento Roma Norte A', 'vendida'))
        self.assertEqual((s, self.status(a)), (200, 'vendida'))
        b = self.create('Departamento Condesa B')                      # a slot is free again: allowed
        self.assertEqual(self.public(), [b])
        s, page, _ = self.save('/propiedades/%d' % a, form('Título nuevo de la A', 'activa', price='4200000'))
        self.assertEqual(s, 400)
        self.assertIn('No pudimos reabrir esta propiedad', page)
        self.assertIn('tu plan permite 1 propiedad y ya tienes 1 abierta', page)
        self.assertIn('no se perdió nada', page)
        self.assertEqual(self.status(a), 'vendida')                   # nothing written
        self.assertEqual(self.web.one('SELECT title, price_cents FROM listings WHERE id=?', a)[:], ('Departamento Roma Norte A', 350000000))
        self.assertIn('Título nuevo de la A', page)                   # the form still shows what they typed
        self.assertIn('value="4200000"', page)
        self.assertEqual(self.status(b), 'activa')
        self.assertEqual(self.public(), [b])
        self.assertEqual(self.web.one("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status='activa'", self.u['aid'])[0], 1)

    def test_it_works_again_once_a_slot_is_free(self):
        a = self.create('Casa Coyoacán A')
        self.save('/propiedades/%d' % a, form('Casa Coyoacán A', 'rentada'))
        b = self.create('Casa Coyoacán B')
        s, page, _ = self.save('/propiedades/%d' % a, form('Casa Coyoacán A', 'activa'))
        self.assertEqual((s, self.status(a)), (400, 'rentada'))
        self.save('/propiedades/%d' % b, form('Casa Coyoacán B', 'vendida'))
        s, page, _ = self.save('/propiedades/%d' % a, form('Casa Coyoacán A', 'activa'))
        self.assertEqual((s, self.status(a)), (200, 'activa'))
        self.assertEqual(self.public(), [a])

    def test_closed_to_closed_and_editing_an_open_listing_are_never_blocked(self):
        a = self.create('Casa Narvarte A')
        s, _, _ = self.save('/propiedades/%d' % a, form('Casa Narvarte A editada', 'pausada'))   # open -> paused: same slot
        self.assertEqual((s, self.status(a)), (200, 'pausada'))
        self.save('/propiedades/%d' % a, form('Casa Narvarte A', 'vendida'))
        b = self.create('Casa Narvarte B')
        s, _, _ = self.save('/propiedades/%d' % a, form('Casa Narvarte A, ya vendida', 'rentada'))  # closed -> closed
        self.assertEqual((s, self.status(a)), (200, 'rentada'))
        s, _, _ = self.save('/propiedades/%d' % b, form('Casa Narvarte B editada'))
        self.assertEqual((s, self.status(b)), (200, 'activa'))

    # ---- other ways around the limit
    def test_a_direct_post_cannot_create_past_the_limit(self):
        self.create('Depa Polanco A')
        s, page, _ = self.save('/propiedades/nueva', form('Depa Polanco B'))
        self.assertEqual(s, 403)
        self.assertIn('Llegaste al límite de tu plan (1 propiedad)', page)
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', self.u['aid'])[0], 1)

    def test_the_wizard_cannot_reopen_a_sold_listing(self):
        a = self.create('Depa Del Valle A')
        self.save('/propiedades/%d' % a, form('Depa Del Valle A', 'vendida'))
        b = self.create('Depa Del Valle B')
        s, page, _ = self.save('/nueva/%d/3' % a, {'title': 'Depa Del Valle A otra vez', 'description': ''})
        self.assertEqual(s, 400)
        self.assertIn('No pudimos reabrir', page)
        self.assertEqual((self.status(a), self.status(b)), ('vendida', 'activa'))

    def test_a_paid_plan_has_the_same_rule_with_its_own_limit(self):
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (self.u['aid'],))
        con.commit()
        ids = [self.create('Propiedad Pro %d' % i) for i in range(5)]
        con.execute("UPDATE listings SET status='vendida' WHERE id=?", (ids[0],))
        con.commit()
        extra = self.create('Propiedad Pro seis')
        s, page, _ = self.save('/propiedades/%d' % ids[0], form('Propiedad Pro 0', 'activa'))
        self.assertEqual(s, 400)
        self.assertIn('tu plan permite 5 propiedades y ya tienes 5 abiertas', page)
        a = con.execute('SELECT * FROM agencies WHERE id=?', (self.u['aid'],)).fetchone()
        self.assertTrue(server.reopen_message(con, a, con.execute('SELECT * FROM listings WHERE id=?', (ids[0],)).fetchone(), 'activa')
                        .startswith('No pudimos reabrir'))
        self.assertEqual(server.reopen_message(con, a, con.execute('SELECT * FROM listings WHERE id=?', (extra,)).fetchone(), 'pausada'), '')  # not closed
        con.close()

    # ---- places that ignored the plan cap
    def downgraded_agency_with_three(self):
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (self.u['aid'],))
        con.commit()
        con.close()
        ids = [self.create('Propiedad Cap %d' % i) for i in range(3)]
        con = db.connect()
        for i, lid in enumerate(ids):
            con.execute("UPDATE listings SET updated_at=datetime('now', ?), share_in_bolsa=1 WHERE id=?", ('-%d hours' % (10 - i), lid))
            con.execute("INSERT INTO photos(listing_id, position, sha256, sizes, width, height) VALUES (?,0,?,?,800,600)",
                        (lid, 'sha%d' % lid, '{"1600": "x.jpg", "800": "x.jpg", "400": "x.jpg"}'))
        con.execute("UPDATE agencies SET plan='gratis' WHERE id=?", (self.u['aid'],))   # card cancelled: only the newest stays public
        con.commit()
        con.close()
        return ids

    def test_portals_only_offer_and_accept_what_the_plan_shows(self):
        ids = self.downgraded_agency_with_three()
        s, page, _ = self.web.req('/portales', cookie=self.u['cookie'])
        self.assertIn('Propiedad Cap 2', page)
        self.assertNotIn('Propiedad Cap 0', page)
        s, page, _ = self.save('/portales/%d/mercadolibre' % ids[0], {})
        self.assertEqual(s, 403)
        self.assertIn('no se muestra con tu plan actual', page)
        self.assertEqual(self.web.q('SELECT * FROM portal_publications WHERE listing_id=?', ids[0]), [])
        self.assertEqual(self.web.q("SELECT * FROM outbox WHERE ref=?", 'listing:%d' % ids[0]), [])
        s, _, _ = self.save('/portales/%d/mercadolibre' % ids[2], {})
        self.assertEqual(s, 303)

    def test_bolsa_shares_stop_at_the_owners_cap(self):
        ids = self.downgraded_agency_with_three()
        other = self.web.signup()
        con = db.connect()
        for lid in ids:
            con.execute("INSERT INTO shares(listing_id, sharing_agency_id, split_pct) VALUES (?,?,50)", (lid, other['aid']))
        con.commit()
        self.assertEqual(db.public_listing_ids(con, other['aid']), [ids[2]])    # was all three
        con.close()
        s, page, _ = self.web.req('/bolsa', cookie=other['cookie'])
        self.assertNotIn('Propiedad Cap', page)                                   # Gratis: Bolsa is a Pro tool (upsell page)
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (other['aid'],))
        con.commit()
        con.close()
        s, page, _ = self.web.req('/bolsa', cookie=other['cookie'])
        self.assertIn('Propiedad Cap 2', page)
        self.assertNotIn('Propiedad Cap 0', page)
        self.assertNotIn('Propiedad Cap 1', page)

    def test_cards_of_a_hidden_listing_are_not_served(self):
        con = db.connect()
        con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (self.u['aid'],))
        # 7 open listings on a 5-listing plan: data from before the guards existed, the 2 oldest are over the limit
        for i in range(7):
            con.execute("INSERT INTO listings(agency_id, ref, slug, title, status, colonia, municipio, estado, updated_at) "
                        "VALUES (?,?,?,?, 'activa', 'Roma', 'Cuauhtémoc', 'CDMX', datetime('now', ?))",
                        (self.u['aid'], 'X-%d' % i, 'casa-%d' % i, 'Casa %d' % i, '-%d hours' % (10 - i)))
        con.commit()
        shown = set(db.public_listing_ids(con, self.u['aid'], include_shared=False))
        slugs = {r['id']: r['slug'] for r in con.execute('SELECT id, slug FROM listings WHERE agency_id=?', (self.u['aid'],))}
        agency_slug = con.execute('SELECT slug FROM agencies WHERE id=?', (self.u['aid'],)).fetchone()[0]
        con.close()
        self.assertEqual(len(shown), 5)
        hidden = [slugs[i] for i in slugs if i not in shown]
        self.assertEqual(sorted(hidden), ['casa-0', 'casa-1'])
        host = '%s.fichaunica.localhost' % agency_slug
        for slug in hidden:
            self.assertEqual(self.web.req('/propiedad/%s/tarjeta-post.jpg' % slug, host=host)[0], 404)
            self.assertEqual(self.web.req('/propiedad/%s' % slug, host=host)[0], 404)

    def test_buyer_alerts_skip_listings_the_plan_hides(self):
        ids = self.downgraded_agency_with_three()
        con = db.connect()
        sid = alerts_buyers.subscribe(con, self.u['aid'], 'Iván', '5598765432', consent=True)
        con.execute("UPDATE agencies SET whatsapp='+525511112222' WHERE id=?", (self.u['aid'],))
        con.commit()
        self.assertEqual(alerts_buyers.run(con), 1)                  # only the one the site shows
        self.assertEqual([r[0] for r in con.execute("SELECT ref FROM outbox WHERE kind='ghl.agent_alert'")],
                         ['saved_search:%d:%d' % (sid, ids[2])])
        con.close()


if __name__ == '__main__':
    unittest.main()
