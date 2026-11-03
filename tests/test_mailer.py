"""llave/mailer.py: dry run without SMTP, send + record with SMTP, refuses empty mail, never raises, never leaks the password.
No test here opens a connection: smtplib.SMTP / SMTP_SSL are replaced by guards or by recording fakes."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db, mailer  # noqa: E402

SMTP = {'LLAVE_SMTP_HOST': 'smtp.ejemplo.test', 'LLAVE_SMTP_PORT': '587', 'LLAVE_SMTP_USER': 'avisos@ejemplo.test',
        'LLAVE_SMTP_PASSWORD': 'sup3r-secret-pw', 'LLAVE_SMTP_FROM': 'Ficha Única <avisos@ejemplo.test>'}
OFF = {k: '' for k in SMTP}


def env(**kw):
    d = dict(SMTP)
    d.update(kw)
    return mock.patch.dict(os.environ, d)


class NoRealSmtp(unittest.TestCase):
    """Base: any attempt to open a real SMTP connection fails the test."""

    def setUp(self):
        def boom(*a, **k):
            raise AssertionError('a real SMTP connection was attempted')

        self._p = [mock.patch('smtplib.SMTP', boom), mock.patch('smtplib.SMTP_SSL', boom)]
        [p.start() for p in self._p]
        self.addCleanup(lambda: [p.stop() for p in self._p])
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 'm.db'))
        db.init(self.con)

    def rows(self):
        return self.con.execute('SELECT * FROM outbox ORDER BY id').fetchall()


class Settings(unittest.TestCase):
    def test_enabled_needs_host_and_a_from_address(self):
        self.assertFalse(mailer.enabled(OFF))
        self.assertTrue(mailer.enabled(SMTP))
        self.assertFalse(mailer.enabled(dict(SMTP, LLAVE_SMTP_HOST='')))
        self.assertTrue(mailer.enabled(dict(SMTP, LLAVE_SMTP_FROM='')))                       # the user is an address: it becomes the From
        self.assertFalse(mailer.enabled(dict(SMTP, LLAVE_SMTP_FROM='', LLAVE_SMTP_USER='usuario')))
        self.assertFalse(mailer.enabled(dict(SMTP, LLAVE_SMTP_FROM='no es una dirección')))

    def test_port_defaults_and_bad_values(self):
        self.assertEqual(mailer.config({'LLAVE_SMTP_HOST': 'h'})['port'], 587)
        self.assertEqual(mailer.config({'LLAVE_SMTP_PORT': 'abc'})['port'], 587)
        self.assertEqual(mailer.config({'LLAVE_SMTP_PORT': '465'})['port'], 465)

    def test_half_configured_is_reported_not_enabled(self):
        self.assertEqual(mailer.config_problems(OFF), [])
        self.assertEqual(mailer.config_problems(SMTP), [])
        self.assertTrue(mailer.config_problems(dict(OFF, LLAVE_SMTP_USER='x@ejemplo.test')))


class DryRun(NoRealSmtp):
    def test_without_smtp_the_message_goes_to_the_outbox_and_nothing_leaves(self):
        with env(**OFF):
            r = mailer.send(self.con, 'rosa@ejemplo.test', 'Nuevo cliente: Ana', 'Ana quiere ver el depa.', '<p>Ana</p>', kind='lead_nuevo', ref='lead:1')
        self.assertEqual((r['ok'], r['status'], r['delivered']), (True, 'dry_run', False))
        row, = self.rows()
        self.assertEqual((row['kind'], row['status'], row['ref']), ('email.lead_nuevo', 'dry_run', 'lead:1'))
        p = json.loads(row['payload'])
        self.assertEqual((p['to'], p['subject'], p['text']), ('rosa@ejemplo.test', 'Nuevo cliente: Ana', 'Ana quiere ver el depa.'))

    def test_never_raises_even_when_the_database_is_gone(self):
        self.con.close()
        with env(**OFF), mock.patch('sys.stderr'):
            r = mailer.send(self.con, 'rosa@ejemplo.test', 'Hola', 'Cuerpo')
        self.assertEqual((r['ok'], r['status']), (False, 'error'))

    def test_private_kinds_never_store_their_text(self):
        with env(**OFF):
            mailer.send(self.con, 'rosa@ejemplo.test', 'Restablece tu contraseña', 'Entra aquí: https://x/restablecer?t=SECRETO', kind='reset')
        row, = self.rows()
        self.assertNotIn('SECRETO', row['payload'])
        self.assertEqual(json.loads(row['payload'])['to'], 'rosa@ejemplo.test')


class Refusals(NoRealSmtp):
    def test_empty_subject_or_body_is_refused_and_never_sent(self):
        sent = []
        with env():
            for subject, text, html in (('', 'cuerpo', None), ('   ', 'cuerpo', None), ('Asunto', '', None), ('Asunto', '  \n ', None),
                                        ('Asunto', None, '<p>solo html</p>'), (None, None, None)):
                r = mailer.send(self.con, 'rosa@ejemplo.test', subject, text, html, kind='lead_nuevo', sender=lambda m, c: sent.append(m))
                self.assertEqual((r['ok'], r['status'], r['delivered']), (False, 'refused', False), (subject, text))
        self.assertEqual(sent, [])
        rows = self.rows()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r['status'] == 'error' and r['response'].startswith('rechazado') for r in rows))

    def test_empty_is_refused_in_dry_run_too(self):
        with env(**OFF):
            r = mailer.send(self.con, 'rosa@ejemplo.test', '', 'cuerpo')
        self.assertEqual(r['status'], 'refused')
        self.assertEqual(self.rows()[0]['status'], 'error')

    def test_bad_recipients_and_header_injection_are_refused(self):
        sent = []
        with env():
            for to in ('', 'no-es-correo', 'a@b', 'rosa@ejemplo.test\nBcc: x@y.test', 'a@ejemplo.test, b@ejemplo.test', None):
                r = mailer.send(self.con, to, 'Asunto', 'Cuerpo', sender=lambda m, c: sent.append(m))
                self.assertEqual(r['status'], 'refused', to)
            r = mailer.send(self.con, 'rosa@ejemplo.test', 'Asunto\nBcc: x@y.test', 'Cuerpo', sender=lambda m, c: sent.append(m))
            self.assertEqual(r['status'], 'refused')
        self.assertEqual(sent, [])


class WithSmtp(NoRealSmtp):
    def test_sends_a_multipart_message_and_records_sent(self):
        got = []
        with env():
            r = mailer.send(self.con, 'rosa@ejemplo.test', 'Nuevo cliente: Ana', 'Texto plano', '<p>Hola <b>Ana</b></p>', kind='lead_nuevo',
                            ref='lead:7', sender=lambda m, c: got.append((m, c)))
        self.assertEqual((r['ok'], r['status'], r['delivered']), (True, 'sent', True))
        msg, cfg = got[0]
        self.assertEqual(msg['To'], 'rosa@ejemplo.test')
        self.assertEqual(msg['Subject'], 'Nuevo cliente: Ana')
        self.assertIn('avisos@ejemplo.test', msg['From'])
        self.assertTrue(msg['Message-ID'].endswith('@ejemplo.test>'))
        self.assertTrue(msg['Date'])
        self.assertEqual(msg.get_body(('plain',)).get_content().strip(), 'Texto plano')
        self.assertIn('<b>Ana</b>', msg.get_body(('html',)).get_content())
        self.assertEqual(cfg['host'], 'smtp.ejemplo.test')
        row, = self.rows()
        self.assertEqual((row['kind'], row['status'], row['attempts'], row['response']), ('email.lead_nuevo', 'sent', 1, msg['Message-ID']))

    def test_text_only_has_no_html_part(self):
        got = []
        with env():
            mailer.send(self.con, 'rosa@ejemplo.test', 'Hola', 'Solo texto', sender=lambda m, c: got.append(m))
        self.assertIsNone(got[0].get_body(('html',)))

    def test_a_failure_is_recorded_without_the_password_and_never_raised(self):
        pw = SMTP['LLAVE_SMTP_PASSWORD']

        def down(msg, cfg):
            raise OSError('535 login failed for avisos@ejemplo.test with password %s' % pw)

        with env(), mock.patch('sys.stderr') as err:
            r = mailer.send(self.con, 'rosa@ejemplo.test', 'Hola', 'Cuerpo', kind='lead_nuevo', sender=down)
        self.assertEqual((r['ok'], r['status'], r['delivered']), (False, 'error', False))
        row, = self.rows()
        self.assertEqual((row['status'], row['attempts']), ('error', 1))
        self.assertIn('OSError', row['response'])
        self.assertNotIn(pw, json.dumps(dict(row)))
        self.assertNotIn(pw, ''.join(str(c) for c in err.write.call_args_list))

    def test_the_password_is_never_stored_on_success_either(self):
        with env():
            mailer.send(self.con, 'rosa@ejemplo.test', 'Hola', 'Cuerpo', sender=lambda m, c: None)
        self.assertNotIn(SMTP['LLAVE_SMTP_PASSWORD'], json.dumps([dict(r) for r in self.rows()]))


class FakeSMTP:
    """Records the conversation a real smtplib.SMTP would have."""
    log = []

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.log.append(('connect', type(self).__name__, host, port, timeout, context is not None))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.log.append(('starttls', context is not None))

    def login(self, user, password):
        FakeSMTP.log.append(('login', user, password))

    def send_message(self, msg, from_addr=None):
        FakeSMTP.log.append(('send', msg['To'], from_addr))


class FakeSMTPSSL(FakeSMTP):
    pass


class Transport(unittest.TestCase):
    def run_port(self, port, user='avisos@ejemplo.test'):
        FakeSMTP.log = []
        cfg = mailer.config(dict(SMTP, LLAVE_SMTP_PORT=str(port), LLAVE_SMTP_USER=user))
        msg = mailer.build_message(cfg, 'rosa@ejemplo.test', 'Hola', 'Cuerpo')
        with mock.patch('smtplib.SMTP', FakeSMTP), mock.patch('smtplib.SMTP_SSL', FakeSMTPSSL):
            mailer._smtp_send(msg, cfg)
        return FakeSMTP.log

    def test_587_uses_starttls_then_login(self):
        log = self.run_port(587)
        self.assertEqual([x[0] for x in log], ['connect', 'starttls', 'login', 'send'])
        self.assertEqual(log[0][1:], ('FakeSMTP', 'smtp.ejemplo.test', 587, mailer.TIMEOUT, False))
        self.assertEqual(log[1], ('starttls', True))                      # certificate checked: a verifying context, not the default
        self.assertEqual(log[2], ('login', 'avisos@ejemplo.test', 'sup3r-secret-pw'))
        self.assertEqual(log[3], ('send', 'rosa@ejemplo.test', 'avisos@ejemplo.test'))

    def test_465_is_ssl_from_the_start(self):
        log = self.run_port(465)
        self.assertEqual([x[0] for x in log], ['connect', 'login', 'send'])
        self.assertEqual((log[0][1], log[0][5]), ('FakeSMTPSSL', True))

    def test_25_is_plain_and_no_user_means_no_login(self):
        log = self.run_port(25, user='')
        self.assertEqual([x[0] for x in log], ['connect', 'send'])


class OffTheRequestThread(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'd.db')
        self.con = db.connect(self.path)
        db.init(self.con)
        self.item = dict(to='rosa@ejemplo.test', subject='Hola', text='Cuerpo', kind='lead_nuevo', ref='lead:1')

    def test_real_smtp_from_a_file_database_goes_out_on_a_worker_thread(self):
        got = []
        with env(), mock.patch.object(mailer, '_smtp_send', lambda m, c: got.append(m['To'])):
            mailer.dispatch(self.con, [self.item, dict(self.item, to='beto@ejemplo.test')])
            mailer.wait()
        self.assertEqual(got, ['rosa@ejemplo.test', 'beto@ejemplo.test'])
        self.assertEqual([r['status'] for r in self.con.execute('SELECT status FROM outbox ORDER BY id')], ['sent', 'sent'])

    def test_dry_run_and_in_memory_databases_stay_inline(self):
        with env(**OFF):
            mailer.dispatch(self.con, [self.item])
        self.assertEqual(self.con.execute("SELECT status FROM outbox").fetchone()[0], 'dry_run')       # no wait() needed
        mem = db.connect(':memory:')
        db.init(mem)
        with env(), mock.patch.object(mailer, '_smtp_send', lambda m, c: None):
            mailer.dispatch(mem, [self.item])
        self.assertEqual(mem.execute("SELECT status FROM outbox").fetchone()[0], 'sent')
        mailer.dispatch(mem, [])
        mailer.dispatch(mem, [None])
        self.assertEqual(mem.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
