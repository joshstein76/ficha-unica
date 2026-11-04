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

    # ---- one wrong number must not wipe the rest ----
    def test_wizard_step_2_shows_what_was_typed_again_after_a_bad_price(self):
        u = self.agent()
        lid = self.draft_id(u)
        s, page, _ = self.step2(u, lid, price='4.5 millones', colonia='Narvarte <Poniente>', m2_built='85', bedrooms='3', bathrooms='2')
        self.assertEqual(s, 400)
        self.assertIn('El precio debe ser un número', page)
        self.assertIn('value="4.5 millones"', page)
        self.assertIn('value="Narvarte &lt;Poniente&gt;"', page)
        self.assertIn('name="municipio" value="Cuauhtémoc"', page)
        self.assertIn('name="m2_built" inputmode="decimal" value="85"', page)
        self.assertIn('name="bedrooms" inputmode="numeric" value="3"', page)
        self.assertIn('name="bathrooms" inputmode="decimal" value="2"', page)

    def test_full_form_shows_what_was_typed_again_after_an_error(self):
        u = self.agent()
        form = {'csrf': u['csrf'], 'title': 'Casa en Coyoacán con jardín', 'operation': 'renta', 'property_type': 'casa', 'status': 'activa',
                'price': 'ocho mil', 'currency': 'USD', 'colonia': 'Del Carmen', 'municipio': 'Coyoacán', 'estado': 'Ciudad de México',
                'bedrooms': '4', 'amenities': 'Jardín, Alberca', 'pets': '1', 'description': 'Con jardín grande.', 'maps': 'https://maps.example/x'}
        s, page, _ = self.web.req('/propiedades/nueva', form, u['cookie'])
        self.assertEqual(s, 400)
        for frag in ('value="Casa en Coyoacán con jardín"', 'value="ocho mil"', 'value="Del Carmen"', 'name="bedrooms" value="4"',
                     'value="Jardín, Alberca"', 'Con jardín grande.</textarea>', 'value="https://maps.example/x"'):
            self.assertIn(frag, page, frag)
        self.assertRegex(page, r'<option value="renta" selected>')
        self.assertRegex(page, r'<option value="USD" selected>')
        self.assertRegex(page, r'name="pets" value="1" checked')
        self.assertNotRegex(page, r'name="furnished" value="1" checked')
        self.assertEqual(self.web.one('SELECT COUNT(*) AS n FROM listings WHERE agency_id=?', u['aid'])['n'], 0)

    def test_editing_a_saved_listing_with_a_bad_price_keeps_the_edit(self):
        u = self.agent()
        lid = self.publish(u)
        form = {'csrf': u['csrf'], 'title': 'Título nuevo de la propiedad', 'operation': 'venta', 'property_type': 'departamento',
                'status': 'activa', 'price': '-1', 'currency': 'MXN', 'colonia': 'Condesa', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México'}
        s, page, _ = self.web.req('/propiedades/%d' % lid, form, u['cookie'])
        self.assertEqual(s, 400)
        self.assertIn('value="Título nuevo de la propiedad"', page)
        self.assertIn('value="Condesa"', page)
        self.assertEqual(self.web.one('SELECT colonia FROM listings WHERE id=?', lid)['colonia'], 'Roma Norte')  # nothing was saved

    # ---- the public site of a brand-new agent ----
    def site_host(self, u):
        return '%s.%s' % (self.web.one('SELECT slug FROM agencies WHERE id=?', u['aid'])['slug'], db.BASE_DOMAIN)

    def test_new_agent_site_has_no_empty_sobre_nosotros_until_there_is_text(self):
        u = self.agent(agency='Casa Vacía')
        self.publish(u)
        s, page, _ = self.web.req('/', host=self.site_host(u))
        self.assertEqual(s, 200)
        self.assertNotIn('Sobre nosotros', page)
        con = db.connect()
        con.execute("UPDATE agencies SET about='Somos un equipo de la Roma.' WHERE id=?", (u['aid'],))
        con.commit()
        con.close()
        s, page, _ = self.web.req('/', host=self.site_host(u))
        self.assertIn('<h2>Sobre nosotros</h2><p class="desc">Somos un equipo de la Roma.</p>', page)


if __name__ == '__main__':
    unittest.main()
