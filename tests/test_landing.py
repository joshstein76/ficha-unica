"""Landing v2 + public pricing: content, prices, no competitor names, 999 only as Próximamente."""
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

TMP = tempfile.mkdtemp()
os.environ.setdefault('LLAVE_DB', os.path.join(TMP, 'l.db'))
os.environ.setdefault('LLAVE_MEDIA', os.path.join(TMP, 'media'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import ThreadingHTTPServer  # noqa: E402
from llave.web.server import Handler  # noqa: E402

PORT = 8692
COMP = re.compile(r'easy\s*broker|idxboost|wiggot|tokko|inmuebles24|lamudi|placester', re.I)


def get(path, host='app.fichaunica.localhost'):
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), headers={'Host': host})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), ex.headers


def main(h):
    return re.search(r'<main.*</main>', h, re.S).group(0)


class Landing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.land = main(get('/')[1].decode())
        cls.prec = main(get('/precios')[1].decode())
        cls.planes = main(get('/planes')[1].decode())
        cls.raw = get('/')[1].decode()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_sections_present(self):
        h = self.land
        for s in ('Crear mi sitio gratis', 'Tu sitio, gratis', 'En Google y en los portales', 'Tus clientes, en WhatsApp',
                  'Cómo funciona', 'RentaPóliza', 'Bolsa 50/50', 'Academia', 'Preguntas frecuentes',
                  'Ficha Única es un servicio de Ciao Bella Marketing', '/terminos', '/privacidad', 'agent-site-demo.webp'):
            self.assertIn(s, self.raw if s in ('/terminos', '/privacidad') or s.startswith('Ficha Única es') else h)
        self.assertEqual(h.count('<details>'), 5)
        self.assertEqual(h.count('<h1'), 1)

    def test_static_demo_image(self):
        s, body, hd = get('/_s/agent-site-demo.webp')
        self.assertEqual((s, hd['Content-Type']), (200, 'image/webp'))
        self.assertLess(len(body), 150000)
        self.assertEqual(get('/_s/../db.py')[0], 404)
        self.assertEqual(get('/_s/nada.png')[0], 404)

    def test_prices_consistent_everywhere(self):
        for h in (self.land, self.prec, self.planes):
            self.assertEqual(sorted(set(re.findall(r'\$(\d+) MXN', h))), ['299', '799', '999'])
            self.assertIn('Gratis', h)

    def test_999_only_proximamente(self):
        for h in (self.land, self.prec):
            card = [c for c in h.split('<div class="card plan') if 'Pro + CRM' in c][0]
            self.assertIn('Próximamente', card)
            self.assertNotIn('<a class="btn', card.split('</div>')[0])
            self.assertEqual(h.count('999'), h.count('$999 MXN'))

    def test_no_competitor_names(self):
        for h in (self.land, self.prec, self.planes):
            self.assertIsNone(COMP.search(h))

    def test_precios_matches_planes_and_reachable_logged_out(self):
        self.assertEqual(get('/precios')[0], 200)
        self.assertEqual(self.prec, self.planes)

    def test_no_invented_social_proof(self):
        self.assertIsNone(re.search(r'testimonio|\d+\s*(asesores|agentes|clientes)\s+(ya|conf)|★|#1|el mejor', self.land, re.I))

    def test_mobile_basics(self):
        r = self.raw
        self.assertIn('width=device-width,initial-scale=1', r)
        self.assertIn('lang="es-MX"', r)
        self.assertIn('application/ld+json', r)
        self.assertNotIn('<script src', r)
        self.assertIsNone(COMP.search(r))


if __name__ == '__main__':
    unittest.main()
