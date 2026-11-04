"""Footer of every agent site: 'Sitio creado con Ficha Única · Crea el tuyo gratis'. The second link goes to the app's sign-up with the
agency as referrer (/registro?ref=<slug>), and a sign-up made through it is recorded in agencies.referred_by (docs/DECISIONS.md #17)."""
import re
import unittest
import urllib.parse

from llave import db
from llave.web import site, styles
from tests import web_harness

SITE_DESIGNS = ('residencia', 'ciudad', 'costa', 'loteria')


class FooterSignup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('footsignup')
        cls.host = cls.web.signup(agency='Casas Roma')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def slug(self):
        return self.web.one('SELECT slug FROM agencies WHERE id=?', self.host['aid'])['slug']

    def site_host(self):
        return '%s.%s' % (self.slug(), db.BASE_DOMAIN)

    def test_footer_text_and_both_links_on_every_design(self):
        for d in SITE_DESIGNS:
            con = db.connect()
            con.execute('UPDATE agencies SET design=? WHERE id=?', (d, self.host['aid']))
            con.commit()
            con.close()
            for path in ('/', '/aviso-de-privacidad'):
                s, page, _ = self.web.req(path, host=self.site_host())
                self.assertEqual(s, 200, (d, path))
                foot = re.search(r'<footer class="sf">.*</footer>', page, re.S).group(0)
                self.assertRegex(foot, r'Sitio creado con <a href="[^"]+\?source=sitio-casas-roma" rel="nofollow">Ficha Única</a>'
                                       r' · <a href="[^"]+/registro\?ref=casas-roma" rel="nofollow">Crea el tuyo gratis</a></span>', (d, path))
                self.assertEqual(foot.count('/registro?ref='), 1, (d, path))

    def test_link_points_at_the_app_host_with_the_agency_slug(self):
        s, page, _ = self.web.req('/', host=self.site_host())
        href = re.search(r'<a href="([^"]+)" rel="nofollow">Crea el tuyo gratis</a>', page).group(1)
        self.assertEqual(href, '%s/registro?ref=%s' % (db.origin('app'), self.slug()))
        self.assertEqual(href, site.signup_url(self.slug()))
        self.assertTrue(urllib.parse.urlparse(href).netloc.startswith('app.'))

    def test_signup_through_the_footer_link_records_the_referrer(self):
        _, page, _ = self.web.req('/', host=self.site_host())
        href = re.search(r'<a href="([^"]+)" rel="nofollow">Crea el tuyo gratis</a>', page).group(1)
        u = urllib.parse.urlparse(href)
        s, form, _ = self.web.req('%s?%s' % (u.path, u.query))          # the app's own sign-up page, as the link opens it
        self.assertEqual(s, 200)
        self.assertIn('<input type="hidden" name="ref" value="%s">' % self.slug(), form)
        ref = re.search(r'name="ref" value="([^"]*)"', form).group(1)
        s, _, _ = self.web.req('/registro', {'name': 'Luis Ramos', 'agency': 'Hogares Norte', 'whatsapp': '55 1111 2222',
                                             'email': 'luis@ejemplo.test', 'password': 'segura1234', 'terms': '1', 'ref': ref})
        self.assertEqual(s, 303)
        row = self.web.one("SELECT referred_by FROM agencies WHERE slug='hogares-norte'")
        self.assertEqual(row['referred_by'], self.host['aid'])

    def test_375px_footer_can_wrap_in_every_design(self):
        """No browser here: the footer row is a wrapping flex box in the base CSS and in Lotería, so the longer credit line wraps
        instead of pushing the page sideways."""
        self.assertIn('footer.sf .in{display:flex;flex-wrap:wrap', styles.SITE_BASE)
        self.assertIn('footer.sf .in>span{display:inline-flex;align-items:center;flex-wrap:wrap', styles.LOTERIA_CSS)


if __name__ == '__main__':
    unittest.main()
