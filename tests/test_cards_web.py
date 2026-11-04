"""Cards over the real routes: who gets which card, cache headers, the share buttons in the panel, the ¡Vendida! / ¡Rentada! card,
and the link preview (og:image) of the public listing page."""
import io
import os
import re
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

from llave import db, photos  # noqa: E402
import web_harness  # noqa: E402
from tests.test_photos import make_jpeg  # noqa: E402


def form(title, status='activa', **kw):
    d = {'title': title, 'operation': 'venta', 'property_type': 'departamento', 'status': status, 'colonia': 'Roma Norte',
         'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000', 'm2_built': '90', 'bedrooms': '2'}
    d.update(kw)
    return d


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('cardsweb')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self._v2 = os.environ.pop('LLAVE_PLANS_V2', None)
        self.u = self.web.signup()
        self.slug = self.web.one('SELECT slug FROM agencies WHERE id=?', self.u['aid'])[0]
        self.host = '%s.fichaunica.localhost' % self.slug

    def tearDown(self):
        os.environ.pop('LLAVE_PLANS_V2', None)
        if self._v2 is not None:
            os.environ['LLAVE_PLANS_V2'] = self._v2

    # ---- helpers
    def plan(self, plan):
        con = db.connect()
        con.execute('UPDATE agencies SET plan=? WHERE id=?', (plan, self.u['aid']))
        con.commit()
        con.close()

    def save(self, path, data, user=None):
        user = user or self.u
        d = dict(data)
        d['csrf'] = user['csrf']
        return self.web.req(path, d, user['cookie'])

    def create(self, title, status='activa', photo=False, **kw):
        before = {r[0] for r in self.web.q('SELECT id FROM listings WHERE agency_id=?', self.u['aid'])}
        s, page, _ = self.save('/propiedades/nueva', form(title, status, **kw))
        self.assertEqual(s, 303, page[:300])
        lid = ({r[0] for r in self.web.q('SELECT id FROM listings WHERE agency_id=?', self.u['aid'])} - before).pop()
        if photo:
            con = db.connect()
            photos.ingest(con, lid, make_jpeg((1800, 1200), seed=lid))
            con.commit()
            con.close()
        return lid

    def slug_of(self, lid):
        return self.web.one('SELECT slug FROM listings WHERE id=?', lid)[0]

    def raw(self, path, host=None, cookie=None, headers=None):
        h = {'Host': host or self.host}
        h.update(headers or {})
        if cookie:
            h['Cookie'] = cookie
        try:
            r = web_harness.OPENER.open(urllib.request.Request('http://127.0.0.1:%d%s' % (self.web.port, path), headers=h), timeout=60)
            return r.status, r.read(), r.headers
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read(), ex.headers

    def card(self, lid, kind='post'):
        return self.raw('/propiedad/%s/tarjeta-%s.jpg' % (self.slug_of(lid), kind))

    def panel_page(self, lid):
        s, page, _ = self.web.req('/propiedades/%d' % lid, cookie=self.u['cookie'])
        self.assertEqual(s, 200)
        return page

    def size(self, data):
        with Image.open(io.BytesIO(data)) as im:
            return im.format, im.size

    # ---- who gets which card
    def test_gratis_has_no_instagram_cards_today_but_the_link_preview_works(self):
        lid = self.create('Departamento Roma Norte A')
        self.assertEqual(self.card(lid, 'post')[0], 404)
        self.assertEqual(self.card(lid, 'historia')[0], 404)
        s, data, h = self.card(lid, 'enlace')
        self.assertEqual((s, h['Content-Type'], self.size(data)), (200, 'image/jpeg', ('JPEG', (1200, 630))))

    def test_plans_v2_gives_gratis_only_the_plain_post_card(self):
        lid = self.create('Departamento Roma Norte B')
        os.environ['LLAVE_PLANS_V2'] = '1'
        s, data, _ = self.card(lid, 'post')
        self.assertEqual((s, self.size(data)), (200, ('JPEG', (1080, 1350))))
        self.assertEqual(self.card(lid, 'historia')[0], 404)
        page = self.panel_page(lid)
        self.assertIn('/tarjeta-post.jpg', page)
        self.assertNotIn('/tarjeta-historia.jpg', page)
        self.assertIn('La tarjeta para historia viene en el plan Pro', page)
        os.environ.pop('LLAVE_PLANS_V2')
        self.assertEqual(self.card(lid, 'post')[0], 404)
        self.assertNotIn('/tarjeta-post.jpg', self.panel_page(lid))

    def test_pro_gets_post_and_story_with_short_cache_and_an_etag_that_follows_the_listing(self):
        self.plan('pro')
        lid = self.create('Departamento Roma Norte C', photo=True)
        s, d1, h1 = self.card(lid, 'post')
        self.assertEqual((s, self.size(d1)), (200, ('JPEG', (1080, 1350))))
        self.assertEqual(self.size(self.card(lid, 'historia')[1]), ('JPEG', (1080, 1920)))
        self.assertEqual(h1['Cache-Control'], 'public, max-age=300')     # same URL, changing picture: never "immutable"
        etag = h1['ETag']
        s, body, _ = self.raw('/propiedad/%s/tarjeta-post.jpg' % self.slug_of(lid), headers={'If-None-Match': etag})
        self.assertEqual((s, body), (304, b''))
        s, page, _ = self.save('/propiedades/%d' % lid, form('Departamento Roma Norte C', price='3900000'))     # the agent changes the price
        self.assertEqual(s, 200)
        s, d2, h2 = self.card(lid, 'post')
        self.assertNotEqual(h2['ETag'], etag)
        self.assertNotEqual(d1, d2)
        s, _, _ = self.raw('/propiedad/%s/tarjeta-post.jpg' % self.slug_of(lid), headers={'If-None-Match': etag})
        self.assertEqual(s, 200)                                           # the old ETag no longer matches: the new card is sent

    def test_cards_only_for_listings_the_site_really_shows(self):
        self.plan('pro')
        draft = self.create('Departamento Roma Norte D', 'borrador')
        sold = self.create('Departamento Roma Norte E', 'vendida')
        for lid in (draft, sold):
            for kind in ('post', 'historia', 'enlace'):
                self.assertEqual(self.card(lid, kind)[0], 404, (lid, kind))
        self.assertEqual(self.raw('/propiedad/no-existe/tarjeta-post.jpg')[0], 404)

    # ---- the panel
    def test_panel_share_buttons(self):
        self.plan('pro')
        lid = self.create('Casa con jardín en Coyoacán', colonia='Del Carmen', municipio='Coyoacán')
        page = self.panel_page(lid)
        self.assertIn('Mándalo a tus grupos', page)
        self.assertIn('Tarjeta para publicar', page)
        self.assertIn('Tarjeta para historia', page)
        url = 'http://%s:%d/propiedad/%s' % (self.host, self.web.port, self.slug_of(lid))
        self.assertIn('%s/tarjeta-post.jpg' % url, page)
        self.assertIn('%s/tarjeta-historia.jpg' % url, page)
        wa = re.search(r'href="(https://wa\.me/\?text=[^"]+)"', page)
        self.assertTrue(wa, 'a wa.me link with no phone number')
        text = urllib.parse.unquote(wa.group(1).split('?text=')[1])
        self.assertEqual(text, 'Casa con jardín en Coyoacán\n$3,500,000 MXN · Del Carmen, Coyoacán\nFotos y datos aquí: %s' % url)
        self.assertNotRegex(wa.group(1), r'wa\.me/\d')
        for kind in ('post', 'historia'):                                  # and the buttons lead to real images
            self.assertEqual(self.raw(re.search(r'href="[^"]*(/propiedad/[^"]+/tarjeta-%s\.jpg)"' % kind, page).group(1))[0], 200)

    def test_gratis_panel_keeps_the_whatsapp_share_and_points_to_pro_for_cards(self):
        lid = self.create('Departamento Roma Norte F')
        page = self.panel_page(lid)
        self.assertIn('Mándalo a tus grupos', page)
        self.assertNotIn('/tarjeta-post.jpg', page)
        self.assertNotIn('/tarjeta-historia.jpg', page)
        self.assertIn('Las tarjetas para Instagram y WhatsApp vienen en el plan Pro', page)
        self.assertNotIn('Presume tu cierre', page)

    def test_a_listing_the_plan_hides_has_nothing_to_share(self):
        a = self.create('Departamento Roma Norte G')
        con = db.connect()
        con.execute("INSERT INTO listings(agency_id, ref, slug, title, status, colonia, municipio, estado, updated_at) "
                    "VALUES (?, 'X-9', 'otra-nueva', 'Otra más nueva', 'activa', 'Roma', 'Cuauhtémoc', 'CDMX', datetime('now', '+1 hour'))", (self.u['aid'],))
        con.commit()
        con.close()
        page = self.panel_page(a)                                          # Gratis shows only the newest one
        self.assertIn('Esta propiedad no se ve en tu sitio', page)
        self.assertNotIn('Mándalo a tus grupos', page)

    def test_the_closing_card_is_offered_only_on_sold_or_rented_listings(self):
        self.plan('pro')
        lid = self.create('Departamento Condesa H')
        for status in ('borrador', 'activa', 'apartada', 'pausada'):
            self.save('/propiedades/%d' % lid, form('Departamento Condesa H', status))
            page = self.panel_page(lid)
            self.assertNotIn('cierre-post', page, status)
            self.assertNotIn('Presume tu cierre', page, status)
            self.assertEqual(self.raw('/propiedades/%d/cierre-post.jpg' % lid, host=web_harness.APP, cookie=self.u['cookie'])[0], 404, status)
        for status, word in (('vendida', '«¡Vendida!»'), ('rentada', '«¡Rentada!»')):
            s, page, _ = self.save('/propiedades/%d' % lid, form('Departamento Condesa H', status))
            self.assertEqual(s, 200)
            page = self.panel_page(lid)
            self.assertIn('¡Presume tu cierre!', page)
            self.assertIn(word, page)
            self.assertIn('formaction="/propiedades/%d/cierre-post.jpg"' % lid, page)
            self.assertIn('formaction="/propiedades/%d/cierre-historia.jpg"' % lid, page)
            self.assertIn('<input type="checkbox" name="precio" value="1">', page)     # price off unless the agent ticks it
            self.assertIn('Si no lo marcas, la tarjeta no lleva ningún precio.', page)
            self.assertNotIn('Mándalo a tus grupos', page)                 # a closed listing is not for sale any more

    def closing(self, lid, kind='post', precio=False, user=None):
        user = user or self.u
        return self.raw('/propiedades/%d/cierre-%s.jpg%s' % (lid, kind, '?precio=1' if precio else ''), host=web_harness.APP, cookie=user['cookie'])

    def test_closing_card_route(self):
        self.plan('pro')
        lid = self.create('Departamento Condesa I', 'vendida', photo=True)
        s, hidden, h = self.closing(lid, 'post')
        self.assertEqual((s, self.size(hidden), h['Cache-Control']), (200, ('JPEG', (1080, 1350)), 'private, no-cache'))
        self.assertEqual(self.size(self.closing(lid, 'historia')[1]), ('JPEG', (1080, 1920)))
        s, shown, _ = self.closing(lid, 'post', precio=True)
        self.assertEqual(s, 200)
        self.assertNotEqual(hidden, shown)                                  # the list price is on one and not the other
        # not public: the public site has no closing card, and another agency cannot ask for this one
        self.assertEqual(self.raw('/propiedad/%s/cierre-post.jpg' % self.slug_of(lid))[0], 404)
        other = self.web.signup()
        s, _, _ = self.closing(lid, 'post', user=other)
        self.assertEqual(s, 404)
        s, _, h = self.raw('/propiedades/%d/cierre-post.jpg' % lid, host=web_harness.APP)             # no session
        self.assertEqual((s, h['Location']), (303, '/entrar'))

    def test_closing_card_is_a_pro_tool_and_gratis_sees_the_plan_page(self):
        lid = self.create('Departamento Condesa J', 'vendida')
        page = self.panel_page(lid)
        self.assertIn('Viene en el plan Pro', page)
        self.assertNotIn('cierre-post.jpg', page)
        s, body, h = self.closing(lid, 'post')
        self.assertTrue(h['Content-Type'].startswith('text/html'))
        self.assertIn(b'plan Pro', body)
        os.environ['LLAVE_PLANS_V2'] = '1'                                  # V2 gives Gratis the post card only, never this one
        s, body, h = self.closing(lid, 'post')
        self.assertTrue(h['Content-Type'].startswith('text/html'))

    def test_wizard_done_shares_with_the_same_message(self):
        lid = self.create('Departamento Roma Norte K')
        s, page, _ = self.web.req('/nueva/%d/lista' % lid, cookie=self.u['cookie'])
        self.assertEqual(s, 200)
        self.assertIn('Mándalo a tus grupos', page)
        self.assertRegex(page, r'href="https://wa\.me/\?text=Departamento')
        self.assertNotIn('tarjeta-post.jpg', page)                          # Gratis
        self.plan('ia')
        self.assertIn('tarjeta-post.jpg', self.web.req('/nueva/%d/lista' % lid, cookie=self.u['cookie'])[1])

    # ---- the link preview
    def meta(self, page, prop):
        m = re.search(r'<meta property="%s" content="([^"]*)"' % re.escape(prop), page)
        return m.group(1) if m else None

    def test_listing_page_link_preview_with_a_photo(self):
        lid = self.create('Departamento Roma Norte L', photo=True)
        s, page, _ = self.web.req('/propiedad/%s' % self.slug_of(lid), host=self.host)
        self.assertEqual(s, 200)
        img = self.meta(page, 'og:image')
        self.assertRegex(img, r'/media/[0-9a-f]{2}/[0-9a-f]{64}/800\.jpg$')    # the 800 px file: light enough for WhatsApp to show
        s, data, _ = self.raw(urllib.parse.urlsplit(img).path)
        self.assertEqual(s, 200)
        real = self.size(data)[1]
        self.assertEqual(int(self.meta(page, 'og:image:width')), real[0])
        self.assertLessEqual(abs(int(self.meta(page, 'og:image:height')) - real[1]), 1)    # the declared size is the real one (to the pixel rounding)
        self.assertEqual(self.meta(page, 'og:title'), 'Departamento Roma Norte L')
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', page)
        self.assertTrue(self.meta(page, 'og:description'))

    def test_listing_page_link_preview_without_a_photo_uses_the_link_card(self):
        lid = self.create('Departamento Roma Norte M')
        s, page, _ = self.web.req('/propiedad/%s' % self.slug_of(lid), host=self.host)
        img = self.meta(page, 'og:image')
        self.assertTrue(img.endswith('/propiedad/%s/tarjeta-enlace.jpg' % self.slug_of(lid)), img)
        self.assertEqual((self.meta(page, 'og:image:width'), self.meta(page, 'og:image:height')), ('1200', '630'))
        s, data, _ = self.raw(urllib.parse.urlsplit(img).path)
        self.assertEqual((s, self.size(data)), (200, ('JPEG', (1200, 630))))   # on Gratis too: it is a page preview, not a card tool
        self.assertIn('$3,500,000 MXN', self.meta(page, 'og:description'))     # no description written: the facts


if __name__ == '__main__':
    unittest.main()
