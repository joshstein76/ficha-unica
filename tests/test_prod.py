"""Production readiness: health, TLS ask, config guard, https origins."""
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
PORT = 8695
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
    bnd = 'prTEST'
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



class Prod(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'x.db'), os.path.join(TMP, 'media'), PORT
        con = db.connect()
        db.init(con)
        con.execute("INSERT INTO agencies(slug, name) VALUES ('casa-sol', 'Casa Sol')")
        con.execute("INSERT INTO agencies(slug, name, custom_domain, domain_verified_at) VALUES ('mia', 'Mía', 'casamia.mx', datetime('now'))")
        con.execute("INSERT INTO agencies(slug, name, custom_domain) VALUES ('pend', 'Pend', 'pendiente.mx')")
        con.commit()
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def test_healthz(self):
        s, body, h = req('anything.example', '/healthz')
        self.assertEqual(s, 200)
        self.assertTrue(json.loads(body)['db_ok'])

    def test_tls_ask(self):
        base = db.BASE_DOMAIN
        for dom, code in (('app.' + base, 200), ('casa-sol.' + base, 200), ('nadie.' + base, 404), ('casamia.mx', 200),
                          ('www.casamia.mx', 200), ('pendiente.mx', 404), ('evil.com', 404)):
            s, _, _ = req('127.0.0.1', '/_tls/ask?domain=' + dom)
            self.assertEqual(s, code, dom)

    def test_production_guard_and_origins(self):
        from llave.web import server, common
        old = (db.ENV, db.SCHEME, db.PUBLIC_PORT, db.BASE_DOMAIN, common.SECRET)
        try:
            db.ENV = 'production'
            self.assertTrue(server.check_production_config())          # default secret + .localhost domain refused
            db.BASE_DOMAIN, common.SECRET, db.SCHEME, db.PUBLIC_PORT = 'fichaunica.mx', 'x' * 48, 'https', None
            self.assertEqual(server.check_production_config(), [])
            self.assertEqual(db.origin('app'), 'https://app.fichaunica.mx')
            self.assertEqual(db.site_url({'slug': 'casa-sol', 'custom_domain': None}), 'https://casa-sol.fichaunica.mx')
        finally:
            db.ENV, db.SCHEME, db.PUBLIC_PORT, db.BASE_DOMAIN, common.SECRET = old


if __name__ == '__main__':
    unittest.main()
