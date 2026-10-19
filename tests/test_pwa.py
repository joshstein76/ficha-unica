"""Installable app: manifest, service worker, offline page, icons; panel pages link them and are never cached by the SW."""
import json
import os
import sys
import tempfile
import threading
import unittest

TMP = tempfile.mkdtemp()
os.environ.setdefault('LLAVE_DB', os.path.join(TMP, 'l.db'))
os.environ.setdefault('LLAVE_MEDIA', os.path.join(TMP, 'media'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import ThreadingHTTPServer  # noqa: E402
from llave.web.server import Handler  # noqa: E402
from tests.test_landing import get  # noqa: E402
import tests.test_landing as tl  # noqa: E402


class Pwa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tl.PORT = 8693
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 8693), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_manifest(self):
        st, body, hd = get('/manifest.webmanifest')
        self.assertEqual(st, 200)
        m = json.loads(body)
        self.assertEqual(m['display'], 'standalone')
        self.assertEqual(m['name'], 'Ficha Única')
        for ic in m['icons']:
            self.assertEqual(get(ic['src'])[0], 200)

    def test_sw_scope_and_no_panel_caching(self):
        st, body, hd = get('/sw.js')
        self.assertEqual(st, 200)
        self.assertEqual(hd['Service-Worker-Allowed'], '/')
        js = body.decode()
        self.assertIn("startsWith('/_s/')", js)
        self.assertNotIn('put(r', js.split("r.mode==='navigate'")[1].split('\n')[0])  # navigations are never stored

    def test_offline_and_head(self):
        self.assertIn('Sin conexión', get('/offline')[1].decode())
        h = get('/entrar')[1].decode()
        self.assertIn('rel="manifest"', h)
        self.assertIn('serviceWorker', h)

    def test_not_on_agent_sites(self):
        self.assertNotEqual(get('/sw.js', host='nadie.fichaunica.localhost')[0], 200)


if __name__ == '__main__':
    unittest.main()
