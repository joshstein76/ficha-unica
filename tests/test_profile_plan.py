"""Agent public profile + plan screens (test mode, never charges)."""
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
PORT = 8697
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
    bnd = 'pfTEST'
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


class ProfilePlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'p.db'), os.path.join(TMP, 'media'), PORT
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

    def signup(self, agency, email):
        s, _, h = req('app.fichaunica.localhost', '/registro', {'name': 'Laura Méndez', 'agency': agency, 'whatsapp': '55 2222 3333',
                                                             'email': email, 'password': 'segura1234', 'terms': '1'})
        self.assertEqual(s, 303)
        cookie = h['Set-Cookie'].split(';')[0]
        _, body, _ = req('app.fichaunica.localhost', '/perfil', cookie=cookie)
        return cookie, re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)

    def test_profile_public_page(self):
        cookie, csrf = self.signup('Casa Laura', 'laura@ejemplo.test')
        body, ct = multipart({'csrf': csrf, 'name': 'Laura Méndez', 'whatsapp': '55 2222 3333', 'zones': 'Coyoacán, Del Valle',
                              'bio': 'Asesora con enfoque en familias.', 'public': '1'}, [('photo', ('yo.jpg', jpeg(800, 600)))])
        s, page, _ = req('app.fichaunica.localhost', '/perfil', body, cookie, ct)
        self.assertEqual(s, 200)
        self.assertIn('Perfil guardado', page)
        con = db.connect()
        u = con.execute("SELECT * FROM users WHERE email='laura@ejemplo.test'").fetchone()
        self.assertEqual(u['slug'], 'laura-mendez')
        self.assertTrue(u['photo_path'].startswith('brand/avatar-'))
        with Image.open(os.path.join(db.MEDIA_DIR, u['photo_path'])) as im:
            self.assertEqual(im.size, (400, 400))
        s, prof, _ = req('casa-laura.fichaunica.localhost', '/asesor/laura-mendez')
        self.assertEqual(s, 200)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', prof, re.S).group(1))
        self.assertEqual((ld['@type'], ld['name']), ('RealEstateAgent', 'Laura Méndez'))
        self.assertIn('Coyoacán', ld['areaServed'])
        s, home, _ = req('casa-laura.fichaunica.localhost', '/')
        self.assertIn('/asesor/laura-mendez', home)
        # hide the profile again -> 404
        s, _, _ = req('app.fichaunica.localhost', '/perfil', {'csrf': csrf, 'name': 'Laura Méndez'}, cookie)
        s, _, _ = req('casa-laura.fichaunica.localhost', '/asesor/laura-mendez')
        self.assertEqual(s, 404)
        con.close()

    def test_plan_change_test_mode(self):
        cookie, csrf = self.signup('Plan Prueba', 'plan@ejemplo.test')
        s, page, _ = req('app.fichaunica.localhost', '/plan', cookie=cookie)
        self.assertIn('$299 MXN', page)
        self.assertIn('$799 MXN', page)
        s, page, _ = req('app.fichaunica.localhost', '/plan/pro', cookie=cookie)
        self.assertIn('MODO PRUEBA', page)
        s, page, _ = req('app.fichaunica.localhost', '/plan/pro', {'csrf': csrf}, cookie)
        self.assertIn('modo prueba, sin cobro', page)
        con = db.connect()
        a = con.execute("SELECT * FROM agencies WHERE slug='plan-prueba'").fetchone()
        self.assertEqual(a['plan'], 'pro')
        self.assertEqual(con.execute("SELECT COUNT(*) FROM audit WHERE action='plan_change_test_mode'").fetchone()[0], 1)
        # downgrade blocked when over the limit
        for i in range(12):
            con.execute("INSERT INTO listings(agency_id, ref, slug, title, colonia, municipio, estado) VALUES (?,?,?,?,?,?,?)",
                        (a['id'], 'P-%d' % i, 'p-%d' % i, 'Propiedad %d' % i, 'Roma', 'Cuauhtémoc', 'CDMX'))
        con.commit()
        s, page, _ = req('app.fichaunica.localhost', '/plan/gratis', {'csrf': csrf}, cookie)
        self.assertEqual(s, 400)
        self.assertIn('Marca algunas como vendidas', page)
        self.assertEqual(con.execute('SELECT plan FROM agencies WHERE id=?', (a['id'],)).fetchone()[0], 'pro')
        con.close()


if __name__ == '__main__':
    unittest.main()
