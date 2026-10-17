import datetime, json, os, tempfile, unittest
from llave import alerts

T0 = datetime.datetime(2026, 10, 17, 12, 0, 0)


class Rec:
    def __init__(self, boom=False):
        self.calls = []; self.boom = boom

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.boom:
            raise RuntimeError('network down')


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.log = os.path.join(self.d, 'logs', 'errors.log')

    def cfg(self, **kw):
        env = {'LLAVE_ALERT_LOG': self.log}
        env.update(kw)
        return alerts.configure(env)

    def prod(self):
        return self.cfg(LLAVE_ENV='production', LLAVE_ALERT_WEBHOOK='https://hooks.invalid/x')

    def test_redaction(self):
        s = alerts.redact('password=hunter2 token: abc123 "csrf": "zzz" Authorization: Bearer q.w.e '
                          'mail juan.perez@example.com tel +52 55 1234 5678 y 5511112222 ok 12345')
        for bad in ('hunter2', 'abc123', 'zzz', 'q.w.e', 'juan.perez', '1234 5678', '551111'):
            self.assertNotIn(bad, s)
        self.assertIn('@example.com', s)
        self.assertIn('5678', s)       # last 4 kept
        self.assertIn('2222', s)
        self.assertIn('12345', s)      # short number untouched

    def test_report_redacts_and_logs(self):
        self.cfg()
        try:
            raise ValueError('bad password=secret99 for a@b.com')
        except ValueError as e:
            a = alerts.report(e, {'path': '/x?token=abc', 'host': 'h', 'method': 'POST', 'cookie': 'sess'}, now=T0)
        blob = json.dumps(a)
        self.assertNotIn('secret99', blob); self.assertNotIn('a@b.com', blob); self.assertNotIn('sess', blob)
        self.assertEqual(set(a['context']), {'path', 'host', 'method'})
        self.assertLessEqual(len(a['summary']), 300)
        self.assertEqual(a['mode'], 'dry')
        with open(self.log) as f:
            self.assertEqual(json.loads(f.readline())['signature'], a['signature'])

    def test_signature_stable(self):
        self.cfg()
        def boom():
            raise KeyError('x')
        sigs = []
        for _ in range(2):
            try:
                boom()
            except KeyError as e:
                sigs.append(alerts.report(e, now=T0)['signature'])
        self.assertEqual(sigs[0], sigs[1])
        self.assertNotEqual(sigs[0], alerts.report('otro mensaje', now=T0)['signature'])

    def test_dry_never_sends(self):
        r = Rec()
        self.cfg(LLAVE_ALERT_WEBHOOK='https://hooks.invalid/x')  # configured but env not production
        self.assertEqual(alerts.report('boom', sender=r, now=T0)['mode'], 'dry')
        self.cfg(LLAVE_ENV='production')  # production but nothing configured
        self.assertEqual(alerts.report('boom', sender=r, now=T0)['mode'], 'dry')
        self.assertEqual(r.calls, [])

    def test_production_webhook_once_and_rate_limit(self):
        self.prod()
        r = Rec()
        a1 = alerts.report('db down', sender=r, now=T0)
        self.assertEqual((a1['mode'], a1['count'], len(r.calls)), ('sent', 1, 1))
        self.assertEqual(r.calls[0][0], 'https://hooks.invalid/x')
        a2 = alerts.report('db down', sender=r, now=T0 + datetime.timedelta(minutes=5))
        self.assertEqual((a2['mode'], len(r.calls)), ('suppressed', 1))
        a3 = alerts.report('db down', sender=r, now=T0 + datetime.timedelta(minutes=10))
        self.assertEqual(a3['mode'], 'suppressed')
        a4 = alerts.report('db down', sender=r, now=T0 + datetime.timedelta(minutes=16))
        self.assertEqual((a4['mode'], a4['count'], len(r.calls)), ('sent', 3, 2))
        self.assertEqual(r.calls[1][1]['count'], 3)

    def test_email_sender(self):
        self.cfg(LLAVE_ENV='production', LLAVE_ALERT_EMAIL_TO='ops@example.com', LLAVE_SMTP_HOST='smtp.invalid')
        got = []
        a = alerts.report('x', sender={'email': got.append}, now=T0)
        self.assertEqual(a['mode'], 'sent')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['To'], 'ops@example.com')

    def test_never_raises(self):
        self.prod()
        a = alerts.report('x', sender=Rec(boom=True), now=T0)
        self.assertEqual(a['mode'], 'error')
        # unwritable log + weird input
        alerts.configure({'LLAVE_ALERT_LOG': '/proc/nope/errors.log'})
        self.assertIsInstance(alerts.report(object(), context=None), dict)

    def test_heartbeat_shape(self):
        h = alerts.heartbeat()
        self.assertEqual(set(h), {'ok', 'db_ok', 'disk_free_mb', 'last_backup_age_h'})


if __name__ == '__main__':
    unittest.main()
