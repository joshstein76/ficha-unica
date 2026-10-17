"""End-to-end: signup -> listing -> photos -> publish -> portal feed -> lead -> GHL dry-run outbox -> Bolsa share."""
import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

TMP = tempfile.mkdtemp()
os.environ['LLAVE_DB'] = os.path.join(TMP, 't.db')
os.environ['LLAVE_MEDIA'] = os.path.join(TMP, 'media')
os.environ['LLAVE_PORT'] = '8699'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402

# other test modules may have imported llave.db first: patch the module, never touch data/llave.db
db.DB_PATH = os.environ['LLAVE_DB']
db.MEDIA_DIR = os.environ['LLAVE_MEDIA']
db.PORT = 8699
from llave.web.server import Handler  # noqa: E402

BASE = 'http://127.0.0.1:8699'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(host, path, data=None, cookie=None, ctype=None):
    headers = {'Host': host}
    if cookie:
        headers['Cookie'] = cookie
    if data is not None and ctype is None:
        data = urllib.parse.urlencode(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif ctype:
        headers['Content-Type'] = ctype
    r = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        resp = OPENER.open(r)
        return resp.status, resp.read().decode('utf-8', 'replace'), resp.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode('utf-8', 'replace'), ex.headers


def jpeg(w=1800, h=1200, color=(120, 140, 160)):
    b = io.BytesIO()
    Image.new('RGB', (w, h), color).save(b, 'JPEG')
    return b.getvalue()


def multipart(fields, files):
    bnd = 'llaveTEST'
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode())
    for k, (fn, data) in files:
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: image/jpeg\r\n\r\n'
                   % (bnd, k, fn)).encode() + data + b'\r\n')
    out.write(('--%s--\r\n' % bnd).encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + bnd


class WebFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 8699), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def signup(self, agency, email):
        s, body, h = req('app.fichaunica.localhost', '/registro', {
            'name': 'María López', 'agency': agency, 'whatsapp': '55 1234 5678', 'email': email,
            'password': 'segura1234', 'terms': '1'})
        self.assertEqual(s, 303, body[:300])
        cookie = h['Set-Cookie'].split(';')[0]
        s, body, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)
        return cookie, csrf

    def test_full_flow(self):
        cookie, csrf = self.signup('Casas Roma', 'maria@ejemplo.test')
        con = db.connect()
        a = con.execute("SELECT * FROM agencies WHERE slug='casas-roma'").fetchone()
        self.assertIsNotNone(a)
        # CSRF enforced
        s, _, _ = req('app.fichaunica.localhost', '/propiedades/nueva', {'title': 'x'}, cookie)
        self.assertEqual(s, 403)
        form = {'csrf': csrf, 'title': 'Departamento con terraza en la Roma Norte', 'operation': 'renta',
                'property_type': 'departamento', 'price': '28,000', 'currency': 'MXN', 'status': 'activa',
                'description': 'Luminoso, con terraza privada y cocina abierta. ' * 6, 'm2_built': '85',
                'bedrooms': '2', 'bathrooms': '2', 'parking': '1', 'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc',
                'estado': 'Ciudad de México', 'share_in_bolsa': '1', 'share_split_pct': '50',
                'rentapoliza_offer': '1', 'internal_note': 'NOTA-SECRETA-123', 'amenities': 'Terraza, Gimnasio'}
        s, _, h = req('app.fichaunica.localhost', '/propiedades/nueva', form, cookie)
        self.assertEqual(s, 303)
        lid = int(re.search(r'/propiedades/(\d+)', h['Location']).group(1))
        body, ct = multipart({'csrf': csrf}, [('fotos', ('a%d.jpg' % i, jpeg(color=(i * 30, 100, 150)))) for i in range(5)]
                             + [('fotos', ('chica.jpg', jpeg(300, 300)))])
        s, page, _ = req('app.fichaunica.localhost', '/propiedades/%d/fotos' % lid, body, cookie, ct)
        self.assertEqual(s, 200)
        self.assertIn('5 fotos listas', page)
        self.assertIn('no se pudieron usar', page)
        # public site + listing page with JSON-LD, canonical, RentaPóliza hook
        s, home, _ = req('casas-roma.fichaunica.localhost', '/')
        self.assertEqual(s, 200)
        self.assertIn('Departamento con terraza', home)
        slug = con.execute('SELECT slug FROM listings WHERE id=?', (lid,)).fetchone()['slug']
        s, lp, _ = req('casas-roma.fichaunica.localhost', '/propiedad/' + slug)
        self.assertEqual(s, 200)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', lp, re.S).group(1))
        self.assertEqual(ld['@type'], 'RealEstateListing')
        self.assertEqual(ld['offers']['price'], 28000)
        self.assertIn('rel="canonical"', lp)
        self.assertIn('RentaPóliza', lp)
        self.assertNotIn('NOTA-SECRETA-123', lp)
        s, fi, _ = req('casas-roma.fichaunica.localhost', '/propiedad/%s/ficha' % slug)
        self.assertEqual(s, 200)
        self.assertIn('noindex', fi)
        self.assertNotIn('NOTA-SECRETA-123', fi)
        # portal toggle -> feed
        s, _, _ = req('app.fichaunica.localhost', '/portales/%d/trovit' % lid, {'csrf': csrf}, cookie)
        self.assertEqual(s, 303)
        s, feed, _ = req('casas-roma.fichaunica.localhost', '/feeds/trovit.xml')
        self.assertEqual(s, 200)
        self.assertIn('For Rent', feed)
        self.assertNotIn('NOTA-SECRETA-123', feed)
        s, _, _ = req('app.fichaunica.localhost', '/portales/%d/mercadolibre' % lid, {'csrf': csrf}, cookie)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM outbox WHERE kind='portal.mercadolibre.create'").fetchone()[0], 1)
        # lead from the site: consent required, then stored + GHL dry-run ops
        s, _, _ = req('casas-roma.fichaunica.localhost', '/contacto', {'listing': lid, 'name': 'Ana', 'phone': '5511112222'})
        self.assertEqual(s, 400)
        s, _, h = req('casas-roma.fichaunica.localhost', '/contacto',
                      {'listing': lid, 'name': 'Ana Pérez', 'phone': '55 1111 2222', 'consent': '1', 'message': 'Me interesa'})
        self.assertEqual(s, 303)
        lead = con.execute('SELECT * FROM leads WHERE agency_id=? ORDER BY id DESC', (a['id'],)).fetchone()
        self.assertEqual(lead['phone'], '+525511112222')
        self.assertEqual(lead['ghl_status'], 'dry_run')
        kinds = [r['kind'] for r in con.execute("SELECT kind FROM outbox WHERE ref=?", ('lead:%d' % lead['id'],))]
        self.assertIn('ghl.contact_upsert', kinds)
        self.assertTrue(all(r['status'] == 'dry_run' for r in con.execute('SELECT status FROM outbox')))
        s, leads_page, _ = req('app.fichaunica.localhost', '/clientes', cookie=cookie)
        self.assertIn('Ana Pérez', leads_page)
        # Bolsa: a second agency shares the listing; lead on their site is a 'bolsa' lead, canonical -> owner
        cookie2, csrf2 = self.signup('Hogar Sur', 'pedro@ejemplo.test')
        s, bolsa, _ = req('app.fichaunica.localhost', '/bolsa', cookie=cookie2)
        self.assertIn('Departamento con terraza', bolsa)
        s, _, _ = req('app.fichaunica.localhost', '/bolsa/%d/compartir' % lid, {'csrf': csrf2}, cookie2)
        self.assertEqual(s, 303)
        s, lp2, _ = req('hogar-sur.fichaunica.localhost', '/propiedad/' + slug)
        self.assertEqual(s, 200)
        self.assertIn('<link rel="canonical" href="http://casas-roma.fichaunica.localhost:8699/propiedad/%s">' % slug, lp2)
        s, _, _ = req('hogar-sur.fichaunica.localhost', '/contacto',
                      {'listing': lid, 'name': 'Luis', 'phone': '5533334444', 'consent': '1'})
        self.assertEqual(s, 303)
        n0 = con.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        s, _, _ = req('hogar-sur.fichaunica.localhost', '/contacto', {'listing': lid, 'name': 'Bot', 'phone': '5599990000', 'consent': '1', 'website': 'spam.example'})
        self.assertEqual(s, 303)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM leads').fetchone()[0], n0)
        b = con.execute("SELECT * FROM leads WHERE source='bolsa'").fetchone()
        self.assertIsNotNone(b)
        self.assertEqual(b['owner_agency_id'], a['id'])
        # the sharer's own sitemap must not list the shared listing
        s, sm, _ = req('hogar-sur.fichaunica.localhost', '/sitemap.xml')
        self.assertNotIn(slug, sm)
        # other agency cannot edit the listing
        s, _, _ = req('app.fichaunica.localhost', '/propiedades/%d' % lid, cookie=cookie2)
        self.assertEqual(s, 404)
        con.close()

    def test_import_services_legal(self):
        cookie, csrf = self.signup('Importa Ya', 'imp@ejemplo.test')
        csv_text = 'titulo;precio;colonia;alcaldía;recámaras\nDepartamento luminoso en Narvarte;3,200,000;Narvarte;Benito Juárez;2\nX;1;;;\n'
        s, page, _ = req('app.fichaunica.localhost', '/propiedades/importar', {'csrf': csrf, 'step': 'preview', 'csv': csv_text}, cookie)
        self.assertEqual(s, 200)
        self.assertIn('1 de 2 filas se crean', page)
        con = db.connect()
        aid = con.execute("SELECT id FROM agencies WHERE slug='importa-ya'").fetchone()['id']
        self.assertEqual(con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=?', (aid,)).fetchone()[0], 0)
        s, page, _ = req('app.fichaunica.localhost', '/propiedades/importar', {'csrf': csrf, 'step': 'commit', 'csv': csv_text}, cookie)
        self.assertIn('1 propiedades importadas', page)
        r = con.execute('SELECT * FROM listings WHERE agency_id=?', (aid,)).fetchone()
        self.assertEqual((r['status'], r['estado'], r['price_cents']), ('borrador', 'Ciudad de México', 320000000))
        con.close()
        for path, text in (('/servicios', 'RentaPóliza'), ('/academia', 'Próximamente')):
            s, page, _ = req('app.fichaunica.localhost', path, cookie=cookie)
            self.assertEqual(s, 200)
            self.assertIn(text, page)
        s, page, _ = req('app.fichaunica.localhost', '/terminos')
        self.assertEqual(s, 200)
        self.assertIn('Ciao Bella Marketing', page)

    def test_mercadolibre_connect_demo(self):
        cookie, csrf = self.signup('Conecta ML', 'ml@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/portales/mercadolibre/conectar', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('modo demo', page)
        s, _, _ = req('app.fichaunica.localhost', '/portales/mercadolibre/conectar', {'csrf': csrf, 'demo': '1'}, cookie)
        self.assertEqual(s, 303)
        s, page, _ = req('app.fichaunica.localhost', '/portales', cookie=cookie)
        self.assertIn('demo, sin publicar de verdad', page)
        s, page, _ = req('app.fichaunica.localhost', '/oauth/mercadolibre/callback?state=nope&code=x', cookie=cookie)
        self.assertEqual(s, 400)

    def test_wizard_bolsa_filters_prices(self):
        cookie, csrf = self.signup('Tres Pasos', 'tres@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/nueva?bienvenida=1', cookie=cookie)
        self.assertIn('son 3 pasos', page)
        body, ct = multipart({'csrf': csrf, 'operation': 'renta', 'property_type': 'casa'},
                             [('fotos', ('f%d.jpg' % i, jpeg(color=(10 * i, 90, 120)))) for i in range(3)])
        s, _, h = req('app.fichaunica.localhost', '/nueva', body, cookie, ct)
        self.assertEqual(s, 303)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        s, _, h = req('app.fichaunica.localhost', '/nueva/%d/2' % lid, {'csrf': csrf, 'price': '35000', 'currency': 'MXN',
                      'colonia': 'Del Valle', 'municipio': 'Benito Juárez', 'estado': 'Ciudad de México', 'm2_built': '180', 'bedrooms': '3'}, cookie)
        self.assertEqual(s, 303)
        s, page, _ = req('app.fichaunica.localhost', '/nueva/%d/3' % lid, cookie=cookie)
        self.assertIn('Casa en renta en Del Valle, 180 m², 3 recámaras', page)
        s, _, h = req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Casa en renta en Del Valle, 180 m², 3 recámaras',
                      'description': 'Casa amplia.', 'portales': '1'}, cookie)
        self.assertEqual(s, 303)
        con = db.connect()
        l = con.execute('SELECT * FROM listings WHERE id=?', (lid,)).fetchone()
        self.assertEqual((l['status'], l['slug']), ('activa', 'casa-en-renta-en-del-valle-180-m2-3-recamaras'))
        self.assertEqual(con.execute('SELECT COUNT(*) FROM photos WHERE listing_id=?', (lid,)).fetchone()[0], 3)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM portal_publications WHERE listing_id=? AND enabled=1', (lid,)).fetchone()[0], 2)
        s, page, _ = req('app.fichaunica.localhost', '/nueva/%d/lista' % lid, cookie=cookie)
        self.assertIn('¡Publicada!', page)
        # Bolsa filters (share it first) + price check confirm
        con.execute("UPDATE listings SET share_in_bolsa=1, lat=19.38613, lng=-99.17137, price_date='2026-01-01' WHERE id=?", (lid,))
        con.commit()
        cookie2, csrf2 = self.signup('Busca Bolsa', 'busca@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/bolsa?property_type=casa&max=40000&beds=3', cookie=cookie2)
        self.assertIn('Del Valle', page)
        self.assertIn('id="map"', page)
        self.assertNotIn('19.38613', page)  # pins are snapped to a ~250 m grid, never the exact point
        self.assertIn('19.385', page)
        s, page, _ = req('app.fichaunica.localhost', '/bolsa?max=20000', cookie=cookie2)
        self.assertNotIn('Del Valle', page)
        s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertIn('sin confirmar', page)
        s, page, _ = req('app.fichaunica.localhost', '/precios/%d' % lid, {'csrf': csrf}, cookie)
        self.assertIn('Precio confirmado', page)
        self.assertNotEqual(con.execute('SELECT price_date FROM listings WHERE id=?', (lid,)).fetchone()[0], '2026-01-01')
        s, _, _ = req('app.fichaunica.localhost', '/precios/%d' % lid, {'csrf': csrf2}, cookie2)
        con.close()

    def test_media_traversal_blocked(self):
        s, _, _ = req('app.fichaunica.localhost', '/media/../../etc/passwd')
        self.assertEqual(s, 404)


if __name__ == '__main__':
    unittest.main()
