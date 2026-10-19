"""With LLAVE_MARKETING_URL set, the logged-out app home hands off to the WordPress site; sign-up and login stay in the app."""
import os
import sys
import tempfile
import threading
import unittest
import urllib.request

TMP = tempfile.mkdtemp()
os.environ.setdefault('LLAVE_DB', os.path.join(TMP, 'l.db'))
os.environ.setdefault('LLAVE_MEDIA', os.path.join(TMP, 'media'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402
from llave.web.server import Handler  # noqa: E402


class NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Marketing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init(db.connect())
        cls.old = db.MARKETING_URL
        db.MARKETING_URL = 'https://fichaunica.mx'
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 8702), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        db.MARKETING_URL = cls.old
        cls.srv.shutdown()

    def get(self, path):
        op = urllib.request.build_opener(NoFollow)
        try:
            r = op.open(urllib.request.Request('http://127.0.0.1:8702' + path, headers={'Host': 'app.fichaunica.localhost'}))
            return r.status, r.headers
        except urllib.error.HTTPError as ex:
            return ex.code, ex.headers

    def test_home_redirects(self):
        st, hd = self.get('/')
        self.assertEqual(st, 303)
        self.assertEqual(hd['Location'], 'https://fichaunica.mx/')

    def test_ref_is_carried(self):
        self.assertEqual(self.get('/?ref=abc')[1]['Location'], 'https://fichaunica.mx/?ref=abc')

    def test_app_pages_stay(self):
        self.assertEqual(self.get('/registro')[0], 200)
        self.assertEqual(self.get('/planes')[0], 200)


if __name__ == '__main__':
    unittest.main()
