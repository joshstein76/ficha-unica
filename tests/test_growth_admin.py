"""Referral loop, Instagram cards route, admin view."""
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
PORT = 8696
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
    bnd = 'grTEST'
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



class GrowthAdmin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'g.db'), os.path.join(TMP, 'media'), PORT
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

    def signup(self, agency, email, ref=''):
        s, _, h = req('app.fichaunica.localhost', '/registro', {'name': 'Pedro Solís', 'agency': agency, 'whatsapp': '55 4444 5555',
                                                             'email': email, 'password': 'segura1234', 'terms': '1', 'ref': ref})
        self.assertEqual(s, 303)
        cookie = h['Set-Cookie'].split(';')[0]
        _, body, _ = req('app.fichaunica.localhost', '/nueva', cookie=cookie)
        return cookie, re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)

    def publish(self, cookie, csrf, colonia):
        body, ct = multipart({'csrf': csrf, 'operation': 'venta', 'property_type': 'casa'}, [('fotos', ('a.jpg', jpeg(1600, 1200)))])
        _, _, h = req('app.fichaunica.localhost', '/nueva', body, cookie, ct)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        req('app.fichaunica.localhost', '/nueva/%d/2' % lid, {'csrf': csrf, 'price': '6500000', 'colonia': colonia,
            'municipio': 'Coyoacán', 'estado': 'Ciudad de México', 'm2_built': '220', 'bedrooms': '3'}, cookie)
        req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Casa en venta en %s con jardín' % colonia,
            'description': 'Casa con jardín.'}, cookie)
        return lid

    def test_referral_bonus(self):
        c1, k1 = self.signup('Invita Mucho', 'invita@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/invitar', cookie=c1)
        self.assertIn('/registro?ref=invita-mucho', page)
        s, reg, _ = req('app.fichaunica.localhost', '/registro?ref=invita-mucho')
        self.assertIn('value="invita-mucho"', reg)
        s, land, _ = req('fichaunica.localhost', '/?ref=invita-mucho')
        self.assertIn('registro?ref=invita-mucho', land)
        c2, k2 = self.signup('Colega Nuevo', 'colega@ejemplo.test', ref='invita-mucho')
        con = db.connect()
        a1 = con.execute("SELECT * FROM agencies WHERE slug='invita-mucho'").fetchone()
        a2 = con.execute("SELECT * FROM agencies WHERE slug='colega-nuevo'").fetchone()
        self.assertEqual(a2['referred_by'], a1['id'])
        self.assertEqual(db.listing_limit(con, a1), 10)          # not yet: colleague hasn't published
        self.publish(c2, k2, 'Santa Catarina')
        self.assertEqual(db.listing_limit(con, a1), 15)          # +5 once the colleague publishes
        s, page, _ = req('app.fichaunica.localhost', '/invitar', cookie=c1)
        self.assertIn('publicó ✓', page)
        con.close()

    def test_cards_and_admin(self):
        c, k = self.signup('Tarjetas Pro', 'tarjetas@ejemplo.test')
        lid = self.publish(c, k, 'Del Carmen')
        con = db.connect()
        slug = con.execute('SELECT slug FROM listings WHERE id=?', (lid,)).fetchone()['slug']
        for kind, size in (('post', (1080, 1350)), ('historia', (1080, 1920))):
            r = OPENER.open(urllib.request.Request(BASE + '/propiedad/%s/tarjeta-%s.jpg' % (slug, kind),
                                                   headers={'Host': 'tarjetas-pro.fichaunica.localhost'}))
            self.assertEqual(r.headers['Content-Type'], 'image/jpeg')
            with Image.open(io.BytesIO(r.read())) as im:
                self.assertEqual(im.size, size)
        s, _, _ = req('tarjetas-pro.fichaunica.localhost', '/propiedad/no-existe/tarjeta-post.jpg')
        self.assertEqual(s, 404)
        # admin: hidden for normal users, visible for admins
        s, _, _ = req('app.fichaunica.localhost', '/admin', cookie=c)
        self.assertEqual(s, 404)
        con.execute("UPDATE users SET role='admin' WHERE email='tarjetas@ejemplo.test'")
        con.commit()
        req('tarjetas-pro.fichaunica.localhost', '/contacto', {'listing': lid, 'name': 'Rosa Díaz', 'phone': '5577778888', 'consent': '1'})
        con.execute("UPDATE leads SET created_at=datetime('now','-20 minutes')")
        con.commit()
        s, page, _ = req('app.fichaunica.localhost', '/admin', cookie=c)
        self.assertEqual(s, 200)
        self.assertIn('Clientes en riesgo', page)
        self.assertIn('Rosa', page)
        self.assertNotIn('5577778888', page)   # admin view never shows full client phones
        con.close()


if __name__ == '__main__':
    unittest.main()
