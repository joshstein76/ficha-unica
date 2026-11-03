"""Shared helpers for the account / email web tests (not a test module: unittest discover skips it).
A real local server on a free port (port 0, so two test runs at once never collide) plus tiny HTTP helpers.
Nothing here opens an SMTP connection: tests that touch mail inject the sender or patch `llave.mailer._smtp_send`."""
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from llave import db
from llave.web.server import Handler

APP = 'app.fichaunica.localhost'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class LocalServer:
    def __init__(self, name):
        self.tmp = tempfile.mkdtemp()
        self.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR = os.path.join(self.tmp, name + '.db'), os.path.join(self.tmp, 'media')
        con = db.connect()
        db.init(con)
        con.close()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.srv.server_address[1]
        db.PORT = self.port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.n = 0

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = self.saved

    def req(self, path, data=None, cookie=None, headers=None, host=APP):
        h = {'Host': host}
        h.update(headers or {})
        if cookie:
            h['Cookie'] = cookie
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            r = OPENER.open(urllib.request.Request('http://127.0.0.1:%d%s' % (self.port, path), data=data, headers=h), timeout=15)
            return r.status, r.read().decode('utf-8', 'replace'), r.headers
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read().decode('utf-8', 'replace'), ex.headers

    def signup(self, email=None, agency=None, password='segura1234'):
        """New agent -> dict(email, cookie, csrf, aid, uid). Uses the real /registro route."""
        self.n += 1
        email = email or 'agente%d@ejemplo.test' % self.n
        s, _, h = self.req('/registro', {'name': 'Rosa Pérez', 'agency': agency or 'Casa Rosa %d' % self.n, 'whatsapp': '55 7777 8888',
                                         'email': email, 'password': password, 'terms': '1'})
        assert s == 303, s
        cookie = h['Set-Cookie'].split(';')[0]
        _, body, _ = self.req('/perfil', cookie=cookie)
        csrf = re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)
        con = db.connect()
        row = con.execute('SELECT id, agency_id FROM users WHERE email=?', (email,)).fetchone()
        con.close()
        return {'email': email, 'cookie': cookie, 'csrf': csrf, 'aid': row['agency_id'], 'uid': row['id'], 'password': password}

    def q(self, sql, *args):
        con = db.connect()
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def one(self, sql, *args):
        r = self.q(sql, *args)
        return r[0] if r else None
