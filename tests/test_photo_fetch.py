import io
import os
import tempfile
import unittest
from functools import partial

from PIL import Image

from llave import db, photo_fetch as pf


def jpeg(size=(1800, 1200)):
    buf = io.BytesIO()
    Image.new('RGB', size, (120, 90, 60)).save(buf, 'JPEG')
    return buf.getvalue()


def resolver_map(m):
    def r(host, port, *a):
        return [(2, 1, 6, '', (m.get(host, '93.184.216.34'), port))]
    return r


class Resp:
    def __init__(self, status=200, ctype='image/jpeg', body=b'', headers=None):
        self.status, self.body, self.pos = status, body, 0
        self.h = {'content-type': ctype}
        self.h.update({k.lower(): v for k, v in (headers or {}).items()})

    def getheader(self, k, d=None):
        return self.h.get(k.lower(), d)

    def read(self, n):
        c = self.body[self.pos:self.pos + n]
        self.pos += len(c)
        return c

    def close(self):
        pass


def opener_for(resp_by_url, calls=None):
    def op(url, ip, headers, timeout):
        if calls is not None:
            calls.append((url, str(ip), headers))
        return resp_by_url[url]
    return op


PUB = resolver_map({})


class SafeUrl(unittest.TestCase):
    def test_rejected(self):
        res = resolver_map({'internal.example.com': '10.1.2.3'})
        for u in ['file:///etc/passwd', 'ftp://example.com/a.jpg', 'http://127.0.0.1/x.jpg', 'http://[::1]/',
                  'http://169.254.169.254/latest', 'http://10.0.0.5', 'http://192.168.1.2', 'http://2130706433/',
                  'http://0x7f000001/', 'http://0x7f.1/', 'http://017700000001/', 'http://[::ffff:127.0.0.1]/',
                  'http://user:pw@example.com/a.jpg', 'http://example.com:8080/a.jpg', 'http://foo.localhost/a.jpg',
                  'http://localhost/a.jpg', 'http://x.local/a.jpg', 'http://x.internal/a.jpg',
                  'http://app.' + db.BASE_DOMAIN + '/a.jpg', 'http://internal.example.com/a.jpg', 'http://0.0.0.0/']:
            ok, why = pf.is_safe_url(u, res)
            self.assertFalse(ok, u)
            self.assertTrue(why)

    def test_public_ok(self):
        self.assertTrue(pf.is_safe_url('https://example.com/a.jpg', PUB)[0])
        self.assertTrue(pf.is_safe_url('http://93.184.216.34/a.jpg', PUB)[0])

    def test_mixed_resolution_rejected(self):
        r = lambda h, p, *a: [(2, 1, 6, '', ('93.184.216.34', p)), (2, 1, 6, '', ('127.0.0.1', p))]
        self.assertFalse(pf.is_safe_url('http://example.com/a.jpg', r)[0])


class Fetch(unittest.TestCase):
    def test_success_and_pinned_ip(self):
        calls = []
        op = opener_for({'https://example.com/a.jpg': Resp(body=jpeg())}, calls)
        data = pf.fetch_bytes('https://example.com/a.jpg', opener=op, resolver=PUB)
        self.assertTrue(data.startswith(b'\xff\xd8\xff'))
        self.assertEqual(calls[0][1], '93.184.216.34')
        self.assertEqual(calls[0][2]['User-Agent'], 'FichaUnica-PhotoImport/1.0')

    def test_bad_type_magic_size_status(self):
        u = 'http://example.com/a.jpg'
        for resp in [Resp(ctype='text/html', body=jpeg()), Resp(body=b'<html>nope</html>'),
                     Resp(status=404), Resp(body=b'\xff\xd8\xff' + b'0' * 5000, headers={'Content-Length': '999999999'})]:
            with self.assertRaises(ValueError):
                pf.fetch_bytes(u, opener=opener_for({u: resp}), resolver=PUB)

    def test_oversize_stream(self):
        u = 'http://example.com/a.jpg'
        with self.assertRaises(ValueError):
            pf.fetch_bytes(u, opener=opener_for({u: Resp(body=b'\xff\xd8\xff' + b'0' * 300000)}), resolver=PUB, max_bytes=100000)

    def test_redirect_to_loopback_rejected(self):
        u = 'http://example.com/a.jpg'
        op = opener_for({u: Resp(status=302, body=b'', headers={'Location': 'http://127.0.0.1/secret.jpg'})})
        with self.assertRaises(ValueError):
            pf.fetch_bytes(u, opener=op, resolver=PUB)

    def test_redirect_ok_and_limit(self):
        a, b = 'http://example.com/a.jpg', 'http://example.com/b.jpg'
        op = opener_for({a: Resp(status=301, headers={'Location': '/b.jpg'}), b: Resp(body=jpeg())})
        self.assertTrue(pf.fetch_bytes(a, opener=op, resolver=PUB))
        loop = opener_for({a: Resp(status=302, headers={'Location': a})})
        with self.assertRaises(ValueError):
            pf.fetch_bytes(a, opener=loop, resolver=PUB)

    def test_unsafe_never_opens(self):
        calls = []
        with self.assertRaises(ValueError):
            pf.fetch_bytes('http://10.0.0.5/a.jpg', opener=opener_for({}, calls), resolver=PUB)
        self.assertEqual(calls, [])


class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = db.MEDIA_DIR
        db.MEDIA_DIR = os.path.join(self.tmp, 'media')
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(slug,name) VALUES('a','A')")
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title) VALUES(1,'R1','l1','Depto Polanco')")
        self.con.commit()

    def tearDown(self):
        db.MEDIA_DIR = self._old
        self.con.close()

    def test_limit_and_dedupe(self):
        urls = ['http://example.com/%d.jpg' % i for i in range(25)] + ['http://example.com/3.jpg']
        self.assertEqual(pf.enqueue(self.con, {1: urls}), 20)
        s = pf.summary(self.con, 1)
        self.assertEqual((s['pendiente'], s['omitida']), (20, 5))
        self.assertEqual(self.con.execute("SELECT error FROM photo_jobs WHERE status='omitida'").fetchone()[0],
                         'Máximo 20 fotos por propiedad')
        self.assertEqual(pf.enqueue(self.con, {1: urls}), 0)  # re-enqueue is a no-op

    def test_run_jobs_ingests(self):
        good, bad, tiny = 'http://example.com/g.jpg', 'http://127.0.0.1/b.jpg', 'http://example.com/t.jpg'
        pf.enqueue(self.con, {1: [good, bad, tiny]})
        op = opener_for({good: Resp(body=jpeg()), tiny: Resp(body=jpeg((200, 100)))})
        fetch = partial(pf.fetch_bytes, opener=op, resolver=PUB)
        out = pf.run_jobs(self.con, sleep_between=0, fetch=fetch)
        self.assertEqual(out, {'lista': 1, 'error': 2})
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM photos WHERE listing_id=1').fetchone()[0], 1)
        row = self.con.execute("SELECT * FROM photo_jobs WHERE url=?", (good,)).fetchone()
        self.assertEqual(row['status'], 'lista')
        self.assertIsNotNone(row['photo_id'])
        self.assertIn('pequeña', self.con.execute("SELECT error FROM photo_jobs WHERE url=?", (tiny,)).fetchone()[0])
        self.assertEqual(pf.summary(self.con, 1)['error'], 2)
        self.assertEqual(self.con.execute("SELECT alt FROM photos").fetchone()[0], 'Depto Polanco')


if __name__ == '__main__':
    unittest.main()
