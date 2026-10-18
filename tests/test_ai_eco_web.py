"""AI helpers, valuation, ecosystem webhook + redeem, team invites (web level)."""
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402
from llave.web.server import Handler  # noqa: E402

TMP = tempfile.mkdtemp()
PORT = 8693
BASE = 'http://127.0.0.1:%d' % PORT


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
    try:
        r = OPENER.open(urllib.request.Request(BASE + path, data=data, headers=headers))
        return r.status, r.read().decode('utf-8', 'replace'), r.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode('utf-8', 'replace'), ex.headers


def multipart(fields, files):
    bnd = 'aeTEST'
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode())
    for k, (fn, data) in files:
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: image/jpeg\r\n\r\n'
                   % (bnd, k, fn)).encode() + data + b'\r\n')
    out.write(('--%s--\r\n' % bnd).encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + bnd


def jpeg(w, h):
    b = io.BytesIO()
    Image.new('RGB', (w, h), (90, 120, 150)).save(b, 'JPEG')
    return b.getvalue()



class AIEcoWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'ae.db'), os.path.join(TMP, 'media'), PORT
        os.environ.pop('LLAVE_AI_LIVE', None)
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def agency(self, slug, email, plan=None):
        s, _, h = req('app.fichaunica.localhost', '/registro', {'name': 'Elena Mora', 'agency': slug.replace('-', ' ').title(),
                      'whatsapp': '55 8888 9999', 'email': email, 'password': 'segura1234', 'terms': '1'})
        cookie = h['Set-Cookie'].split(';')[0]
        if plan:
            con = db.connect(); con.execute('UPDATE agencies SET plan=? WHERE slug=?', (plan, slug)); con.commit(); con.close()
        _, body, _ = req('app.fichaunica.localhost', '/nueva', cookie=cookie)
        return cookie, re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)

    def publish(self, cookie, csrf, colonia='Del Valle', price='5000000', m2='120'):
        b, ct = multipart({'csrf': csrf, 'operation': 'venta', 'property_type': 'departamento'}, [('fotos', ('a.jpg', jpeg(1600, 1200)))])
        _, _, h = req('app.fichaunica.localhost', '/nueva', b, cookie, ct)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        req('app.fichaunica.localhost', '/nueva/%d/2' % lid, {'csrf': csrf, 'price': price, 'colonia': colonia, 'municipio': 'Benito Juárez',
            'estado': 'Ciudad de México', 'm2_built': m2, 'bedrooms': '2'}, cookie)
        req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Departamento en venta en %s %s' % (colonia, lid), 'description': 'x'}, cookie)
        return lid

    def test_ai_helpers_and_kit(self):
        c, k = self.agency('ia-ayuda', 'ia@ejemplo.test')
        lid = self.publish(c, k)
        s, page, _ = req('app.fichaunica.localhost', '/propiedades/%d' % lid, cookie=c)
        self.assertIn('Ayuda inteligente', page)
        s, page, _ = req('app.fichaunica.localhost', '/propiedades/%d/ia-texto' % lid, {'csrf': k}, cookie=c)
        self.assertEqual(s, 200)
        self.assertIn('a partir de tus datos', page)            # template mode (AI off by default)
        self.assertIn('Versión en inglés', page)
        s, _, _ = req('app.fichaunica.localhost', '/propiedades/%d/ordenar-fotos' % lid, {'csrf': k}, cookie=c)
        self.assertEqual(s, 303)
        s, page, _ = req('app.fichaunica.localhost', '/que-publicar', cookie=c)
        self.assertEqual(s, 200)
        self.assertIn('tarjeta-post.jpg', page)

    def test_valuation(self):
        c, k = self.agency('valua-ya', 'valua@ejemplo.test')
        for i, (p, m) in enumerate((('4000000', '100'), ('4400000', '110'), ('5200000', '120'))):
            self.publish(c, k, 'Narvarte', p, m)
        s, page, _ = req('valua-ya.fichaunica.localhost', '/vende')
        self.assertIn('¿Cuánto vale su propiedad?', page)
        s, page, _ = req('valua-ya.fichaunica.localhost', '/vende', {'operation': 'venta', 'property_type': 'departamento', 'colonia': 'Narvarte',
                         'municipio': 'Benito Juárez', 'm2': '105', 'name': 'Raúl', 'phone': '5511223344', 'consent': '1'})
        self.assertIn('Rango orientativo', page)
        s, page, _ = req('valua-ya.fichaunica.localhost', '/vende', {'operation': 'venta', 'property_type': 'casa', 'colonia': 'Tlalpan Centro',
                         'municipio': 'Tlalpan', 'm2': '200', 'name': 'Rosa', 'phone': '5511223355', 'consent': '1'})
        self.assertIn('no hay suficientes propiedades comparables', page)
        s, _, _ = req('valua-ya.fichaunica.localhost', '/vende', {'colonia': 'X', 'municipio': 'Y', 'm2': '50', 'name': 'Z', 'phone': '5511223366'})
        self.assertEqual(s, 400)                                  # consent enforced server-side
        con = db.connect()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM leads WHERE source='vendedor'").fetchone()[0], 2)
        con.close()

    def test_eco_webhook_and_redeem(self):
        from llave import eco
        c, k = self.agency('eco-casas', 'eco@ejemplo.test')
        lid = self.publish(c, k)
        body = json.dumps({'event': 'poliza.emitida', 'folio': 'RP-1001', 'agent_email': 'eco@ejemplo.test'}).encode()
        def post(raw, sig, ts):
            r = urllib.request.Request(BASE + '/api/eco/rentapoliza', data=raw, headers={'Host': 'app.fichaunica.localhost',
                                       'Content-Type': 'application/json', 'X-Eco-Signature': sig, 'X-Eco-Timestamp': ts})
            try:
                resp = OPENER.open(r); return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as ex:
                return ex.code, json.loads(ex.read())
        s, out = post(body, 'sha256=x', '1')
        self.assertEqual((s, out['code']), (503, 'no_configurado'))
        os.environ['LLAVE_ECO_SECRET_RENTAPOLIZA'] = 'secreto-de-prueba-123'
        try:
            s, out = post(body, 'sha256=bad', '1')
            self.assertEqual(s, 401)
            import time
            ts = str(int(time.time()))
            sig = eco.sign('secreto-de-prueba-123', body, ts)
            s, out = post(body, sig if sig.startswith('sha256=') else 'sha256=' + sig, ts)
            self.assertEqual((s, out['code']), (200, 'confirmado'))
            s, out = post(body, sig if sig.startswith('sha256=') else 'sha256=' + sig, ts)
            self.assertEqual(out['code'], 'duplicado')
        finally:
            os.environ.pop('LLAVE_ECO_SECRET_RENTAPOLIZA', None)
        s, page, _ = req('app.fichaunica.localhost', '/servicios', cookie=c)
        self.assertIn('Tus créditos', page)
        s, page, _ = req('app.fichaunica.localhost', '/servicios/canjear/destacar_7d', {'csrf': k, 'listing': lid}, cookie=c)
        self.assertIn('canjeado', page)
        con = db.connect()
        self.assertTrue(eco.active_boost(con, lid))
        self.assertEqual(eco.balance(con, con.execute("SELECT id FROM agencies WHERE slug='eco-casas'").fetchone()[0]), 10)
        con.close()

    def test_team_invite(self):
        c, k = self.agency('equipo-grande', 'jefa@ejemplo.test', plan='agencia')
        s, page, _ = req('app.fichaunica.localhost', '/equipo', {'csrf': k}, cookie=c)
        link = re.search(r'/unirse/([A-Za-z0-9_-]+)', page).group(1)
        s, page, _ = req('app.fichaunica.localhost', '/unirse/' + link)
        self.assertIn('Únete a Equipo Grande', page)
        s, _, h = req('app.fichaunica.localhost', '/unirse/' + link, {'name': 'Tomás Gil', 'whatsapp': '5544443333',
                      'email': 'tomas@ejemplo.test', 'password': 'segura1234'})
        self.assertEqual(s, 303)
        con = db.connect()
        u = con.execute("SELECT * FROM users WHERE email='tomas@ejemplo.test'").fetchone()
        self.assertEqual((u['role'], u['agency_id']), ('agent', con.execute("SELECT id FROM agencies WHERE slug='equipo-grande'").fetchone()[0]))
        con.close()
        s, _, _ = req('app.fichaunica.localhost', '/unirse/' + link)
        self.assertEqual(s, 404)                                  # single use


if __name__ == '__main__':
    unittest.main()
