"""Public directory (free-leads source) + buyer alerts."""
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
PORT = 8694
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
    bnd = 'paTEST'
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



class PortalAlerts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'pa.db'), os.path.join(TMP, 'media'), PORT
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

    def agency_with_listing(self, slug, colonia, price, op='venta'):
        s, _, h = req('app.fichaunica.localhost', '/registro', {'name': 'Sofía Rivas', 'agency': slug.replace('-', ' ').title(),
                      'whatsapp': '55 6666 7777', 'email': slug + '@ejemplo.test', 'password': 'segura1234', 'terms': '1'})
        cookie = h['Set-Cookie'].split(';')[0]
        _, body, _ = req('app.fichaunica.localhost', '/nueva', cookie=cookie)
        csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)
        b, ct = multipart({'csrf': csrf, 'operation': op, 'property_type': 'departamento'}, [('fotos', ('a.jpg', jpeg(1600, 1200)))])
        _, _, h = req('app.fichaunica.localhost', '/nueva', b, cookie, ct)
        lid = int(re.search(r'/nueva/(\d+)/2', h['Location']).group(1))
        req('app.fichaunica.localhost', '/nueva/%d/2' % lid, {'csrf': csrf, 'price': str(price), 'colonia': colonia,
            'municipio': 'Benito Juárez', 'estado': 'Ciudad de México', 'bedrooms': '2'}, cookie)
        return lid, cookie, csrf

    def test_directory_and_general_request(self):
        lid, cookie, csrf = self.agency_with_listing('narvarte-casas', 'Narvarte', 3500000)
        s, page, _ = req('fichaunica.localhost', '/propiedades')
        self.assertNotIn('Departamento en venta en Narvarte', page)          # still a draft: not listed
        req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Departamento en venta en Narvarte', 'description': 'x'}, cookie)
        s, page, _ = req('fichaunica.localhost', '/propiedades?colonia=Narvarte')
        self.assertEqual(s, 200)
        self.assertIn('Departamento en venta en Narvarte', page)
        self.assertIn('narvarte-casas.fichaunica.localhost', page)           # card links to the agency's own page
        s, page, _ = req('fichaunica.localhost', '/propiedades?colonia=Polanco')
        self.assertNotIn('Departamento en venta en Narvarte', page)
        s, page, _ = req('fichaunica.localhost', '/busco', {'name': 'Marta', 'phone': '5512340000', 'consent': '1',
                                                         'message': 'Busco departamento en Narvarte, hasta 4 millones.'})
        self.assertIn('Un asesor de la zona', page)
        con = db.connect()
        r = con.execute('SELECT * FROM portal_requests').fetchone()
        a = con.execute("SELECT id FROM agencies WHERE slug='narvarte-casas'").fetchone()
        self.assertEqual(r['agency_id'], a['id'])
        self.assertEqual(con.execute('SELECT source FROM leads WHERE id=?', (r['lead_id'],)).fetchone()[0], 'portal')
        con.close()

    def test_buyer_alert(self):
        lid, cookie, csrf = self.agency_with_listing('alertas-roma', 'Roma Norte', 4200000)
        s, page, _ = req('alertas-roma.fichaunica.localhost', '/alerta', {'name': 'Iván', 'phone': '5598765432', 'operation': 'venta',
                                                                       'colonia': 'Roma', 'max': '5000000', 'consent': '1'})
        self.assertIn('Le avisaremos', page)
        from llave import alerts_buyers
        con = db.connect()
        self.assertEqual(alerts_buyers.run(con), 0)                               # listing is still a draft
        req('app.fichaunica.localhost', '/nueva/%d/3' % lid, {'csrf': csrf, 'title': 'Departamento en venta en Roma Norte', 'description': 'x'}, cookie)
        self.assertEqual(alerts_buyers.run(con), 1)
        self.assertEqual(alerts_buyers.run(con), 0)                               # never twice
        p = json.loads(con.execute("SELECT payload FROM outbox WHERE ref LIKE 'saved_search:%'").fetchone()[0])
        self.assertEqual(p['audience'], 'agency')
        self.assertIn('wa.me/525598765432', p['body']['text'])
        s, page, _ = req('alertas-roma.fichaunica.localhost', '/alerta', {'name': 'X', 'phone': '5598765432'})
        self.assertEqual(s, 400)                                                  # consent required
        con.close()


if __name__ == '__main__':
    unittest.main()
