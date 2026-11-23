"""2026-11-22 phone walk: after a buyer sends the site form, the thank-you page must not promise "te escribimos en breve"
(the agent may never open the panel) and its WhatsApp button must carry the exact property (title + folio).
Money facts on a listing page take two columns so "$3,850,000 MXN" never breaks mid-number."""
import os
import sys
import unittest
import urllib.parse
from html import unescape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import db  # noqa: E402
import web_harness  # noqa: E402


class ThanksCarriesTheProperty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('thankswa')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()
        con = db.connect()
        self.slug = con.execute('SELECT slug FROM agencies WHERE id=?', (self.u['aid'],)).fetchone()[0]
        con.execute("UPDATE agencies SET whatsapp='525512345678' WHERE id=?", (self.u['aid'],))
        self.lid = con.execute("INSERT INTO listings(agency_id, ref, slug, status, title, colonia, municipio, estado, operation, property_type,"
                               " price_cents, currency) VALUES (?, 'T-7','depto-narvarte','activa','Depto en Narvarte','Narvarte','Benito Juárez','CDMX',"
                               "'venta','departamento', 385000000, 'MXN')", (self.u['aid'],)).lastrowid
        con.commit()
        con.close()
        self.host = '%s.fichaunica.localhost' % self.slug

    def wa_text(self, page):
        main = page.split('<main', 1)[1]
        href = unescape(main.split('href="https://wa.me/', 1)[1].split('"', 1)[0])
        return urllib.parse.parse_qs(urllib.parse.urlsplit('https://wa.me/' + href).query)['text'][0]

    def test_form_then_thanks_names_the_listing(self):
        s, _, h = self.web.req('/contacto', {'listing': self.lid, 'name': 'Carla Ruiz', 'phone': '55 4444 5555', 'consent': '1'}, host=self.host)
        self.assertEqual(s, 303)
        loc = urllib.parse.urlsplit(h['Location'])
        s, page, _ = self.web.req(loc.path + '?' + loc.query, host=self.host)
        self.assertEqual(s, 200)
        self.assertNotIn('en breve', page)
        self.assertIn('Depto en Narvarte (folio T-7)', self.wa_text(page))
        self.assertNotIn('Carla', self.wa_text(page))  # nothing personal in the link
        self.assertIn('El mensaje ya lleva la propiedad', page)

    def test_unknown_listing_falls_back_to_plain_message(self):
        s, page, _ = self.web.req('/gracias?l=987654', host=self.host)
        self.assertEqual(s, 200)
        self.assertEqual(self.wa_text(page), 'Hola, acabo de dejar mis datos en su sitio.')
        self.assertNotIn('ya lleva la propiedad', page)
        s, page, _ = self.web.req('/gracias?l=abc', host=self.host)
        self.assertEqual(s, 200)

    def test_price_fact_is_wide(self):
        s, page, _ = self.web.req('/propiedad/depto-narvarte', host=self.host)
        self.assertEqual(s, 200)
        self.assertIn('<div class="wide"><b>$3,850,000 MXN</b><small>Precio</small></div>', page)
        header = page.split('<header', 1)[1].split('</header>', 1)[0]  # the header button names the property too
        self.assertIn('folio%20T-7', header.replace('+', '%20'))


if __name__ == '__main__':
    unittest.main()


class PhotoStepShowsThumbnails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('thumbs')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def test_wizard_has_thumbnail_strip(self):
        u = self.web.signup()
        s, page, _ = self.web.req('/nueva', cookie=u['cookie'])
        self.assertEqual(s, 200)
        self.assertIn('class="thumbs"', page)
        self.assertIn('URL.createObjectURL', page)


class PulsoSitesStayLight(unittest.TestCase):
    def test_light_only_follows_the_look(self):
        from llave.web import site, styles
        a = {'design': 'ciudad', 'accent': '#2F5BEA'}
        old = styles.LOOK
        try:
            styles.LOOK = 'pulso'
            self.assertTrue(site.light_only())
            self.assertNotIn('prefers-color-scheme:dark', styles.site_css(a['design'], a['accent'], dark_mode=not site.light_only()))
            styles.LOOK = 'loteria'
            self.assertFalse(site.light_only())
        finally:
            styles.LOOK = old

    def test_demo_agency_is_noindex_with_bar(self):
        from llave.web import site
        self.assertIn('noindex', site.demo_head({'is_demo': 1}))
        self.assertEqual(site.demo_head({'is_demo': 0}), '')
        self.assertIn('Sitio de ejemplo', site.demo_bar({'is_demo': 1, 'slug': 'casa-norte'}))
