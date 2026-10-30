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

    def signup(self, agency, email, plan='ia'):
        s, body, h = req('app.fichaunica.localhost', '/registro', {
            'name': 'María López', 'agency': agency, 'whatsapp': '55 1234 5678', 'email': email,
            'password': 'segura1234', 'terms': '1'})
        self.assertEqual(s, 303, body[:300])
        cookie = h['Set-Cookie'].split(';')[0]
        if plan != 'gratis':  # functional tests run on the top plan; plan gates have their own test
            con = db.connect(); con.execute('UPDATE agencies SET plan=? WHERE id=(SELECT agency_id FROM users WHERE email=?)', (plan, email)); con.commit(); con.close()
        s, body, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)
        return cookie, csrf

    def test_novedades_unread_clears(self):
        cookie, _ = self.signup('Casas Novedades', 'nov@ejemplo.test')
        s, home, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertIn('nuevas', home)
        s, page, _ = req('app.fichaunica.localhost', '/novedades', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('Tu panel, más fácil', page)
        s, home, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertNotIn('nuevas', home)

    def test_formatos_gate_and_doc(self):
        import os
        cookie, csrf = self.signup('Casas Formatos', 'fmt@ejemplo.test')
        os.environ.pop('LLAVE_FORMATOS', None)
        s, page, _ = req('app.fichaunica.localhost', '/formatos', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('abogado', page)
        self.assertNotIn('Recibo de apartado', page)
        os.environ['LLAVE_FORMATOS'] = '1'
        try:
            s, page, _ = req('app.fichaunica.localhost', '/formatos', cookie=cookie)
            self.assertIn('Recibo de apartado', page)
            s, form, _ = req('app.fichaunica.localhost', '/formatos/apartado', cookie=cookie)
            self.assertIn('María López', form)  # prefilled agent
            s, doc, _ = req('app.fichaunica.localhost', '/formatos/apartado', {'csrf': csrf, 'comprador': 'Ana <b>', 'monto': '50,000'}, cookie)
            self.assertEqual(s, 200)
            self.assertIn('50,000 MXN', doc)
            self.assertIn('Ana &lt;b&gt;', doc)
            self.assertIn('No sustituye asesoría legal', doc)
        finally:
            os.environ.pop('LLAVE_FORMATOS', None)

    def test_calculadoras_render(self):
        cookie, csrf = self.signup('Casas Calc', 'calc@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/calculadoras', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('Lo que recibe tu vendedor', page)
        s, page, _ = req('app.fichaunica.localhost', '/calculadoras/neta', cookie=cookie)
        self.assertIn('value="16"', page)
        s, page, _ = req('app.fichaunica.localhost', '/calculadoras/neta?precio=1000000&comision=5&iva=16&hipoteca=&adeudos=&otros=', cookie=cookie)
        self.assertIn('$942,000.00 MXN', page)
        self.assertIn('confirma montos con tu notario', page)
        s, page, _ = req('app.fichaunica.localhost', '/calculadoras/compra?precio=2000000&isai=3&honorarios=40000&avaluo=&otros=', cookie=cookie)
        self.assertIn('$100,000.00 MXN', page)
        s, page, _ = req('app.fichaunica.localhost', '/calculadoras/compra?precio=2000000&isai=', cookie=cookie)
        self.assertIn('ISAI', page)
        self.assertNotIn('Total de gastos', page)

    def test_operaciones_flow_and_isolation(self):
        cookie, csrf = self.signup('Casas Ops', 'ops@ejemplo.test')
        cookie2, csrf2 = self.signup('Casas Otras', 'otras@ejemplo.test')
        host = 'app.fichaunica.localhost'
        s, _, _ = req(host, '/operaciones/nueva', {'client_name': 'Ana', 'kind': 'venta'}, cookie)
        self.assertEqual(s, 403)  # CSRF
        s, page, _ = req(host, '/operaciones/nueva', {'csrf': csrf, 'client_name': '', 'kind': 'venta'}, cookie)
        self.assertEqual(s, 400)
        s, _, h = req(host, '/operaciones/nueva', {'csrf': csrf, 'client_name': 'Ana <b>', 'kind': 'venta', 'amount': '2,500,000'}, cookie)
        self.assertEqual(s, 303)
        url = h['Location']
        s, page, _ = req(host, url, cookie=cookie)
        self.assertIn('Ana &lt;b&gt;', page)
        self.assertIn('Certificado de libertad de gravamen', page)
        self.assertIn('/formatos', page)
        did = url.rsplit('/', 1)[1]
        s, _, _ = req(host, url + '/etapa', {'stage': 'oferta'}, cookie)
        self.assertEqual(s, 403)
        s, _, _ = req(host, url + '/etapa', {'csrf': csrf, 'stage': 'oferta'}, cookie)
        self.assertEqual(s, 303)
        s, page, _ = req(host, '/operaciones?etapa=oferta', cookie=cookie)
        self.assertIn('Ana &lt;b&gt;', page)
        con = db.connect()
        tid = con.execute('SELECT id FROM deal_tasks WHERE deal_id=? ORDER BY position LIMIT 1', (did,)).fetchone()[0]
        s, _, _ = req(host, '%s/tarea/%d' % (url, tid), {'csrf': csrf, 'done': '1'}, cookie)
        self.assertEqual(s, 303)
        self.assertEqual(con.execute('SELECT done FROM deal_tasks WHERE id=?', (tid,)).fetchone()[0], 1)
        # the other agency sees nothing and changes nothing
        s, page, _ = req(host, url, cookie=cookie2)
        self.assertEqual(s, 404)
        s, page, _ = req(host, '/operaciones', cookie=cookie2)
        self.assertNotIn('Ana', page)
        s, _, _ = req(host, url + '/etapa', {'csrf': csrf2, 'stage': 'cerrada'}, cookie2)
        self.assertEqual(s, 404)
        s, _, _ = req(host, '%s/tarea/%d' % (url, tid), {'csrf': csrf2, 'done': '0'}, cookie2)
        self.assertEqual(s, 404)
        row = con.execute('SELECT stage FROM deals WHERE id=?', (did,)).fetchone()
        self.assertEqual(row[0], 'oferta')
        self.assertEqual(con.execute('SELECT done FROM deal_tasks WHERE id=?', (tid,)).fetchone()[0], 1)
        con.close()

    def test_app_host_never_indexed_but_shares_well(self):
        s, body, h = req('app.fichaunica.localhost', '/robots.txt')
        self.assertEqual(s, 200)
        self.assertIn('Disallow: /stripe/', body)
        self.assertIn('text/plain', h['Content-Type'])
        for path in ('/registro', '/entrar', '/robots.txt'):
            s, page, h = req('app.fichaunica.localhost', path)
            self.assertEqual((s, h['X-Robots-Tag']), (200, 'noindex'), path)
        s, page, _ = req('app.fichaunica.localhost', '/registro')
        self.assertIn('og:image', page)
        self.assertIn('<meta name="description"', page)
        self.assertEqual(page.count('<meta name="description"'), 1)
        self.signup('Indexable Sur', 'idx@ejemplo.test')
        for path in ('/', '/robots.txt'):  # agent sites must stay indexable
            s, _, h = req('indexable-sur.fichaunica.localhost', path)
            self.assertEqual(s, 200, path)
            self.assertIsNone(h.get('X-Robots-Tag'), path)

    def test_plan_page_wording(self):
        cookie, _ = self.signup('Plan Claro', 'plan@ejemplo.test', plan='gratis')
        s, page, _ = req('app.fichaunica.localhost', '/plan', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('Usas 0 de 1 propiedad.', page)
        self.assertIn('<b>$0</b>', page)
        self.assertIn('para siempre', page)
        s, page, _ = req('app.fichaunica.localhost', '/registro')
        self.assertIn('autocomplete="tel"', page)

    def test_signup_guard_honeypot_cap_login_lockout(self):
        from llave.web import server
        base = {'name': 'Ana Ruiz', 'whatsapp': '55 1234 5678', 'password': 'segura1234', 'terms': '1'}
        s, _, h = req('app.fichaunica.localhost', '/registro', dict(base, agency='Bot Casas', email='bot@ejemplo.test', website='x'))
        self.assertEqual(s, 200)
        self.assertNotIn('Set-Cookie', h)
        old = server.SIGNUP_DAILY_CAP, server.LOGIN_FAILS_15MIN
        try:
            server.SIGNUP_DAILY_CAP = 0
            s, page, _ = req('app.fichaunica.localhost', '/registro', dict(base, agency='Casas Llenas', email='llena@ejemplo.test'))
            self.assertEqual(s, 429)
            self.assertIn('lugares del día', page)
            server.LOGIN_FAILS_15MIN = 2
            for _ in range(2):
                self.assertEqual(req('app.fichaunica.localhost', '/entrar', {'email': 'nadie@ejemplo.test', 'password': 'mala1234'})[0], 401)
            self.assertEqual(req('app.fichaunica.localhost', '/entrar', {'email': 'nadie@ejemplo.test', 'password': 'mala1234'})[0], 429)
        finally:
            server.SIGNUP_DAILY_CAP, server.LOGIN_FAILS_15MIN = old
            con = db.connect(); con.execute('DELETE FROM rate_events'); con.commit(); con.close()

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
        # aggregators are partner-only: the toggle does nothing and Portales says why; the open feed has the listing
        s, _, _ = req('app.fichaunica.localhost', '/portales/%d/trovit' % lid, {'csrf': csrf}, cookie)
        self.assertEqual(s, 303)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM portal_publications WHERE listing_id=? AND portal='trovit'", (lid,)).fetchone()[0], 0)
        s, pp, _ = req('app.fichaunica.localhost', '/portales', cookie=cookie)
        self.assertNotIn('/portales/%d/trovit' % lid, pp)
        self.assertIn('solo recibe anuncios de portales', pp)
        s, feed, _ = req('casas-roma.fichaunica.localhost', '/feeds/llave_open.xml')
        self.assertEqual(s, 200)
        self.assertIn('renta', feed)
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
        for path, text in (('/servicios', 'RentaPóliza'), ('/academia', 'Tu primera propiedad en 10 minutos'), ('/academia/rentas-seguras', 'no asesoría legal')):
            s, page, _ = req('app.fichaunica.localhost', path, cookie=cookie)
            self.assertEqual(s, 200)
            self.assertIn(text, page)
        s, page, _ = req('app.fichaunica.localhost', '/terminos')
        self.assertEqual(s, 200)
        self.assertIn('Ciao Bella Marketing', page)

    def test_kit_home_and_five_tabs_behind_switch(self):
        cookie, csrf = self.signup('Kit Home', 'kit@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertNotIn('agent-dash.js', page)  # off by default: old Home
        os.environ['LLAVE_KIT_HOME'] = '1'
        try:
            s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
            self.assertEqual(s, 200)
            self.assertIn('/_s/agent-dash.js', page)
            self.assertNotIn('[PREMIO]', page)
            m = re.search(r'data:(\{.*\}),onAction', page, re.S)
            data = json.loads(m.group(1))
            self.assertEqual([t['label'] for t in data['tabs']], ['Inicio', 'Clientes', 'Mi sitio', 'Crecer', 'Cuenta'])
            s, page, _ = req('app.fichaunica.localhost', '/academia', cookie=cookie)
            self.assertEqual(page.count('<nav class="tabs"'), 1)
            self.assertIn('aria-current="page"', page)
            for name in ('agent-dash.js', 'agent-dash.css', 'ficha-unica-brand.json', 'fu-mark.svg'):
                s, _p, _ = req('app.fichaunica.localhost', '/_s/' + name)
                self.assertEqual(s, 200, name)
            # kit 1.2.0 (logo) / 1.1.0: first week as a checklist, lesson 1 as the next step, no alerts on a fresh account
            self.assertIn('/_s/agent-dash.js?v=1.2.0', req('app.fichaunica.localhost', '/', cookie=cookie)[1])
            self.assertIn('"logo": "/_s/fu-mark.svg"', req('app.fichaunica.localhost', '/', cookie=cookie)[1])
            self.assertEqual(len(data['checklist']['items']), 5)
            self.assertNotIn('done', data['checklist']['items'][0])  # no property yet
            self.assertEqual(data['next']['cta']['href'], '/academia/primera-propiedad')
            self.assertNotIn('alerts', data)
            con = db.connect()
            aid = con.execute("SELECT agency_id FROM users WHERE email='kit@ejemplo.test'").fetchone()[0]
            con.execute("INSERT INTO leads (agency_id, name, phone, status, created_at) VALUES (?, 'Ana', '5512345678', 'nuevo', datetime('now','-1 hour'))", (aid,))
            con.commit(); con.close()
            s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
            data = json.loads(re.search(r'data:(\{.*\}),onAction', page, re.S).group(1))
            self.assertEqual(data['alerts'][0]['tone'], 'warn')
            self.assertIn('1 cliente sin respuesta', data['alerts'][0]['title'])
        finally:
            os.environ.pop('LLAVE_KIT_HOME', None)

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
        # no aggregator takes an agent's feed directly, so publishing switches nothing on (2026-10-29)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM portal_publications WHERE listing_id=? AND enabled=1', (lid,)).fetchone()[0], 0)
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

    def test_inbox_status_reminder_stats(self):
        cookie, csrf = self.signup('Rapida Respuesta', 'rapida@ejemplo.test')
        body, ct = multipart({'csrf': csrf, 'operation': 'venta', 'property_type': 'departamento'}, [('fotos', ('a.jpg', jpeg()))])
        s, _, h = req('app.fichaunica.localhost', '/nueva', body, cookie, ct)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        req('app.fichaunica.localhost', '/nueva/%d/2' % lid, {'csrf': csrf, 'price': '3000000', 'colonia': 'Narvarte',
            'municipio': 'Benito Juárez', 'estado': 'Ciudad de México'}, cookie)
        req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Departamento en venta en Narvarte', 'description': 'x'}, cookie)
        con = db.connect()
        slug = con.execute('SELECT slug FROM listings WHERE id=?', (lid,)).fetchone()['slug']
        for ua in ('Mozilla/5.0', 'Mozilla/5.0', 'Googlebot/2.1'):
            r = urllib.request.Request(BASE + '/propiedad/' + slug, headers={'Host': 'rapida-respuesta.fichaunica.localhost', 'User-Agent': ua})
            OPENER.open(r).read()
        self.assertEqual(con.execute('SELECT SUM(views) FROM listing_views WHERE listing_id=?', (lid,)).fetchone()[0], 2)
        req('rapida-respuesta.fichaunica.localhost', '/contacto', {'listing': lid, 'name': 'Carla Ruiz', 'phone': '5512121212', 'consent': '1'})
        lead = con.execute('SELECT * FROM leads WHERE listing_id=?', (lid,)).fetchone()
        con.execute("UPDATE leads SET created_at=datetime('now','-9 minutes') WHERE id=?", (lead['id'],))
        con.commit()
        s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertIn('sin respuesta hace más de 5 minutos', page)
        from llave import lead_watch
        self.assertEqual(lead_watch.remind(con), 1)
        self.assertEqual(lead_watch.remind(con), 0)
        s, _, h = req('app.fichaunica.localhost', '/clientes/%d/whatsapp' % lead['id'], cookie=cookie)
        self.assertEqual(s, 303)
        self.assertTrue(h['Location'].startswith('https://wa.me/525512121212?text=Hola%20Carla'))
        l2 = con.execute('SELECT * FROM leads WHERE id=?', (lead['id'],)).fetchone()
        self.assertEqual(l2['status'], 'contactado')
        self.assertIsNotNone(l2['first_response_at'])
        req('app.fichaunica.localhost', '/clientes/%d/estado' % lead['id'], {'csrf': csrf, 'status': 'cita'}, cookie)
        self.assertEqual(con.execute('SELECT status FROM leads WHERE id=?', (lead['id'],)).fetchone()[0], 'cita')
        s, _, h = req('app.fichaunica.localhost', '/clientes/%d/seguimiento' % lead['id'], {'csrf': csrf, 'dias': '1'}, cookie)
        self.assertEqual(s, 303)
        self.assertIsNotNone(con.execute('SELECT follow_up_on FROM leads WHERE id=?', (lead['id'],)).fetchone()[0])
        s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertNotIn('para dar seguimiento hoy', page)  # tomorrow, not yet due
        con.execute("UPDATE leads SET follow_up_on=date('now','-1 day') WHERE id=?", (lead['id'],)); con.commit()
        s, page, _ = req('app.fichaunica.localhost', '/', cookie=cookie)
        self.assertIn('1 cliente para dar seguimiento hoy', page)
        s, page, _ = req('app.fichaunica.localhost', '/clientes?estado=hoy', cookie=cookie)
        self.assertIn('Carla Ruiz', page)
        self.assertIn('Seguimiento hoy · 1', page)
        req('app.fichaunica.localhost', '/clientes/%d/seguimiento' % lead['id'], {'csrf': 'bad', 'dias': '0'}, cookie)
        self.assertIsNotNone(con.execute('SELECT follow_up_on FROM leads WHERE id=?', (lead['id'],)).fetchone()[0])  # CSRF blocks
        req('app.fichaunica.localhost', '/clientes/%d/seguimiento' % lead['id'], {'csrf': csrf, 'dias': '0'}, cookie)
        self.assertIsNone(con.execute('SELECT follow_up_on FROM leads WHERE id=?', (lead['id'],)).fetchone()[0])
        s, page, _ = req('app.fichaunica.localhost', '/estadisticas', cookie=cookie)
        self.assertEqual(s, 200)
        self.assertIn('Visitas a tus propiedades', page)
        con.close()

    def test_media_traversal_blocked(self):
        s, _, _ = req('app.fichaunica.localhost', '/media/../../etc/passwd')
        self.assertEqual(s, 404)


if __name__ == '__main__':
    unittest.main()
