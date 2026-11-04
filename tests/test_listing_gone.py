"""A sold or rented listing's page answers 410 Gone (noindex) so Google drops it; a paused one, a draft or an unknown slug stay 404."""
import unittest

from llave import db
from tests import web_harness


class ListingGone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('listinggone')
        cls.host = cls.web.signup(agency='Casas Gone')
        con = db.connect()
        for slug, status in (('casa-activa', 'activa'), ('casa-vendida', 'vendida'), ('casa-rentada', 'rentada'),
                             ('casa-pausada', 'pausada'), ('casa-borrador', 'borrador')):
            con.execute("INSERT INTO listings(agency_id, ref, slug, status, title, colonia, municipio, estado) VALUES (?,?,?,?,?,?,?,?)",
                        (cls.host['aid'], slug, slug, status, 'Casa ' + status, 'Roma', 'CDMX', 'CDMX'))
        con.commit()
        con.close()
        slug = cls.web.one('SELECT slug FROM agencies WHERE id=?', cls.host['aid'])['slug']
        cls.site = '%s.%s' % (slug, db.BASE_DOMAIN)

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def get(self, slug):
        return self.web.req('/propiedad/' + slug, host=self.site)

    def test_sold_and_rented_are_gone(self):
        for slug in ('casa-vendida', 'casa-rentada'):
            s, page, h = self.get(slug)
            self.assertEqual(s, 410, slug)
            self.assertEqual(h['X-Robots-Tag'], 'noindex')
            self.assertIn('ya no está disponible', page)

    def test_active_is_found_and_the_rest_stay_404(self):
        self.assertEqual(self.get('casa-activa')[0], 200)
        for slug in ('casa-pausada', 'casa-borrador', 'no-existe'):
            self.assertEqual(self.get(slug)[0], 404, slug)

    def test_another_agencys_sold_slug_is_not_gone_here(self):
        other = self.web.signup(agency='Otra Agencia')
        slug = self.web.one('SELECT slug FROM agencies WHERE id=?', other['aid'])['slug']
        s, _, _ = self.web.req('/propiedad/casa-vendida', host='%s.%s' % (slug, db.BASE_DOMAIN))
        self.assertEqual(s, 404)


if __name__ == '__main__':
    unittest.main()
