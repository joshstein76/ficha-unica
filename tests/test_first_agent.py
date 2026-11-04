"""A first real agent walks Ficha Única on a phone: sign up, publish a first property, look at the site, answer the first client.
Each test is one thing that cost trust on that walk and is now fixed (docs/DECISIONS.md, last numbered item)."""
import io
import re
import unittest

from PIL import Image

from llave import db
from tests import web_harness


def jpeg(w=1200, h=800):
    b = io.BytesIO()
    Image.new('RGB', (w, h), (180, 120, 80)).save(b, 'JPEG')
    return b.getvalue()


def multipart(fields, files):
    bnd = 'firstTEST'
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode())
    for k, (fn, data) in files:
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: image/jpeg\r\n\r\n'
                   % (bnd, k, fn)).encode() + data + b'\r\n')
    out.write(('--%s--\r\n' % bnd).encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + bnd


class FirstAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('firstagent')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def agent(self, plan=None, **kw):
        u = self.web.signup(**kw)
        if plan:
            con = db.connect()
            con.execute('UPDATE agencies SET plan=? WHERE id=?', (plan, u['aid']))
            con.commit()
            con.close()
        return u

    def draft(self, u, n_photos=1, files=None):
        """Wizard step 1 -> the new listing id (redirect to step 2)."""
        files = files if files is not None else [('fotos', ('f%d.jpg' % i, jpeg())) for i in range(n_photos)]
        body, ct = multipart({'csrf': u['csrf'], 'operation': 'venta', 'property_type': 'departamento'}, files)
        s, page, h = self.web.req('/nueva', body, u['cookie'], {'Content-Type': ct})
        return s, page, h

    def draft_id(self, u):
        s, _, h = self.draft(u)
        self.assertEqual(s, 303)
        return int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))

    def step2(self, u, lid, **over):
        f = {'csrf': u['csrf'], 'price': '4500000', 'currency': 'MXN', 'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc',
             'estado': 'Ciudad de México', 'm2_built': '85', 'bedrooms': '2', 'bathrooms': '1.5'}
        f.update(over)
        return self.web.req('/nueva/%d/2' % lid, f, u['cookie'])

    def publish(self, u, **over):
        lid = self.draft_id(u)
        s, _, _ = self.step2(u, lid, **over)
        self.assertEqual(s, 303)
        s, _, _ = self.web.req('/nueva/%d/3' % lid, {'csrf': u['csrf'], 'title': 'Departamento en venta en Roma Norte', 'description': 'Bonito.'},
                               u['cookie'])
        self.assertEqual(s, 303)
        return lid

    # ---- price ----
    def test_wizard_refuses_a_zero_negative_or_absurd_price_and_never_crashes(self):
        u = self.agent()
        lid = self.draft_id(u)
        for bad in ('-5', '0', '1e999', 'inf', 'nan', '99999999999999999999999'):
            s, page, _ = self.step2(u, lid, price=bad)
            self.assertEqual(s, 400, bad)
            self.assertRegex(page, r'(Revisa el precio|El precio debe ser un número)', bad)
        self.assertIsNone(self.web.one('SELECT price_cents FROM listings WHERE id=?', lid)['price_cents'])
        s, _, _ = self.step2(u, lid, price='4,500,000')
        self.assertEqual(s, 303)
        self.assertEqual(self.web.one('SELECT price_cents FROM listings WHERE id=?', lid)['price_cents'], 450000000)

    def test_wizard_accepts_an_empty_price_as_to_be_asked(self):
        u = self.agent()
        lid = self.draft_id(u)
        s, _, _ = self.step2(u, lid, price='')
        self.assertEqual(s, 303)
        self.assertIsNone(self.web.one('SELECT price_cents FROM listings WHERE id=?', lid)['price_cents'])

    def test_full_form_refuses_a_negative_price(self):
        u = self.agent()
        form = {'csrf': u['csrf'], 'title': 'Casa en Coyoacán con jardín', 'operation': 'venta', 'property_type': 'casa', 'status': 'borrador',
                'price': '-5', 'currency': 'MXN', 'colonia': 'Del Carmen', 'municipio': 'Coyoacán', 'estado': 'Ciudad de México'}
        s, page, _ = self.web.req('/propiedades/nueva', form, u['cookie'])
        self.assertEqual(s, 400)
        self.assertIn('Revisa el precio', page)
        form['price'] = '3200000'
        s, _, _ = self.web.req('/propiedades/nueva', form, u['cookie'])
        self.assertEqual(s, 303)


if __name__ == '__main__':
    unittest.main()
