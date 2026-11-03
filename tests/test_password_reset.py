"""Password reset (2026-11-03): token hashed at rest, single use, 60-minute expiry, same answer for any email, rate limited,
success ends the user's other sessions, /entrar shows the link only when mail can be sent. No real SMTP: `mailer._smtp_send` is patched."""
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import auth, db, emails, mailer, password_reset as pr  # noqa: E402
from llave.web import server  # noqa: E402
import web_harness  # noqa: E402
import test_pg_parity  # noqa: E402

SMTP = {'LLAVE_SMTP_HOST': 'smtp.ejemplo.test', 'LLAVE_SMTP_PORT': '587', 'LLAVE_SMTP_USER': 'avisos@ejemplo.test',
        'LLAVE_SMTP_PASSWORD': 'sup3r-secret-pw', 'LLAVE_SMTP_FROM': 'Ficha Única <avisos@ejemplo.test>'}
OFF = {k: '' for k in SMTP}
T0 = datetime.datetime(2026, 11, 3, 12, 0, 0)


def mail_env(**kw):
    d = dict(SMTP)
    d.update(kw)
    return mock.patch.dict(os.environ, d)


def link_in(msg):
    m = re.search(r'https?://\S+/restablecer\?t=([\w-]+)', msg.get_body(('plain',)).get_content())
    return m.group(1) if m else None


class Unit(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'r.db')
        self.con = db.connect(self.path)
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(id, slug, name) VALUES (1,'casa','Casa')")
        self.con.execute("INSERT INTO users(id, agency_id, name, email, password_hash) VALUES (1,1,'Rosa Pérez','rosa@ejemplo.test',?)",
                         (auth.hash_password('vieja-clave-1'),))
        self.con.execute("INSERT INTO users(id, agency_id, name, email, password_hash) VALUES (2,1,'Beto','beto@ejemplo.test',?)",
                         (auth.hash_password('otra-clave-22'),))
        for tok, uid in (('s1', 1), ('s2', 1), ('s3', 2)):
            self.con.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,datetime('now','+1 day'))", (tok, uid))
        self.con.commit()

    def pw_ok(self, uid, password):
        return auth.verify_password(password, self.con.execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()[0])

    def test_unknown_email_makes_nothing(self):
        self.assertIsNone(pr.request(self.con, 'nadie@ejemplo.test', now=T0))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM password_resets').fetchone()[0], 0)

    def test_token_is_hashed_at_rest(self):
        u, token = pr.request(self.con, ' ROSA@ejemplo.test ', now=T0)
        self.assertEqual(u['id'], 1)
        row = self.con.execute('SELECT * FROM password_resets').fetchone()
        self.assertEqual(row['token_hash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, json.dumps([list(r) for r in self.con.execute('SELECT * FROM password_resets')]))
        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(row['expires_at'], '2026-11-03 13:00:00')

    def test_expires_after_sixty_minutes(self):
        _, token = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        self.assertIsNotNone(pr.lookup(self.con, token, now=T0 + datetime.timedelta(minutes=59)))
        self.assertIsNone(pr.lookup(self.con, token, now=T0 + datetime.timedelta(minutes=61)))
        with self.assertRaises(pr.InvalidToken):
            pr.complete(self.con, token, 'clave-nueva-123', now=T0 + datetime.timedelta(minutes=61))
        self.assertTrue(self.pw_ok(1, 'vieja-clave-1'))

    def test_single_use(self):
        _, token = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        self.assertEqual(pr.complete(self.con, token, 'clave-nueva-123', now=T0), 1)
        with self.assertRaises(pr.InvalidToken):
            pr.complete(self.con, token, 'otra-mas-12345', now=T0)
        self.assertTrue(self.pw_ok(1, 'clave-nueva-123'))
        self.assertIsNone(pr.lookup(self.con, token, now=T0))

    def test_two_parallel_uses_apply_once(self):
        _, token = pr.request(self.con, 'rosa@ejemplo.test')
        results, errors = [], []

        def go(i):
            c = db.connect(self.path)
            try:
                results.append(pr.complete(c, token, 'clave-paralela-%d' % i))
            except pr.InvalidToken:
                results.append('invalid')
            except Exception as ex:
                errors.append(repr(ex))
            finally:
                c.close()

        threads = [threading.Thread(target=go, args=(i,)) for i in range(5)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sorted(map(str, results)), ['1', 'invalid', 'invalid', 'invalid', 'invalid'])

    def test_a_new_request_replaces_the_old_link(self):
        _, first = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        _, second = pr.request(self.con, 'rosa@ejemplo.test', now=T0 + datetime.timedelta(minutes=1))
        self.assertIsNone(pr.lookup(self.con, first, now=T0 + datetime.timedelta(minutes=2)))
        self.assertIsNotNone(pr.lookup(self.con, second, now=T0 + datetime.timedelta(minutes=2)))

    def test_success_ends_every_session_of_that_user_only_and_other_links(self):
        _, token = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        pr.request(self.con, 'beto@ejemplo.test', now=T0)
        pr.complete(self.con, token, 'clave-nueva-123', now=T0)
        left = [r[0] for r in self.con.execute('SELECT token FROM sessions ORDER BY token')]
        self.assertEqual(left, ['s3'])                                  # Rosa's two are gone, Beto's stays
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM password_resets WHERE used_at IS NULL').fetchone()[0], 1)  # Beto's link still lives
        self.assertTrue(self.pw_ok(2, 'otra-clave-22'))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM audit WHERE action='password_reset_done'").fetchone()[0], 1)

    def test_a_weak_password_does_not_burn_the_link(self):
        _, token = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        with self.assertRaises(ValueError) as cm:
            pr.complete(self.con, token, 'corta', now=T0)
        self.assertNotIsInstance(cm.exception, pr.InvalidToken)
        self.assertIn('al menos 8', str(cm.exception))
        self.assertIsNotNone(pr.lookup(self.con, token, now=T0))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM sessions WHERE user_id=1').fetchone()[0], 2)

    def test_the_email_is_spanish_short_and_has_the_link_only_in_the_message(self):
        u, token = pr.request(self.con, 'rosa@ejemplo.test', now=T0)
        kw = pr.email_for(u, token)
        self.assertEqual((kw['to'], kw['kind'], kw['subject']), ('rosa@ejemplo.test', 'reset', 'Restablece tu contraseña'))
        self.assertEqual(emails.check(kw['subject']), '')
        self.assertIn('/restablecer?t=' + token, kw['text'])
        self.assertIn('/restablecer?t=' + token, kw['html'])
        self.assertIn('Hola Rosa,', kw['text'])
        self.assertIn('60 minutos', kw['text'])
        self.assertNotIn('<style', kw['html'])                          # inline styles only
        self.assertNotIn('<img', kw['html'])                            # no hotlinked logo


class Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('reset')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()
        self.mails = []
        con = db.connect()
        for table in ('rate_events', 'password_resets', 'outbox'):
            con.execute('DELETE FROM %s' % table)
        con.commit()
        con.close()
        self._p = [mock.patch.object(mailer, '_smtp_send', lambda msg, cfg: self.mails.append(msg)), mock.patch.object(mailer, 'ASYNC', False),
                   mock.patch('smtplib.SMTP', side_effect=AssertionError('real SMTP')), mock.patch('smtplib.SMTP_SSL', side_effect=AssertionError('real SMTP'))]
        [p.start() for p in self._p]
        self.addCleanup(lambda: [p.stop() for p in self._p])

    def ask(self, email, **extra):
        data = {'email': email}
        data.update(extra)
        return self.web.req('/olvide', data)

    def reset_path(self):
        return '/restablecer?t=' + link_in(self.mails[-1])

    # ---- the entry point depends on mail being available
    def test_the_link_on_entrar_and_the_page_need_working_mail(self):
        with mail_env(**OFF):
            s, page, _ = self.web.req('/entrar')
            self.assertNotIn('/olvide', page)
            s, page, _ = self.web.req('/olvide')
            self.assertEqual(s, 200)
            self.assertIn('todavía no hay recuperación por correo', page)
            self.assertNotIn('name="email"', page)
            s, page, _ = self.ask(self.u['email'])
            self.assertEqual(s, 503)
            self.assertEqual(self.web.q('SELECT * FROM password_resets'), [])
        with mail_env():
            s, page, _ = self.web.req('/entrar')
            self.assertIn('href="/olvide"', page)
            self.assertIn('¿Olvidaste tu contraseña?', page)
            s, page, _ = self.web.req('/olvide')
            self.assertIn('Enviarme el enlace', page)

    # ---- same answer, any email
    def test_same_response_for_known_and_unknown_emails(self):
        with mail_env():
            s1, b1, _ = self.ask(self.u['email'])
            s2, b2, _ = self.ask('nadie-existe@ejemplo.test')
            s3, b3, _ = self.ask(self.u['email'].upper())
        self.assertEqual((s1, s2, s3), (200, 200, 200))
        self.assertEqual(b1, b2)
        self.assertEqual(b1, b3)
        self.assertIn('Si ese correo tiene cuenta', b1)
        self.assertEqual([m['To'] for m in self.mails], [self.u['email'], self.u['email']])      # nothing went to the unknown address
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM password_resets')[0] >= 1, True)

    def test_a_malformed_email_gets_a_form_error_not_a_probe(self):
        with mail_env():
            s, page, _ = self.ask('esto-no-es-correo')
        self.assertEqual(s, 400)
        self.assertIn('Revisa tu correo', page)
        self.assertEqual(self.mails, [])

    def test_honeypot_looks_the_same_and_does_nothing(self):
        with mail_env():
            s, page, _ = self.ask(self.u['email'], website='http://spam.test')
        self.assertEqual(s, 200)
        self.assertIn('Si ese correo tiene cuenta', page)
        self.assertEqual(self.mails, [])

    def test_outbox_keeps_who_but_never_the_link(self):
        with mail_env():
            self.ask(self.u['email'])
        token = link_in(self.mails[-1])
        rows = self.web.q("SELECT * FROM outbox WHERE kind='email.reset'")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['status'], json.loads(rows[0]['payload'])['to']), ('sent', self.u['email']))
        self.assertNotIn(token, json.dumps([dict(r) for r in rows]))
        self.assertNotIn(token, json.dumps([list(r) for r in self.web.q('SELECT * FROM password_resets')]))
        self.assertNotIn(SMTP['LLAVE_SMTP_PASSWORD'], json.dumps([dict(r) for r in rows]))

    def test_mail_goes_out_from_a_worker_thread_when_async(self):
        with mail_env(), mock.patch.object(mailer, 'ASYNC', True):
            s, _, _ = self.ask(self.u['email'])
            mailer.wait()
        self.assertEqual(s, 200)
        self.assertEqual(len(self.mails), 1)

    # ---- the full trip
    def test_full_reset_flow(self):
        with mail_env():
            self.ask(self.u['email'])
        path = self.reset_path()
        s, page, _ = self.web.req(path)
        self.assertEqual(s, 200)
        self.assertIn('Elige tu contraseña nueva', page)
        token = link_in(self.mails[-1])
        # a mismatch or a weak password does not use up the link
        s, page, _ = self.web.req('/restablecer', {'t': token, 'password': 'clave-nueva-123', 'password2': 'otra-cosa-1234'})
        self.assertEqual(s, 400)
        self.assertIn('no coinciden', page)
        s, page, _ = self.web.req('/restablecer', {'t': token, 'password': 'corta', 'password2': 'corta'})
        self.assertEqual(s, 400)
        self.assertIn('al menos 8', page)
        self.assertEqual(self.web.req(path)[0], 200)
        # the existing session of this user (the one from sign-up) works until the reset
        self.assertEqual(self.web.req('/propiedades', cookie=self.u['cookie'])[0], 200)
        s, _, h = self.web.req('/restablecer', {'t': token, 'password': 'clave-nueva-123', 'password2': 'clave-nueva-123'})
        self.assertEqual((s, h['Location']), (303, '/'))
        new_cookie = h['Set-Cookie'].split(';')[0]
        self.assertEqual(self.web.req('/propiedades', cookie=new_cookie)[0], 200)             # signed in with a fresh session
        s, _, h = self.web.req('/propiedades', cookie=self.u['cookie'])                       # the old one is gone
        self.assertEqual((s, h['Location']), (303, '/entrar'))
        self.assertEqual(self.web.req('/entrar', {'email': self.u['email'], 'password': 'clave-nueva-123'})[0], 303)
        self.assertEqual(self.web.req('/entrar', {'email': self.u['email'], 'password': self.u['password']})[0], 401)
        # the link is spent
        for method_args in ((path,), ('/restablecer', {'t': token, 'password': 'otra-nueva-1234', 'password2': 'otra-nueva-1234'})):
            s, page, _ = self.web.req(*method_args)
            self.assertEqual(s, 400)
            self.assertIn('Este enlace ya no sirve', page)
        self.assertEqual(self.web.req('/entrar', {'email': self.u['email'], 'password': 'clave-nueva-123'})[0], 303)

    def test_an_expired_link_is_refused(self):
        with mail_env():
            self.ask(self.u['email'])
        con = db.connect()
        con.execute("UPDATE password_resets SET expires_at=datetime('now','-1 minute')")
        con.commit()
        con.close()
        s, page, _ = self.web.req(self.reset_path())
        self.assertEqual(s, 400)
        self.assertIn('ya se usó o venció', page)
        s, _, _ = self.web.req('/restablecer', {'t': link_in(self.mails[-1]), 'password': 'clave-nueva-123', 'password2': 'clave-nueva-123'})
        self.assertEqual(s, 400)

    def test_garbage_tokens_get_the_same_refusal(self):
        for t in ('', 'x', 'a' * 500, "' OR 1=1 --", '../../etc/passwd'):
            s, page, _ = self.web.req('/restablecer?t=' + urllib.parse.quote(t))
            self.assertEqual(s, 400, t)
            self.assertIn('Este enlace ya no sirve', page)
            s, _, _ = self.web.req('/restablecer', {'t': t, 'password': 'clave-nueva-123', 'password2': 'clave-nueva-123'})
            self.assertEqual(s, 400, t)

    # ---- limits
    def test_per_email_limit_counts_unknown_emails_too(self):
        with mail_env(), mock.patch.object(server, 'RESET_PER_EMAIL_HOUR', 2), mock.patch.object(server, 'RESET_PER_IP_HOUR', 100):
            for email in (self.u['email'], 'nadie-existe@ejemplo.test'):
                codes = [self.ask(email)[0] for _ in range(4)]
                self.assertEqual(codes, [200, 200, 429, 429], email)                         # known and unknown behave the same
        self.assertEqual(len(self.mails), 2)

    def test_per_ip_limit(self):
        with mail_env(), mock.patch.object(server, 'RESET_PER_IP_HOUR', 3), mock.patch.object(server, 'RESET_PER_EMAIL_HOUR', 100):
            codes = [self.ask('persona%d@ejemplo.test' % i)[0] for i in range(5)]
            s, page, _ = self.ask('otra@ejemplo.test')
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertEqual(s, 429)
        self.assertIn('Espera un rato', page)

    # ---- schema
    def test_supabase_has_the_table_with_rls(self):
        pg = test_pg_parity.pg_schema()
        self.assertEqual(pg['password_resets'], {'token_hash', 'user_id', 'expires_at', 'used_at', 'created_at'})
        with open(os.path.join(test_pg_parity.ROOT, 'supabase', 'migrations', '0007_password_resets.sql'), encoding='utf-8') as fh:
            sql = fh.read()
        self.assertIn('alter table public.password_resets enable row level security', sql)
        self.assertNotIn('create policy', sql)                                           # no policies, no grants: server only

    def test_old_databases_get_the_table_on_init(self):
        con = db.connect(':memory:')
        db.init(con)
        con.execute('DROP TABLE password_resets')
        db.init(con)
        self.assertEqual({r[1] for r in con.execute('PRAGMA table_info(password_resets)')},
                         {'token_hash', 'user_id', 'expires_at', 'used_at', 'created_at'})


if __name__ == '__main__':
    unittest.main()
