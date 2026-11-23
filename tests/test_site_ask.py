"""The agent-site search bar (LLAVE_SITE_ASK=1): the Spanish parser, the answer shape and limits, the /buscar route (404 off, JSON on,
429 after 60 per IP per 10 minutes) and the guarantee that with the switch off the home page has no trace of it."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from llave import db, site_ask
from llave.web import server, site

PORT = 8771
HOST = 'casa-ask.fichaunica.localhost'
COLONIAS = ['Roma Sur', 'Roma Norte', 'Condesa', 'Benito Juárez']

ROWS = [  # ref, title, operation, type, price pesos, beds, baths, colonia, municipio, status
    ('A1', 'Depa luminoso en Roma Sur', 'venta', 'departamento', 2980000, 2, 1, 'Roma Sur', 'Cuauhtémoc', 'activa'),
    ('A2', 'Depa con balcón en Roma Norte', 'venta', 'departamento', 3900000, 3, 2, 'Roma Norte', 'Cuauhtémoc', 'activa'),
    ('A3', 'Depa en renta cerca del parque', 'renta', 'departamento', 18500, 2, 1, 'Condesa', 'Cuauhtémoc', 'activa'),
    ('A4', 'Casa familiar con jardín', 'venta', 'casa', 6500000, 4, 3, 'Del Valle', 'Benito Juárez', 'apartada'),
    ('A5', 'Terreno plano', 'venta', 'terreno', 1200000, None, None, 'Tlalpan Centro', 'Tlalpan', 'activa'),
    ('A6', 'Oficina pequeña', 'renta', 'oficina', 15000, None, 1, 'Roma Norte', 'Cuauhtémoc', 'activa'),
    ('A7', 'Depa en Roma Sur con terraza', 'venta', 'departamento', 2500000, 2, 2, 'Roma Sur', 'Cuauhtémoc', 'activa'),
    ('A8', 'Casa vendida en Roma', 'venta', 'casa', 2000000, 2, 1, 'Roma Sur', 'Cuauhtémoc', 'vendida'),
    ('A9', 'Borrador en Roma Sur', 'venta', 'departamento', 1000000, 2, 1, 'Roma Sur', 'Cuauhtémoc', 'borrador'),
]


def get(path, ip=None):
    headers = {'Host': HOST}
    if ip:
        headers['X-Forwarded-For'] = ip
    try:
        r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), headers=headers))
        return r.status, r.read().decode('utf-8'), r.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode('utf-8'), ex.headers


class Parse(unittest.TestCase):
    def p(self, q):
        return site_ask.parse(q, COLONIAS)

    def test_beds_and_colonia(self):
        f = self.p('2 recámaras en roma sur')
        self.assertEqual((f['beds'], f['colonia'], f['colonia_tokens']), (2, 'Roma Sur', ['roma', 'sur']))
        self.assertEqual(f['terms'], [])
        self.assertEqual(self.p('3 rec en condesa')['beds'], 3)
        self.assertEqual(self.p('4 habitaciones')['beds'], 4)
        self.assertEqual(self.p('dos recámaras')['beds'], 2)

    def test_rent_type_and_price(self):
        f = self.p('depa en renta hasta 25 mil')
        self.assertEqual((f['operation'], f['type'], f['max_price']), ('renta', 'departamento', 25000))
        for words in ('quiero alquilar', 'rentar algo', 'pago mensual', 'al mes'):
            self.assertEqual(self.p(words)['operation'], 'renta', words)

    def test_sale_and_price_forms(self):
        f = self.p('casa en venta 3.5 mdp')
        self.assertEqual((f['operation'], f['type'], f['max_price']), ('venta', 'casa', 3500000))
        for text, n in (('hasta 3 millones', 3000000), ('3m', 3000000), ('menos de 20 mil', 20000), ('$18,000', 18000),
                        ('3.5 mdp', 3500000), ('$3,200,000', 3200000)):
            self.assertEqual(self.p(text)['max_price'], n, text)

    def test_types_and_baths(self):
        for text, kind in (('depa', 'departamento'), ('departamento', 'departamento'), ('casa', 'casa'), ('terreno', 'terreno'),
                           ('oficina', 'oficina'), ('local comercial', 'local'), ('bodega', 'bodega')):
            self.assertEqual(self.p(text)['type'], kind, text)
        self.assertEqual(self.p('2 baños')['baths'], 2)
        self.assertEqual(self.p('120 m2')['max_price'], None)

    def test_accents_and_case(self):
        a, b = self.p('CASA en JUÁREZ'), self.p('casa en juarez')
        self.assertEqual(a, b)
        self.assertEqual(a['colonia'], 'Juárez')
        self.assertEqual(self.p('Condesa')['colonia'], 'Condesa')

    def test_garbage(self):
        for q in ('', '   ', '!!!???', None):
            f = self.p(q)
            self.assertFalse(site_ask._has_filters(f), q)
        f = self.p('zxqv blorpt')
        self.assertEqual((f['operation'], f['type'], f['beds'], f['max_price'], f['colonia']), (None, None, None, None, ''))
        self.assertEqual(f['terms'], ['zxqv', 'blorpt'])


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT, os.environ.get('LLAVE_SITE_ASK'))
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(cls.tmp, 'ask.db'), os.path.join(cls.tmp, 'media'), PORT
        os.environ.pop('LLAVE_SITE_ASK', None)
        cls.con = db.connect()
        db.init(cls.con)
        server.signup(cls.con, {'name': 'María López', 'agency': 'Casa Ask', 'whatsapp': '55 1234 5678', 'email': 'ask@ejemplo.test',
                                'password': 'segura1234', 'terms': '1'})
        cls.con.execute("UPDATE agencies SET design='ciudad', accent='#1f4e79', plan='ia' WHERE id=1")
        for n, r in enumerate(ROWS):
            ref, title, op, kind, price, beds, baths, col, mun, st = r
            cls.con.execute(
                "INSERT INTO listings(agency_id,ref,slug,title,description,status,operation,property_type,price_cents,currency,"
                "bedrooms,bathrooms,m2_built,colonia,municipio,estado,updated_at) VALUES (1,?,?,?,?,?,?,?,?,'MXN',?,?,80,?,?,'CDMX',?)",
                (ref, 'slug-' + ref.lower(), title, 'Descripción de ' + title, st, op, kind, price * 100, beds, baths, col, mun,
                 '2026-11-0%d 10:00:00' % (n + 1)))
        cls.con.commit()
        cls.agency = cls.con.execute('SELECT * FROM agencies WHERE id=1').fetchone()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.con.close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT, old = cls.saved
        if old is None:
            os.environ.pop('LLAVE_SITE_ASK', None)
        else:
            os.environ['LLAVE_SITE_ASK'] = old

    def tearDown(self):
        os.environ.pop('LLAVE_SITE_ASK', None)


class Answer(Base):
    def test_shape(self):
        r = site_ask.answer(self.con, self.agency, '2 recámaras en roma')
        self.assertEqual(r['kind'], 'homes')
        self.assertEqual(r['q'], '2 recámaras en roma')
        self.assertEqual(sorted(r), ['kind', 'listings', 'q', 'summary', 'total'])
        self.assertEqual(r['total'], 3)  # A1, A2 (3 rec counts as 2+), A7; sold + draft never appear
        first = r['listings'][0]
        self.assertEqual(sorted(first), ['baths', 'beds', 'id', 'img', 'label', 'm2', 'n', 'p', 'rent', 'u'])
        self.assertTrue(first['u'].startswith('http') and first['u'].endswith('/propiedad/' + first['u'].rsplit('/', 1)[1]))
        self.assertIn(HOST.split('.')[0], first['u'])
        self.assertEqual(r['summary'], '3 propiedades · 2+ rec. · Roma')

    def test_filters_end_to_end(self):
        r = site_ask.answer(self.con, self.agency, 'depa en venta 2 rec hasta 3 mdp roma sur')
        self.assertEqual([h['n'] for h in r['listings']], ['Depa en Roma Sur con terraza', 'Depa luminoso en Roma Sur'])
        self.assertEqual(r['summary'], '2 departamentos en venta · 2+ rec. · hasta $3M · Roma Sur')
        self.assertEqual(r['listings'][1]['p'], '$2,980,000 MXN')
        self.assertEqual(r['listings'][1]['label'], 'En venta')
        self.assertFalse(r['listings'][1]['rent'])

    def test_rent(self):
        r = site_ask.answer(self.con, self.agency, 'depa en renta hasta 25 mil')
        self.assertEqual([(h['p'], h['label'], h['rent']) for h in r['listings']], [('$18,500 MXN al mes', 'En renta', True)])
        self.assertEqual(r['summary'], '1 departamento en renta · hasta $25 mil')

    def test_only_public_status(self):
        r = site_ask.answer(self.con, self.agency, 'casa')
        self.assertEqual([h['n'] for h in r['listings']], ['Casa familiar con jardín'])  # apartada shows, vendida does not

    def test_nothing_found(self):
        for q in ('palacio con alberca en narnia', '', '???', 'casa hasta 100 mil'):
            r = site_ask.answer(self.con, self.agency, q)
            self.assertEqual((r['kind'], r['listings'], r['total'], r['summary']), ('none', [], 0, ''), q)

    def test_limits(self):
        for n in range(10, 22):
            self.con.execute(
                "INSERT INTO listings(agency_id,ref,slug,title,status,operation,property_type,price_cents,currency,colonia,municipio,updated_at) "
                "VALUES (1,?,?,?,'activa','venta','casa',100000000,'MXN','Polanco','Miguel Hidalgo','2026-11-05 10:00:00')",
                ('P%d' % n, 'polanco-%d' % n, 'Casa en Polanco %d' % n))
        self.con.commit()
        try:
            r = site_ask.answer(self.con, self.agency, 'casa en polanco')
            self.assertEqual((len(r['listings']), r['total']), (6, 12))
            r = site_ask.answer(self.con, self.agency, 'casa en polanco', phone=True)
            self.assertEqual((len(r['listings']), r['total']), (4, 12))
        finally:
            self.con.execute("DELETE FROM listings WHERE ref LIKE 'P%'")
            self.con.commit()


class Route(Base):
    def test_off_is_404(self):
        s, _, _ = get('/buscar?q=casa')
        self.assertEqual(s, 404)

    def test_on_returns_json(self):
        os.environ['LLAVE_SITE_ASK'] = '1'
        s, body, h = get('/buscar?q=2+rec%C3%A1maras+en+roma&ph=1', ip='10.1.1.1')
        self.assertEqual(s, 200)
        self.assertIn('application/json', h['Content-Type'])
        self.assertEqual(h['Cache-Control'], 'no-store')
        d = json.loads(body)
        self.assertEqual(d['kind'], 'homes')
        print('\n/buscar?q=2 recámaras en roma ->', json.dumps(d, ensure_ascii=False, indent=1))
        s, body, _ = get('/buscar', ip='10.1.1.1')
        self.assertEqual(json.loads(body)['kind'], 'none')

    def test_not_on_the_app_host(self):
        os.environ['LLAVE_SITE_ASK'] = '1'
        try:
            r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d/buscar?q=casa' % PORT, headers={'Host': 'app.fichaunica.localhost'}))
            status, body = r.status, r.read().decode()
        except urllib.error.HTTPError as ex:
            status, body = ex.code, ex.read().decode()
        self.assertNotIn('"kind"', body)

    def test_rate_limit(self):
        os.environ['LLAVE_SITE_ASK'] = '1'
        for i in range(60):
            self.assertEqual(get('/buscar?q=casa', ip='10.9.9.9')[0], 200, i)
        s, _, h = get('/buscar?q=casa', ip='10.9.9.9')
        self.assertEqual(s, 429)
        self.assertEqual(h['Retry-After'], '600')
        self.assertEqual(h['Cache-Control'], 'no-store')
        self.assertEqual(get('/buscar?q=casa', ip='10.9.9.10')[0], 200)  # another visitor is not affected


class Ui(Base):
    def test_off_has_no_trace(self):
        html = site.home(self.con, self.agency)
        self.assertNotIn('idxb-ask', html)
        self.assertNotIn('/buscar', html)
        self.assertNotIn('idxb-ask', get('/')[1])

    def test_on_has_the_bar(self):
        os.environ['LLAVE_SITE_ASK'] = '1'
        html = site.home(self.con, self.agency)
        for cls in ('idxb-ask-bar', 'idxb-ask-icon', 'idxb-ask-input', 'idxb-ask-ex', 'idxb-ask-go', 'idxb-ask-answer',
                    '--idxb-ask-btn:#1f4e79', '--idxb-ask-btn-fg', '--idxb-ask-rad', '--idxb-ask-ink', '--idxb-ask-font'):
            self.assertIn(cls, html, cls)
        self.assertIn('2 recámaras en Roma', html)
        self.assertIn('depa en renta hasta 25 mil', html)
        self.assertNotIn('placeholder', html.split('idxb-ask-input')[1].split('>')[0])  # examples are painted, never in the input
        self.assertNotIn('value=', html.split('idxb-ask-input')[1].split('>')[0])
        self.assertIn('prefers-reduced-motion', html)
        self.assertIn('pointer-events:none', html)
        self.assertIn('No encontré nada con esas palabras. Pruebe con otras, o escríbame y le ayudo.', html)
        self.assertIn('https://wa.me/525512345678', html)
        # the bar sits under the hero, before the listings
        self.assertLess(html.index('</section><div class="in"><style>'), html.index('<h2>Propiedades</h2>'))

    def test_on_only_changes_the_bar(self):
        off = site.home(self.con, self.agency)
        os.environ['LLAVE_SITE_ASK'] = '1'
        on = site.home(self.con, self.agency)
        bar = on[on.index('<div class="in"><style>.idxb-ask'):]
        bar = bar[:bar.index('</script></div></div>') + len('</script></div></div>')]
        self.assertEqual(on.replace(bar, '', 1), off)


if __name__ == '__main__':
    unittest.main()


class SpokenAmounts(unittest.TestCase):
    """2026-11-23 cross-apply from IDX Bloom ("900 mil" read wrong there): spoken amounts and ranges never become search words."""
    def test_words_and_ranges(self):
        cases = {'hasta un millón': 1000000, 'medio millón': 500000, 'un millón y medio': 1500000, 'dos millones': 2000000,
                 'entre 2 y 3 millones': 3000000, 'entre 2 millones y 3 millones': 3000000, 'entre 15 y 20 mil': 20000,
                 'menos de 900 mil': 900000}
        for q, n in cases.items():
            f = site_ask.parse(q)
            self.assertEqual(f['max_price'], n, q)
            self.assertEqual(f['terms'], [], q)
