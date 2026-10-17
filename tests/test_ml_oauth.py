import base64
import datetime
import hashlib
import os
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db, ml_oauth  # noqa: E402

KEYS = ('ML_CLIENT_ID', 'ML_CLIENT_SECRET', 'ML_REDIRECT_URI', 'LLAVE_ML_LIVE')


class MLOAuthTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in KEYS}
        for k in KEYS:
            os.environ.pop(k, None)
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(id, slug, name, email) VALUES (1,'vive','VIVE','a@x.mx')")
        self.con.execute("""INSERT INTO listings(id, agency_id, ref, slug, status, operation, property_type, title,
            description, price_cents, m2_built, colonia, municipio, estado, show_exact_location)
            VALUES (1,1,'V-1','depa','activa','venta','departamento','Departamento en Polanco con terraza',
            'Bonito', 100000000, 100, 'Polanco','Miguel Hidalgo','CDMX', 0)""")
        self.con.commit()
        self.calls = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def configure(self, live=False):
        os.environ['ML_CLIENT_ID'] = 'cid'
        os.environ['ML_CLIENT_SECRET'] = 'csecret'
        if live:
            os.environ['LLAVE_ML_LIVE'] = '1'

    def fake(self, resp):
        def post(url, data, headers=None):
            self.calls.append((url, data, headers))
            return resp
        return post

    def test_not_configured(self):
        self.assertIsNone(ml_oauth.start(self.con, 1))
        self.assertFalse(ml_oauth.is_live())
        self.assertIn('/oauth/mercadolibre/callback', ml_oauth.config()['redirect_uri'])

    def test_start_url_and_pkce(self):
        self.configure()
        url = ml_oauth.start(self.con, 1)
        self.assertTrue(url.startswith(ml_oauth.AUTH_URL + '?'))
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(q['response_type'], 'code')
        self.assertEqual(q['client_id'], 'cid')
        self.assertEqual(q['code_challenge_method'], 'S256')
        row = self.con.execute('SELECT * FROM ml_oauth_states WHERE state=?', (q['state'],)).fetchone()
        exp = base64.urlsafe_b64encode(hashlib.sha256(row['code_verifier'].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(q['code_challenge'], exp)

    def _state(self):
        self.configure()
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(ml_oauth.start(self.con, 1)).query))
        return q['state']

    def test_state_single_use(self):
        s = self._state()
        with self.assertRaises(RuntimeError):
            ml_oauth.finish(self.con, s, 'code')  # not live, but state consumed
        with self.assertRaises(ValueError):
            ml_oauth.finish(self.con, s, 'code')

    def test_state_expiry(self):
        s = self._state()
        old = (datetime.datetime.utcnow() - datetime.timedelta(minutes=11)).replace(microsecond=0).isoformat()
        self.con.execute('UPDATE ml_oauth_states SET created_at=?', (old,))
        self.con.commit()
        with self.assertRaises(ValueError):
            ml_oauth.finish(self.con, s, 'code', http_post=self.fake({}))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ml_oauth_states').fetchone()[0], 0)

    def test_finish_not_live_stores_nothing(self):
        s = self._state()
        with self.assertRaises(RuntimeError) as cm:
            ml_oauth.finish(self.con, s, 'code', http_post=self.fake({'access_token': 'x'}))
        self.assertIn('desactivada', str(cm.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM ml_accounts').fetchone()[0], 0)

    def test_finish_live_stores_tokens(self):
        self.configure(live=True)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(ml_oauth.start(self.con, 1)).query))
        verifier = self.con.execute('SELECT code_verifier FROM ml_oauth_states').fetchone()[0]
        tok = {'access_token': 'AT1', 'refresh_token': 'RT1', 'expires_in': 21600, 'user_id': 77, 'scope': 'offline_access'}
        self.assertEqual(ml_oauth.finish(self.con, q['state'], 'CODE', http_post=self.fake(tok)), 1)
        url, data, _ = self.calls[0]
        self.assertEqual(url, ml_oauth.TOKEN_URL)
        self.assertEqual(data['grant_type'], 'authorization_code')
        self.assertEqual(data['code_verifier'], verifier)
        self.assertEqual(data['code'], 'CODE')
        a = self.con.execute('SELECT * FROM ml_accounts WHERE agency_id=1').fetchone()
        self.assertEqual((a['access_token'], a['refresh_token'], a['status'], a['ml_user_id']),
                         ('AT1', 'RT1', 'conectada', '77'))
        st = ml_oauth.status(self.con, 1)
        self.assertEqual((st['status'], st['live'], st['configured']), ('conectada', True, True))
        self.assertNotIn('AT1', str(st))

    def test_refresh(self):
        self.configure(live=True)
        ml_oauth.ensure_tables(self.con)
        far = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).replace(microsecond=0).isoformat()
        self.con.execute("INSERT INTO ml_accounts(agency_id, access_token, refresh_token, expires_at, status) "
                         "VALUES (1,'A','R',?, 'conectada')", (far,))
        self.con.commit()
        self.assertFalse(ml_oauth.refresh_if_needed(self.con, 1, self.fake({})))
        self.assertEqual(self.calls, [])
        soon = (datetime.datetime.utcnow() + datetime.timedelta(minutes=2)).replace(microsecond=0).isoformat()
        self.con.execute('UPDATE ml_accounts SET expires_at=?', (soon,))
        self.con.commit()
        self.assertTrue(ml_oauth.refresh_if_needed(
            self.con, 1, self.fake({'access_token': 'A2', 'refresh_token': 'R2', 'expires_in': 21600})))
        self.assertEqual(self.calls[0][1]['grant_type'], 'refresh_token')
        self.assertEqual(self.calls[0][1]['refresh_token'], 'R')
        a = self.con.execute('SELECT * FROM ml_accounts').fetchone()
        self.assertEqual((a['access_token'], a['refresh_token']), ('A2', 'R2'))

    def test_refresh_not_live_noop(self):
        self.configure()
        self.assertFalse(ml_oauth.refresh_if_needed(self.con, 1, self.fake({})))
        self.assertEqual(self.calls, [])

    def test_disconnect_wipes(self):
        ml_oauth.ensure_tables(self.con)
        self.con.execute("INSERT INTO ml_accounts(agency_id, access_token, refresh_token, expires_at, status) "
                         "VALUES (1,'A','R','2030-01-01T00:00:00','conectada')")
        ml_oauth.disconnect(self.con, 1)
        a = self.con.execute('SELECT * FROM ml_accounts').fetchone()
        self.assertEqual((a['access_token'], a['refresh_token'], a['expires_at'], a['status']),
                         (None, None, None, 'desconectada'))

    def test_connect_demo(self):
        ml_oauth.connect_demo(self.con, 1)
        st = ml_oauth.status(self.con, 1)
        self.assertEqual((st['status'], st['nickname']), ('demo', 'cuenta de prueba'))
        self.assertEqual(ml_oauth.status(self.con, 99)['status'], 'desconectada')

    def test_publish_dry_run_writes_outbox(self):
        ml_oauth.connect_demo(self.con, 1)
        r = ml_oauth.publish(self.con, 1, http_post=self.fake({}))
        self.assertEqual(r['mode'], 'dry_run')
        self.assertEqual(self.calls, [])
        row = self.con.execute("SELECT * FROM outbox WHERE kind='portal.mercadolibre.create'").fetchone()
        self.assertEqual(row['status'], 'dry_run')

    def test_publish_live(self):
        self.configure(live=True)
        far = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).replace(microsecond=0).isoformat()
        ml_oauth.ensure_tables(self.con)
        self.con.execute("INSERT INTO ml_accounts(agency_id, access_token, refresh_token, expires_at, status) "
                         "VALUES (1,'AT','RT',?, 'conectada')", (far,))
        self.con.commit()
        r = ml_oauth.publish(self.con, 1, http_post=self.fake({'id': 'MLM123', 'permalink': 'http://x'}))
        self.assertEqual((r['mode'], r['item_id']), ('live', 'MLM123'))
        url, data, headers = self.calls[0]
        self.assertEqual(url, ml_oauth.ITEMS_URL)
        self.assertEqual(headers['Authorization'], 'Bearer AT')
        self.assertNotIn('_dry_run', data)
        out = self.con.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(out['status'], 'sent')
        self.assertNotIn('AT', out['response'])


if __name__ == '__main__':
    unittest.main()
