"""Accessibility + speed: skip links, labelled contact form, gzip, media cache/ETag, <picture>/webp, contrast, HTTP/1.1."""
import gzip
import http.client
import io
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
os.environ['LLAVE_DB'] = os.path.join(TMP, 'a.db')
os.environ['LLAVE_MEDIA'] = os.path.join(TMP, 'media')
os.environ['LLAVE_PORT'] = '8698'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402
from llave.web import styles  # noqa: E402
from llave.web.server import Handler  # noqa: E402

PORT = 8698
BASE = 'http://127.0.0.1:%d' % PORT
APP = 'app.fichaunica.localhost'
SITE = 'casa-luz.fichaunica.localhost'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(host, path, data=None, cookie=None, ctype=None, extra=None):
    headers = {'Host': host}
    headers.update(extra or {})
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
        return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), ex.headers


def jpeg(w=1800, h=1200, color=(120, 140, 160)):
    b = io.BytesIO()
    Image.new('RGB', (w, h), color).save(b, 'JPEG')
    return b.getvalue()


def multipart(fields, files):
    bnd = 'llaveA11Y'
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode())
    for k, (fn, data) in files:
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: image/jpeg\r\n\r\n'
                   % (bnd, k, fn)).encode() + data + b'\r\n')
    out.write(('--%s--\r\n' % bnd).encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + bnd


class A11ySpeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # other test modules patch the same module globals at import time: re-assert ours, restore afterwards
        cls._saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.environ['LLAVE_DB'], os.environ['LLAVE_MEDIA'], PORT
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        s, body, h = req(APP, '/registro', {'name': 'Luz Ortega', 'agency': 'Casa Luz', 'whatsapp': '55 1234 5678',
                                           'email': 'luz@ejemplo.test', 'password': 'segura1234', 'terms': '1'})
        assert s == 303, body[:300]
        cls.cookie = h['Set-Cookie'].split(';')[0]
        s, page, _ = req(APP, '/', cookie=cls.cookie)
        cls.dash = page.decode()
        csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', cls.dash).group(1)
        form = {'csrf': csrf, 'title': 'Casa con jardín en Coyoacán', 'operation': 'venta', 'property_type': 'casa',
                'price': '5,500,000', 'currency': 'MXN', 'status': 'activa', 'description': 'Casa luminosa con jardín. ' * 8,
                'm2_built': '150', 'bedrooms': '3', 'bathrooms': '2', 'parking': '2', 'colonia': 'Coyoacán',
                'municipio': 'Coyoacán', 'estado': 'Ciudad de México'}
        s, _, h = req(APP, '/propiedades/nueva', form, cls.cookie)
        assert s == 303
        cls.lid = int(re.search(r'/propiedades/(\d+)', h['Location']).group(1))
        body, ct = multipart({'csrf': csrf}, [('fotos', ('f%d.jpg' % i, jpeg(color=(i * 40, 90, 150)))) for i in range(4)])
        s, _, _ = req(APP, '/propiedades/%d/fotos' % cls.lid, body, cls.cookie, ct)
        assert s == 200
        con = db.connect()
        cls.slug = con.execute('SELECT slug FROM listings WHERE id=?', (cls.lid,)).fetchone()['slug']
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls._saved

    def text(self, host, path, **kw):
        s, body, h = req(host, path, **kw)
        return s, body.decode('utf-8', 'replace'), h

    def test_skip_link_site_and_panel(self):
        for host, path, cookie in ((SITE, '/', None), (SITE, '/propiedad/' + self.slug, None),
                                   (APP, '/entrar', None), (APP, '/', self.cookie)):
            s, page, _ = self.text(host, path, cookie=cookie)
            self.assertEqual(s, 200, path)
            self.assertRegex(page, r'<body><a class="skip" href="#main">Saltar al contenido</a>', path)
            self.assertRegex(page, r'<main id="main"', path)

    def test_contact_form_has_labels(self):
        s, page, _ = self.text(SITE, '/propiedad/' + self.slug)
        for fid, name in (('f-name', 'name'), ('f-phone', 'phone'), ('f-email', 'email'), ('f-msg', 'message')):
            self.assertIn('<label class="vh" for="%s">' % fid, page)
            self.assertRegex(page, r'<(input|textarea) id="%s" name="%s"' % (fid, name))
        self.assertIn('autocomplete="tel" maxlength="20"', page)
        self.assertIn('<h2 class="vh">Contacto</h2>', page)
        s, err, _ = self.text(SITE, '/contacto', data={'listing': self.lid, 'name': 'Ana', 'phone': '5511112222'})
        self.assertEqual(s, 400)
        self.assertIn('id="err"', err)
        self.assertIn('aria-invalid="true" aria-describedby="err"', err)

    def test_gzip_served_when_requested(self):
        s, plain, h = req(SITE, '/propiedad/' + self.slug)
        self.assertIsNone(h.get('Content-Encoding'))
        self.assertEqual(h.get('Vary'), 'Accept-Encoding')
        self.assertEqual(h.get('Cache-Control'), 'no-cache')
        s, gz, h = req(SITE, '/propiedad/' + self.slug, extra={'Accept-Encoding': 'gzip'})
        self.assertEqual(h.get('Content-Encoding'), 'gzip')
        self.assertLess(len(gz), len(plain))
        self.assertEqual(gzip.decompress(gz), plain)
        s, _, h = req(APP, '/entrar')
        self.assertEqual(h.get('Cache-Control'), 'private, no-store')

    def test_media_etag_and_304(self):
        s, home, _ = self.text(SITE, '/')
        rel = re.search(r'/media/([0-9a-f]{2}/[0-9a-f]{64}/\d+\.(?:jpg|webp))', home).group(1)
        s, body, h = req(SITE, '/media/' + rel)
        self.assertEqual(s, 200)
        self.assertEqual(h['Cache-Control'], 'public, max-age=31536000, immutable')
        etag = h['ETag']
        self.assertTrue(etag)
        self.assertEqual(int(h['Content-Length']), len(body))
        s, body, h = req(SITE, '/media/' + rel, extra={'If-None-Match': etag})
        self.assertEqual((s, body), (304, b''))
        self.assertEqual(h['ETag'], etag)

    def test_picture_webp_on_home(self):
        s, home, _ = self.text(SITE, '/')
        self.assertIn('<picture>', home)
        self.assertRegex(home, r'<source type="image/webp" srcset="[^"]+\.webp 400w, [^"]+\.webp 800w, [^"]+\.webp 1600w"')
        self.assertIn('sizes="(min-width:1120px) 360px, (min-width:600px) 33vw, 100vw"', home)
        self.assertIn('fetchpriority="high"', home)
        self.assertRegex(home, r'width="\d+" height="\d+"')
        s, lp, _ = self.text(SITE, '/propiedad/' + self.slug)
        self.assertIn('class="swipe" aria-hidden="true"', lp)
        self.assertIn('foto 1 de 4', lp)

    def test_contrast_helpers(self):
        for accent in ('#1a1a1a', '#d4a017', '#0ea5e9', '#1f4e79', '#e11d48'):
            on = styles.on_accent(accent)
            self.assertGreaterEqual(styles.contrast(on, accent), 4.5, accent)
            css = styles.site_css('ciudad', accent)
            self.assertIn('--accent-text:', css)
            light = styles.accent_text(accent, '#ffffff')
            self.assertGreaterEqual(styles.contrast(light, '#ffffff'), 4.5, accent)
            dark_base = '#d8d2c8' if styles.luminance(accent) < 0.05 else accent
            dark = styles.accent_text(dark_base, '#121212', dark=True)
            self.assertGreaterEqual(styles.contrast(dark, '#121212'), 4.5, accent)
            self.assertGreaterEqual(styles.contrast(styles.on_accent(dark_base), dark_base), 4.5, accent)

    def test_http11_redirect_head_and_keepalive(self):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=10)
        try:
            c.request('POST', '/contacto', body='website=bot&name=x', headers={
                'Host': SITE, 'Content-Type': 'application/x-www-form-urlencoded'})
            r = c.getresponse()
            self.assertEqual(r.version, 11)
            self.assertEqual(r.status, 303)
            self.assertEqual(r.getheader('Content-Length'), '0')
            self.assertEqual(r.read(), b'')
            c.request('HEAD', '/', headers={'Host': SITE})   # same connection: keep-alive still in sync
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertGreater(int(r.getheader('Content-Length')), 0)
            self.assertEqual(r.read(), b'')
            c.request('GET', '/robots.txt', headers={'Host': SITE})
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertIn(b'User-agent', r.read())
        finally:
            c.close()


if __name__ == '__main__':
    unittest.main()
