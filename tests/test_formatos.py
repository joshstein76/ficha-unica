import os
import unittest

from llave import formatos
from llave.web.common import e


class Formatos(unittest.TestCase):
    def test_every_placeholder_is_a_field(self):
        import re
        for f in formatos.FORMATOS:
            names = {n for n, *_ in f['fields']}
            used = set(re.findall(r'\{(\w+)\}', ' '.join(f['body'])))
            self.assertLessEqual(used, names, f['key'])

    def test_render_escapes_and_blanks(self):
        f = formatos.BY_KEY['apartado']
        vals = {n: '' for n, *_ in f['fields']}
        vals['comprador'] = '<script>x</script>'
        out = ' '.join(formatos.render_lines(f, vals, e))
        self.assertNotIn('<script>', out)
        self.assertIn('__________', out)

    def test_search_and_tags(self):
        self.assertEqual([x['key'] for x in formatos.search('apartado')], ['apartado'])
        self.assertTrue(formatos.search('', 'Venta'))
        self.assertEqual(formatos.search('zzz'), [])

    def test_off_unless_flag(self):
        os.environ.pop('LLAVE_FORMATOS', None)
        self.assertFalse(formatos.enabled())
        os.environ['LLAVE_FORMATOS'] = '1'
        try:
            self.assertTrue(formatos.enabled())
        finally:
            os.environ.pop('LLAVE_FORMATOS', None)

    def test_no_competitor_names(self):
        blob = str(formatos.FORMATOS).lower()
        for bad in ('easybroker', 'lokation', 'wiggot', 'tokko', 'realtors'):
            self.assertNotIn(bad, blob)


if __name__ == '__main__':
    unittest.main()
