"""Ficha Única v7 brand look (owner-approved 2026-10-20): light only, Onest, mandarin, on the landing, pricing, sign-up/login,
the agent panel and the PWA shell. Agent-site designs (Residencia / Ciudad / Costa) are NOT part of it and must stay as they were."""
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
os.environ.setdefault('LLAVE_DB', os.path.join(TMP, 'b.db'))
os.environ.setdefault('LLAVE_MEDIA', os.path.join(TMP, 'media'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402
from llave.web import panel, styles  # noqa: E402
from llave.web.server import Handler  # noqa: E402

PORT = 8711
BASE = 'http://127.0.0.1:%d' % PORT
APP = 'app.fichaunica.localhost'
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'llave', 'web', 'static')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(host, path, data=None, cookie=None):
    headers = {'Host': host}
    if cookie:
        headers['Cookie'] = cookie
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        r = OPENER.open(urllib.request.Request(BASE + path, data=data, headers=headers))
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), ex.headers


def hexes(css):
    return {m.upper() for m in re.findall(r'#[0-9a-fA-F]{6}\b', css)}


class BrandV7(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.environ['LLAVE_DB'], os.environ['LLAVE_MEDIA'], PORT
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        s, body, h = req(APP, '/registro', {'name': 'Brand Tester', 'agency': 'Casa Marca', 'whatsapp': '55 1234 5678',
                                           'email': 'marca@ejemplo.test', 'password': 'segura1234', 'terms': '1'})
        assert s == 303, body[:300]
        cls.cookie = h['Set-Cookie'].split(';')[0]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls._saved

    def page(self, path, host=APP, cookie=None):
        s, body, _ = req(host, path, cookie=cookie)
        self.assertEqual(s, 200, path)
        return body.decode('utf-8')

    def brand_pages(self):
        pages = {p: self.page(p) for p in ('/', '/planes', '/precios', '/registro', '/entrar', '/terminos', '/privacidad', '/offline')}
        pages['/ (logged in)'] = self.page('/', cookie=self.cookie)
        pages['/plan'] = self.page('/plan', cookie=self.cookie)
        pages['/propiedades (panel)'] = self.page('/propiedades', cookie=self.cookie)
        pages['/propiedades (directory)'] = self.page('/propiedades', host='fichaunica.localhost')
        return pages

    def test_light_only_no_dark_blocks(self):
        for name, h in self.brand_pages().items():
            self.assertNotIn('prefers-color-scheme', h, name)
            self.assertNotIn('color-scheme:dark', h, name)
        self.assertNotIn('prefers-color-scheme', styles.PANEL)
        for k in ('--bg:#FFFFFF', 'color-scheme:light'):
            self.assertIn(k, styles.BRAND_TOKENS)

    def test_brand_tokens_everywhere(self):
        for name, h in self.brand_pages().items():
            if name == '/offline':
                self.assertIn('#FF6B1A', h)
                continue
            self.assertIn('Onest', h, name)
            self.assertIn('--o:#FF6B1A', h, name)
            self.assertIn('#B83F0A', h, name)                      # orange text token
            if 'directory' not in name:                            # the directory reuses the site layout classes (its token block still names Figtree)
                self.assertNotIn('Figtree', h, name)               # the old panel font
            self.assertNotIn('#0f5c4c', h.lower(), name)           # the old teal
        pages = self.brand_pages()
        for name in ('/', '/planes', '/registro', '/entrar', '/terminos', '/ (logged in)', '/plan', '/propiedades (directory)'):
            h = pages[name]
            self.assertIn('M19 6h26c7.2 0 13 5.8 13 13', h, name)    # the chat-bubble-with-a-house mark, inline
            self.assertNotIn('i-sheet"', h, name)                    # the old sheet glyph is gone
            self.assertRegex(h, r'<svg class="mark"[^>]*aria-hidden="true"', name)
            ids = re.findall(r'<linearGradient id="([^"]+)"', h)
            self.assertTrue(ids and len(ids) == len(set(ids)), (name, ids))   # one gradient id per inline copy
        self.assertEqual(len(re.findall(r'<linearGradient id="', pages['/'])), 3)   # header, hero pill, footer
        self.assertIn('letter-spacing:-.035em', pages['/'])

    def test_focus_and_reduced_motion_everywhere(self):
        for name, h in self.brand_pages().items():
            if name == '/offline':
                continue
            self.assertIn(':focus-visible', h, name)
            self.assertIn('prefers-reduced-motion', h, name)

    def test_agent_site_designs_unchanged(self):
        for d in ('residencia', 'ciudad', 'costa'):
            css = styles.site_css(d, '#1f4e79')
            self.assertIn('prefers-color-scheme:dark', css, d)       # their dark theme stays
            self.assertNotIn('Onest', css, d)
            self.assertNotIn('#FF6B1A', css.upper(), d)
            self.assertEqual(css, styles.site_css(d, '#1f4e79', dark_mode=True))
            self.assertNotIn('prefers-color-scheme', styles.site_css(d, '#1f4e79', dark_mode=False))
        self.assertIn('Instrument+Serif', styles.fonts_url('residencia'))
        self.assertIn('Fraunces', styles.fonts_url('costa'))

    def test_brand_text_contrast(self):
        ink, ink2, muted, line = '#1A1A22', '#464653', '#636371', '#E6E6EE'
        bgs = ('#FFFFFF', '#F6F6F9')
        for fg in (ink, ink2, muted, '#B83F0A'):
            for bg in bgs:
                self.assertGreaterEqual(styles.contrast(fg, bg), 4.5, (fg, bg))
        for fg, bg in ((ink, '#FF6B1A'), (ink, '#FFC24B'), (ink, '#F2501F'), ('#B83F0A', '#FFF1E7'), ('#0F6F50', '#E3F5EC'),
                       ('#B3261E', '#FDECEA'), ('#B83F0A', '#FDECEA'), ('#FFFFFF', '#0F8043'), ('#FFFFFF', ink), (ink, '#E3F5EC')):
            self.assertGreaterEqual(styles.contrast(fg, bg), 4.5, (fg, bg))
        self.assertGreaterEqual(styles.contrast('#B83F0A', '#FFFFFF'), 4.5)       # focus ring / links on white
        self.assertGreaterEqual(styles.contrast('#8B8B99', '#FFFFFF'), 3.0)       # form-field border
        self.assertGreaterEqual(styles.contrast(muted, '#E6E6EE'), 4.5)           # muted step labels on the line colour

    def test_every_hex_in_brand_css_is_a_brand_colour(self):
        allowed = {'#FFFFFF', '#F6F6F9', '#1A1A22', '#464653', '#636371', '#E6E6EE', '#8B8B99', '#FF6B1A', '#FF9A3D', '#FFC24B', '#B83F0A',
                   '#FFF1E7', '#F2501F', '#0F8043', '#0F6F50', '#E3F5EC', '#B3261E', '#FDECEA'}
        self.assertEqual(hexes(styles.PANEL) - allowed, set())

    def test_pwa_shell_in_brand(self):
        s, body, _ = req(APP, '/manifest.webmanifest')
        m = json.loads(body)
        self.assertEqual(m['theme_color'], '#FF6B1A')
        self.assertEqual(m['background_color'], '#ffffff')
        for ic in m['icons']:
            s, png, _ = req(APP, ic['src'])
            self.assertEqual(s, 200)
        for name, size in (('icon-192.png', 192), ('icon-512.png', 512), ('apple-touch-icon.png', 180)):  # same filenames; the lead drops the new art in
            with Image.open(os.path.join(STATIC, name)) as im:
                self.assertEqual(im.size, (size, size), name)
        self.assertIn('theme-color" content="#FF6B1A"', self.page('/entrar'))
        s, js, _ = req(APP, '/sw.js')
        self.assertIn("const V='fu-v2'", js.decode())                             # new cache so installed apps pick up the new shell

    def test_landing_assets_exist_and_no_portal_promise(self):
        h = self.page('/')
        urls = set(re.findall(r'src="(/_s/[^"]+)"', h)) | set(re.findall(r'href="(/_s/[^"]+)"', h))
        self.assertTrue(any('u-casa-2-pisos' in u for u in urls))
        for u in urls:
            self.assertEqual(req(APP, u)[0], 200, u)
        for name in ('/', '/planes', '/registro', '/entrar'):
            self.assertNotIn('en camino', self.page(name), name)

    def test_plans_match_panel_and_limits(self):
        for path in ('/', '/planes'):
            h = self.page(path)
            for key, name, price, feats in panel.PLANS:
                card = [c for c in h.split('<div class="card plan') if re.match(r'(?: top)?" data-k="%s"' % key, c)][0]
                for f in feats:
                    self.assertIn(f.replace('&', '&amp;'), card, (key, f))
                if price:
                    self.assertIn('<b>$%d</b>' % price, card)
                self.assertIn('%d propiedad' % db.PLAN_LIMITS[key], card)
        self.assertEqual({k: p for k, _n, p, _f in panel.PLANS}, {'gratis': 0, 'pro': 499, 'ia': 999})
        self.assertEqual(db.PLAN_LIMITS, {'gratis': 1, 'pro': 5, 'ia': 25})

    def test_forms_unchanged(self):
        reg = self.page('/registro?marca=Casa%20Roma')
        self.assertIn('value="Casa Roma"', reg)
        self.assertIn('action="/registro"', reg)
        for f in ('ref', 'name', 'agency', 'whatsapp', 'email', 'password', 'terms'):
            self.assertRegex(reg, r'<input[^>]* name="%s"' % f)
        login = self.page('/entrar')
        self.assertIn('action="/entrar"', login)
        for f in ('email', 'password'):
            self.assertRegex(login, r'<input[^>]* name="%s"' % f)
        dash = self.page('/', cookie=self.cookie)
        self.assertRegex(dash, r'<form method="post" action="/salir"[^>]*><input type="hidden" name="csrf" value="[0-9a-f]+">')

    def test_panel_nav_and_pills_keep_their_hooks(self):
        dash = self.page('/', cookie=self.cookie)
        self.assertIn('<nav class="tabs" aria-label="Secciones">', dash)
        self.assertIn('aria-current="page"', dash)
        for cls in ('.pill.activa', '.pill.pendiente', '.pill.error', '.notice.err', '.notice.warn', '.btn.ghost', '.btn.wa', 'nav.tabs a.on', '.fab'):
            self.assertIn(cls, styles.PANEL)


if __name__ == '__main__':
    unittest.main()
