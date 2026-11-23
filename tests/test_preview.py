"""'Ve tu página' instant preview (2026-11-23): off by default, POST only, nothing stored, values escaped, button pre-fills sign-up."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import db  # noqa: E402
from llave.web import preview  # noqa: E402
import web_harness  # noqa: E402


class Preview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('preview')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def counts(self):
        con = db.connect()
        try:
            return tuple(con.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0] for t in ('agencies', 'users', 'listings', 'leads'))
        finally:
            con.close()

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {'LLAVE_PREVIEW': ''}):
            s, page, _ = self.web.req('/vista-previa')
        self.assertNotIn('Ve tu página', page)

    def test_preview_stores_nothing_and_escapes(self):
        before = self.counts()
        with mock.patch.dict(os.environ, {'LLAVE_PREVIEW': '1'}):
            s, page, _ = self.web.req('/vista-previa')
            self.assertEqual(s, 200)
            self.assertIn('Ve tu página', page)
            s, page, _ = self.web.req('/vista-previa', {'name': 'Daniela <b>Ríos</b>', 'zona': 'Del Valle'})
            self.assertEqual(s, 200)
            self.assertIn('Daniela &lt;b&gt;Ríos&lt;/b&gt;', page)
            self.assertNotIn('<b>Ríos</b>', page)
            self.assertIn('Bienes raíces en Del Valle', page)
            self.assertIn('noindex', page)
            self.assertIn('no guardamos nada', page)
            s, page, _ = self.web.req('/vista-previa', {'name': 'Daniela', 'zona': ''})
            self.assertEqual(s, 400)
            s, page, _ = self.web.req('/vista-previa', {'paso': 'registro', 'name': 'Daniela Ríos', 'agency': 'Casas DR', 'zona': 'Del Valle'})
            self.assertEqual(s, 200)
            self.assertIn('value="Daniela Ríos"', page)
            self.assertIn('value="Casas DR"', page)
            self.assertIn('action="/registro"', page)
        self.assertEqual(self.counts(), before)


if __name__ == '__main__':
    unittest.main()
