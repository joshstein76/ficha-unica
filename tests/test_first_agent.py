"""A first real agent walks Ficha Única on a phone: sign up, publish a first property, look at the site, answer the first client.
Each test is one thing that cost trust on that walk and is now fixed (docs/DECISIONS.md, last numbered item)."""
import datetime
import io
import re
import unittest
from unittest import mock

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

    # ---- the second property on Gratis ----
    def test_plan_limit_warning_links_to_the_plans_page(self):
        u = self.agent()
        self.publish(u)
        for path in ('/nueva', '/propiedades/nueva'):
            s, page, _ = self.web.req(path, cookie=u['cookie'])
            self.assertEqual(s, 200, path)
            self.assertIn('Llegaste al límite de tu plan (1 propiedad)', page, path)
            self.assertIn('<a href="/plan">Ver planes</a>', page, path)

    # ---- Inicio on a phone ----
    def test_first_week_rows_never_drop_the_text_under_the_tick(self):
        from llave.web import panel, styles
        h = panel.first_week(1, 2, [(True, 'Agrega tu WhatsApp para recibir clientes', '/perfil'), (False, 'Sube tu primera propiedad', '/nueva')])
        self.assertEqual(h.count('class="row step"'), 2)
        self.assertIn('<span class="pill ok">✓</span><span>Agrega tu WhatsApp para recibir clientes</span>', h)
        self.assertIn('.row.step{flex-wrap:nowrap', styles.PANEL)
        self.assertIn('.row.step .pill{flex:none}', styles.PANEL)

    def test_inicio_of_an_agent_with_no_properties_leads_with_the_next_step(self):
        u = self.agent()
        s, page, _ = self.web.req('/', cookie=u['cookie'])
        self.assertEqual(s, 200)
        self.assertIn('<h2>Sube tu primera propiedad</h2>', page)
        self.assertLess(page.index('Sube tu primera propiedad'), page.index('class="stats"'))
        self.assertIn('<a class="btn" href="/nueva">Empezar</a>', page)
        self.publish(u)
        s, page, _ = self.web.req('/', cookie=u['cookie'])
        self.assertNotIn('<h2>Sube tu primera propiedad</h2>', page)

    # ---- sign-up ----
    def test_signup_says_the_password_minimum_and_lets_you_read_the_terms(self):
        s, page, _ = self.web.req('/registro')
        self.assertEqual(s, 200)
        self.assertIn('(mínimo 8 caracteres)', page)
        self.assertIn('<a href="/terminos" target="_blank" rel="noopener">términos</a>', page)
        self.assertIn('<a href="/privacidad" target="_blank" rel="noopener">aviso de privacidad</a> (borrador).', page)  # "(borrador)" stays until the lawyer
        for path in ('/terminos', '/privacidad'):
            self.assertEqual(self.web.req(path)[0], 200, path)

    def test_wrong_password_keeps_the_email_in_the_field(self):
        u = self.agent()
        s, page, _ = self.web.req('/entrar', {'email': u['email'], 'password': 'otra-clave-123'})
        self.assertEqual(s, 401)
        self.assertIn('Correo o contraseña incorrectos.', page)
        self.assertIn('name="email" type="email" value="%s"' % u['email'], page)
        s, page, _ = self.web.req('/entrar', {'email': 'x"><b>@ejemplo.test', 'password': 'otra-clave-123'})
        self.assertNotIn('<b>@ejemplo.test', page)

    # ---- a free pilot plan ----
    def test_plan_page_says_a_pilot_plan_is_free_and_when_it_ends(self):
        u = self.agent(plan='pro')
        con = db.connect()
        today = datetime.date.today()
        con.execute('UPDATE agencies SET plan_until=? WHERE id=?', ((today + datetime.timedelta(days=58)).isoformat(), u['aid']))
        con.commit()
        s, page, _ = self.web.req('/plan', cookie=u['cookie'])
        self.assertRegex(page, r'<p class="small">Tu plan Pro es un piloto gratis hasta el \d{1,2} \w{3} \d{4}\.</p>')
        con.execute('UPDATE agencies SET plan_until=? WHERE id=?', ((today - datetime.timedelta(days=3)).isoformat(), u['aid']))
        con.commit()
        s, page, _ = self.web.req('/plan', cookie=u['cookie'])
        self.assertRegex(page, r'<p class="small">Tu piloto gratis del plan Pro terminó el \d{1,2} \w{3} \d{4}\.</p>')
        con.execute("UPDATE agencies SET plan_until=NULL WHERE id=?", (u['aid'],))
        con.commit()
        self.assertNotIn('piloto gratis', self.web.req('/plan', cookie=u['cookie'])[1])
        con.execute("UPDATE agencies SET plan_until=?, stripe_subscription_id='sub_test' WHERE id=?", ((today + datetime.timedelta(days=5)).isoformat(), u['aid']))
        con.commit()
        self.assertNotIn('piloto gratis', self.web.req('/plan', cookie=u['cookie'])[1])  # a paying agent is never told it is a free pilot
        con.close()
        gratis = self.agent()
        self.assertNotIn('piloto gratis', self.web.req('/plan', cookie=gratis['cookie'])[1])

    # ---- the first client ----
    def test_lead_card_shows_the_phone_the_client_left(self):
        u = self.agent(agency='Casa Cliente')
        lid = self.publish(u)
        s, _, h = self.web.req('/contacto', {'listing': lid, 'name': 'Carlos Cliente', 'phone': '55 0000 0002', 'consent': '1',
                                             'message': 'Hola, me interesa.'}, host=self.site_host(u))
        self.assertEqual(s, 303)
        s, page, _ = self.web.req('/clientes', cookie=u['cookie'])
        self.assertIn('<a href="tel:+525500000002">+52 55 0000 0002</a>', page)
        s, page, _ = self.web.req('/', cookie=u['cookie'])
        self.assertIn('<a href="tel:+525500000002">+52 55 0000 0002</a>', page)

    # ---- dates ----
    def test_price_date_is_the_mexico_city_day_not_the_server_clock_day(self):
        self.assertEqual(db.today_cdmx(), (datetime.datetime.utcnow() - datetime.timedelta(hours=6)).date())
        u = self.agent(agency='Casa Noche')
        with mock.patch.object(db, 'today_cdmx', return_value=datetime.date(2026, 11, 3)):
            lid = self.publish(u)
            self.assertEqual(self.web.one('SELECT price_date FROM listings WHERE id=?', lid)['price_date'], '2026-11-03')
            s, page, _ = self.web.req('/propiedad/%s' % self.web.one('SELECT slug FROM listings WHERE id=?', lid)['slug'], host=self.site_host(u))
            self.assertIn('Precio confirmado el 3 nov 2026', page)
            form = {'csrf': u['csrf'], 'title': 'Departamento en venta en Roma Norte', 'operation': 'venta', 'property_type': 'departamento',
                    'status': 'activa', 'price': '4000000', 'currency': 'MXN', 'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México'}
            self.assertEqual(self.web.req('/propiedades/%d' % lid, form, u['cookie'])[0], 200)
            self.assertEqual(self.web.one('SELECT price_date FROM listings WHERE id=?', lid)['price_date'], '2026-11-03')

    # ---- photos ----
    def test_too_small_photo_says_its_size_and_what_to_do(self):
        u = self.agent()
        s, page, _ = self.draft(u, files=[('fotos', ('chica.jpg', jpeg(300, 200)))])
        self.assertEqual(s, 400)
        self.assertIn('La foto es muy pequeña (300 × 200 px): cada lado debe medir al menos 600 px. Sube la original del celular.', page)

    def test_wizard_says_when_only_some_of_the_photos_were_used(self):
        u = self.agent()
        s, _, h = self.draft(u, files=[('fotos', ('ok.jpg', jpeg())), ('fotos', ('chica.jpg', jpeg(300, 200))), ('fotos', ('ok2.jpg', jpeg(1000, 700)))])
        self.assertEqual(s, 303)
        self.assertTrue(h['Location'].endswith('/2?mal=1'), h['Location'])
        s, page, _ = self.web.req(h['Location'], cookie=u['cookie'])
        self.assertIn('2 fotos listas.', page)
        self.assertIn('1 foto no se pudo usar: cada una debe ser JPG, PNG o WebP y medir al menos 600 px por lado.', page)
        # all photos fine: no warning and a clean redirect
        u2 = self.agent()
        s, _, h = self.draft(u2, n_photos=2)
        self.assertTrue(h['Location'].endswith('/2'), h['Location'])
        self.assertNotIn('no se pudo usar', self.web.req(h['Location'], cookie=u2['cookie'])[1])
        # a hand-made query cannot inject markup or crash
        s, page, _ = self.web.req(h['Location'] + '?mal=<b>x</b>', cookie=u2['cookie'])
        self.assertEqual(s, 200)
        self.assertNotIn('<b>x</b>', page)

    def test_one_photo_reads_one_foto_lista(self):
        u = self.agent()
        s, _, h = self.draft(u, n_photos=1)
        page = self.web.req(h['Location'], cookie=u['cookie'])[1]
        self.assertIn('<p class="muted">1 foto lista.</p>', page)
        self.assertNotIn('1 fotos', page)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        body, ct = multipart({'csrf': u['csrf']}, [('fotos', ('a.jpg', jpeg(900, 700)))])
        s, page, _ = self.web.req('/propiedades/%d/fotos' % lid, body, u['cookie'], {'Content-Type': ct})
        self.assertEqual(s, 200)
        self.assertIn('1 foto lista.', page)

    def test_inicio_cards_do_not_promise_what_the_plan_does_not_include(self):
        gratis = self.agent()
        page = self.web.req('/', cookie=gratis['cookie'])[1]
        self.assertIn('Publicaciones para tus redes cada semana. Viene en el plan Pro + IA.', page)
        self.assertIn('Visitas, clientes y tu tiempo de respuesta. Viene en el plan Pro.', page)
        self.assertNotIn('5 publicaciones listas', page)
        pro = self.agent(plan='pro')
        page = self.web.req('/', cookie=pro['cookie'])[1]
        self.assertIn('Visitas, clientes y tu tiempo de respuesta.</span>', page)
        self.assertIn('Publicaciones para tus redes cada semana. Viene en el plan Pro + IA.', page)
        ia = self.agent(plan='ia')
        page = self.web.req('/', cookie=ia['cookie'])[1]
        self.assertIn('5 publicaciones listas para Instagram y Facebook.', page)
        self.assertNotIn('Viene en el plan', page)

    def test_new_agent_site_does_not_claim_a_city_the_agent_never_chose(self):
        u = self.agent(agency='Casa Tapatía', email='tapatia@ejemplo.test')
        self.assertEqual(self.web.one('SELECT city FROM agencies WHERE id=?', u['aid'])['city'], '')
        self.publish(u)
        page = self.web.req('/', host=self.site_host(u))[1]
        self.assertIn('© Casa Tapatía · México', page)
        self.assertNotIn('Ciudad de México</', page.split('<footer')[1])
        self.assertIn('"areaServed": "México"', page)
        self.assertIn('placeholder="Ej. Guadalajara"', self.web.req('/sitio', cookie=u['cookie'])[1])
        con = db.connect()
        con.execute("UPDATE agencies SET city='Guadalajara' WHERE id=?", (u['aid'],))
        con.commit()
        con.close()
        self.assertIn('© Casa Tapatía · Guadalajara', self.web.req('/', host=self.site_host(u))[1])

    def test_listing_page_swipe_hint_only_when_there_is_more_than_one_photo(self):
        u = self.agent(agency='Casa Galería')
        lid = self.publish(u)                       # one photo
        slug = self.web.one('SELECT slug FROM listings WHERE id=?', lid)['slug']
        page = self.web.req('/propiedad/' + slug, host=self.site_host(u))[1]
        self.assertNotIn('desliza', page)
        self.assertNotIn('1 fotos', page)
        body, ct = multipart({'csrf': u['csrf']}, [('fotos', ('b.jpg', jpeg(1000, 700))), ('fotos', ('c.jpg', jpeg(1100, 700)))])
        self.assertEqual(self.web.req('/propiedades/%d/fotos' % lid, body, u['cookie'], {'Content-Type': ct})[0], 200)
        page = self.web.req('/propiedad/' + slug, host=self.site_host(u))[1]
        self.assertIn('3 fotos · desliza →', page)


if __name__ == '__main__':
    unittest.main()
