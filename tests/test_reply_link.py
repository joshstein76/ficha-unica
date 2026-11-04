"""The "Responder por WhatsApp" button of an agent email (llave/reply_link.py, /w/<token>).
A scanner that GETs the link must change nothing; the POST behind the big button records the reply the way the panel does and opens WhatsApp;
a dead link shows no name and no phone. No real SMTP, no network beyond a local test server."""
import datetime
import http.client
import io
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import db, lead_watch as lw, mailer, reply_link  # noqa: E402
from llave.web import common  # noqa: E402
import web_harness  # noqa: E402

NOW = datetime.datetime(2026, 11, 3, 16, 0, 0)
PHONE = '+525511119999'


class Token(unittest.TestCase):
    def test_round_trip_and_binding(self):
        t = reply_link.make(7, 3, 5, now=NOW)
        self.assertEqual(reply_link.read(t, now=NOW), (7, 3, 5))
        self.assertEqual(reply_link.read(reply_link.make(7, 3, now=NOW), now=NOW), (7, 3, 0))      # the agency-email fallback has no user
        a, b, c, exp, sig = t.split('.')
        for forged in ('8.%s.%s.%s.%s' % (b, c, exp, sig),                  # another lead
                       '%s.4.%s.%s.%s' % (a, c, exp, sig),                  # another agency
                       '%s.%s.6.%s.%s' % (a, b, exp, sig),                  # another person
                       '%s.%s.%s.%d.%s' % (a, b, c, int(exp) + 86400, sig),  # a longer life
                       '%s.%s.%s.%s.%s' % (a, b, c, exp, '0' * 32),
                       '%s.%s.%s.%s.%s' % (a, b, c, exp, 'é' * 32)):        # non-ASCII must be a no, not an error
            self.assertIsNone(reply_link.read(forged, now=NOW), forged)

    def test_expires_after_30_days(self):
        t = reply_link.make(7, 3, 5, now=NOW)
        self.assertEqual(reply_link.TTL_DAYS, 30)
        self.assertTrue(reply_link.read(t, now=NOW + datetime.timedelta(days=29, hours=23)))
        self.assertIsNone(reply_link.read(t, now=NOW + datetime.timedelta(days=30, seconds=1)))

    def test_garbage_and_other_secrets(self):
        for bad in (None, '', 'x', '1.2.3', '1.2.3.4', 'a.b.c.d.e', '-1.2.3.4.' + 'a' * 32, '0.2.3.4.' + 'a' * 32, '1.2.3.4.5.6', 'x' * 400,
                    '1.2.-3.%d.%s' % (10 ** 10, 'a' * 32)):
            self.assertIsNone(reply_link.read(bad, now=NOW), bad)
        t = reply_link.make(7, 3, 5, now=NOW)
        with mock.patch.object(common, 'SECRET', 'another-secret-that-is-long-enough-xx'):
            self.assertIsNone(reply_link.read(t, now=NOW))                  # a rotated app secret ends every old link

    def test_url_is_on_the_app_host(self):
        u = reply_link.url(7, 3, 5)
        self.assertTrue(u.startswith(db.origin('app') + '/w/'), u)
        self.assertEqual(reply_link.read(u.rsplit('/', 1)[1]), (7, 3, 5))


class Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('replylink')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()
        self.aid, self.uid = self.u['aid'], self.u['uid']
        self.con = db.connect()
        self.addCleanup(self.con.close)
        lw.ensure_columns(self.con)
        self.lid = self.con.execute("INSERT INTO listings(agency_id, ref, slug, status, title, colonia, municipio, estado, operation, property_type) "
                                    "VALUES (?, 'W-%d','depto-roma','activa','Depto en Roma Norte','Roma','Cuauhtémoc','CDMX','venta','departamento')"
                                    % self.aid, (self.aid,)).lastrowid
        self.con.commit()

    def lead(self, agency=None, owner=None, phone=PHONE, status='nuevo', minutes_ago=9, **kw):
        agency = agency or self.aid
        created = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes_ago)).strftime(lw.FMT)
        lid = self.con.execute("INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, created_at, status, first_response_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (agency, owner or agency, self.lid, kw.get('name', 'Marta Pérez'), phone, 'marta@cliente.test', 'Hola', created, status,
                                kw.get('resp'))).lastrowid
        self.con.commit()
        return lid

    def row(self, lid):
        return self.con.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()

    def link(self, lid, agency=None, user=None, now=None):
        return '/w/' + reply_link.make(lid, agency or self.aid, self.uid if user is None else user, now=now)

    def audit(self, lid):
        """The 'lead_responded' rows of one lead (the test database is shared by the whole class)."""
        return [(x['actor'], x['detail']) for x in self.con.execute(
            "SELECT * FROM audit WHERE action='lead_responded' AND (detail=? OR detail LIKE ?) ORDER BY id", ('lead:%d' % lid, 'lead:%d %%' % lid))]

    def head(self, path):
        c = http.client.HTTPConnection('127.0.0.1', self.web.port, timeout=15)
        c.request('HEAD', path, headers={'Host': web_harness.APP})
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def assert_private_headers(self, h):
        self.assertEqual(h.get_all('Referrer-Policy'), ['no-referrer'])         # one header, the strict one
        self.assertIn('noindex', h['X-Robots-Tag'])
        self.assertIn('no-store', h['Cache-Control'])

    # ---------- GET changes nothing ----------
    def test_get_shows_one_button_and_records_nothing(self):
        lid = self.lead()
        path = self.link(lid)
        for _ in range(3):                                                      # a scanner, a link preview and the agent's phone
            s, page, h = self.web.req(path)
            self.assertEqual(s, 200)
        self.assert_private_headers(h)
        self.assertEqual(self.head(path), 200)
        self.assertIn('Responder por WhatsApp', page)
        self.assertRegex(page, r'<form[^>]*method="post"[^>]*action="%s"' % re.escape(path))
        self.assertIn('Marta Pérez', page)
        self.assertIn('Depto en Roma Norte', page)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', page)
        self.assertIn('<meta name="referrer" content="no-referrer">', page)
        for leak in ('wa.me', '5511119999', '55 1111 9999', 'marta@cliente.test'):
            self.assertNotIn(leak, page)                                        # the page itself holds no number
        r = self.row(lid)
        self.assertEqual((r['status'], r['first_response_at']), ('nuevo', None))
        self.assertEqual(self.audit(lid), [])
        self.assertEqual([x['id'] for x in lw.overdue(self.con, 5) if x['id'] == lid], [lid])      # the 5-minute reminder still applies

    # ---------- POST records and opens WhatsApp ----------
    def test_post_records_the_reply_and_opens_whatsapp(self):
        lid = self.lead()
        s, _, h = self.web.req(self.link(lid), {})                              # no cookie: the token is the key
        self.assertEqual(s, 303)
        self.assertEqual(h.get_all('Referrer-Policy'), ['no-referrer'])
        loc = h['Location']
        self.assertTrue(loc.startswith('https://wa.me/525511119999?text='), loc)
        self.assertIn('Soy%20Rosa%20de%20', loc)                                # the agent's first name, as in the email
        r = self.row(lid)
        self.assertEqual(r['status'], 'contactado')
        self.assertTrue(r['first_response_at'])
        self.assertEqual(self.audit(lid), [('agency:%d' % self.aid, 'lead:%d via:correo' % lid)])
        self.assertEqual([x['id'] for x in lw.overdue(self.con, 5) if x['id'] == lid], [])         # no reminder for an answered lead
        self.assertEqual([x for x in lw.overdue(self.con, 5) if x['id'] == lid], [])

    def test_post_twice_changes_nothing_more(self):
        lid = self.lead()
        s1, _, h1 = self.web.req(self.link(lid), {})
        first = self.row(lid)['first_response_at']
        s2, _, h2 = self.web.req(self.link(lid), {})
        self.assertEqual((s1, s2), (303, 303))
        self.assertEqual(h1['Location'], h2['Location'])
        r = self.row(lid)
        self.assertEqual((r['status'], r['first_response_at']), ('contactado', first))
        self.assertEqual(len(self.audit(lid)), 1)
        s3, page, _ = self.web.req(self.link(lid))                              # looking again says so
        self.assertEqual(s3, 200)
        self.assertIn('Ya lo habías marcado como contactado', page)

    def test_a_lead_the_agent_already_moved_keeps_its_status(self):
        lid = self.lead(status='cita', resp='2026-11-03 10:00:00')
        s, _, h = self.web.req(self.link(lid), {})
        self.assertEqual(s, 303)
        r = self.row(lid)
        self.assertEqual((r['status'], r['first_response_at']), ('cita', '2026-11-03 10:00:00'))

    def test_same_wording_and_effect_as_the_panel_route(self):
        a, b = self.lead(), self.lead()
        s, _, panel_h = self.web.req('/clientes/%d/whatsapp' % a, cookie=self.u['cookie'])
        s2, _, mail_h = self.web.req(self.link(b), {})
        self.assertEqual((s, s2), (303, 303))
        self.assertEqual(panel_h['Location'], mail_h['Location'])
        ra, rb = self.row(a), self.row(b)
        self.assertEqual((ra['status'], bool(ra['first_response_at'])), (rb['status'], bool(rb['first_response_at'])))
        self.assertEqual(rb['status'], 'contactado')

    def test_panel_route_still_refuses_another_agencys_lead_and_a_missing_phone(self):
        other = self.web.signup()
        theirs = self.lead(agency=other['aid'])
        nophone = self.lead(phone='')
        for lid in (theirs, nophone):
            s, _, h = self.web.req('/clientes/%d/whatsapp' % lid, cookie=self.u['cookie'])
            self.assertEqual((s, h['Location']), (303, '/clientes'))
            self.assertEqual(self.row(lid)['status'], 'nuevo')

    def test_works_for_any_agency_and_never_across_them(self):
        other = self.web.signup()
        mine, theirs = self.lead(), self.lead(agency=other['aid'])
        t_other = reply_link.make(theirs, other['aid'], other['uid'])
        s, _, h = self.web.req('/w/' + t_other, {})
        self.assertEqual(s, 303)
        self.assertEqual((self.row(theirs)['status'], self.row(mine)['status']), ('contactado', 'nuevo'))
        # agency B's signature on agency A's lead: the lead is not B's, so nothing opens and nothing changes
        s, page, _ = self.web.req('/w/' + reply_link.make(mine, other['aid'], other['uid']), {})
        self.assertEqual(s, 404)
        self.assertEqual(self.row(mine)['status'], 'nuevo')
        # a token cannot be re-pointed at another lead
        a, b, c, exp, sig = t_other.split('.')
        s, _, _ = self.web.req('/w/%d.%s.%s.%s.%s' % (mine, b, c, exp, sig), {})
        self.assertEqual(s, 404)
        self.assertEqual(self.row(mine)['status'], 'nuevo')

    def test_bolsa_owner_gets_whatsapp_but_the_row_stays_the_receiving_agencys(self):
        other = self.web.signup()
        lid = self.lead(agency=other['aid'], owner=self.aid)                    # a client of `other` on a property of this agency
        s, _, h = self.web.req(self.link(lid), {})                              # the OWNER's email
        self.assertEqual(s, 303)
        self.assertTrue(h['Location'].startswith('https://wa.me/525511119999?text='))
        self.assertEqual(self.row(lid)['status'], 'nuevo')                      # not the owner's row to move
        s, _, _ = self.web.req(self.link(lid, agency=other['aid'], user=other['uid']), {})   # the receiving agency's email
        self.assertEqual((s, self.row(lid)['status']), (303, 'contactado'))

    # ---------- a dead link leaks nothing ----------
    def test_dead_links_show_one_plain_page_without_the_client(self):
        gone = self.lead()
        nophone = self.lead(phone='')
        old = self.lead()
        deleted_agency_lead = self.lead()
        self.con.execute('DELETE FROM leads WHERE id=?', (gone,))
        self.con.commit()
        dead = [self.link(gone),                                                # lead deleted
                self.link(nophone),                                             # nothing to open
                self.link(old, now=datetime.datetime.utcnow() - datetime.timedelta(days=31)),   # expired
                '/w/' + 'a' * 30,                                               # not a token
                '/w/%d.%d.%d.%d.%s' % (deleted_agency_lead, self.aid, self.uid, 4102444800, '0' * 32),   # forged
                self.link(deleted_agency_lead)[:-1] + ('0' if not self.link(deleted_agency_lead).endswith('0') else '1')]   # one wrong character
        for path in dead:
            for method_data in (None, {}):
                s, page, h = self.web.req(path, method_data)
                self.assertEqual(s, 404, path)
                self.assertIn('Este enlace ya no sirve', page)
                self.assertIn('href="/entrar"', page)
                for leak in ('wa.me', '5511119999', 'Marta', 'marta@cliente.test', 'Depto en Roma'):
                    self.assertNotIn(leak, page, path)
                self.assertNotIn('Location', h)
                self.assert_private_headers(h)
        for lid in (nophone, old, deleted_agency_lead):
            self.assertEqual(self.row(lid)['status'], 'nuevo')

    def test_a_deleted_agent_still_gets_the_link_signed_by_the_agency(self):
        lid = self.lead()
        s, _, h = self.web.req(self.link(lid, user=987654), {})                 # a person who no longer exists
        self.assertEqual(s, 303)
        self.assertRegex(h['Location'], r'Somos%20|Soy%20')                     # the default wording without a person: "Somos <agency>"
        self.assertEqual(self.row(lid)['status'], 'contactado')

    # ---------- logs and the rest of the site ----------
    def test_the_token_never_reaches_our_log(self):
        lid = self.lead()
        path = self.link(lid)
        err = io.StringIO()
        with mock.patch.object(sys, 'stderr', err):
            self.web.req(path)
            self.web.req(path, {})
        out = err.getvalue()
        self.assertIn('/w/[REDACTED]', out)
        self.assertNotIn(path.rsplit('/', 1)[1], out)

    def test_other_pages_keep_their_normal_referrer_policy(self):
        s, _, h = self.web.req('/entrar')
        self.assertEqual(h.get_all('Referrer-Policy'), ['strict-origin-when-cross-origin'])

    def test_only_get_and_post_open_a_link(self):
        lid = self.lead()
        c = http.client.HTTPConnection('127.0.0.1', self.web.port, timeout=15)
        c.request('PUT', self.link(lid), body=b'', headers={'Host': web_harness.APP})
        r = c.getresponse()
        r.read()
        c.close()
        self.assertEqual(self.row(lid)['status'], 'nuevo')


class FromTheEmail(unittest.TestCase):
    """The whole path with the real emails: a lead arrives, the agent taps the button in the email, the reminder never fires."""
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('replylinkmail')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.mails = []
        self._p = [mock.patch.object(mailer, '_smtp_send', lambda msg, cfg: self.mails.append(msg)), mock.patch.object(mailer, 'ASYNC', False),
                   mock.patch('smtplib.SMTP', side_effect=AssertionError('real SMTP')), mock.patch('smtplib.SMTP_SSL', side_effect=AssertionError('real SMTP')),
                   mock.patch.dict(os.environ, {'LLAVE_SMTP_HOST': 'smtp.ejemplo.test', 'LLAVE_SMTP_PORT': '587', 'LLAVE_SMTP_USER': 'a@ejemplo.test',
                                                'LLAVE_SMTP_PASSWORD': 'pw-not-real', 'LLAVE_SMTP_FROM': 'Ficha Única <a@ejemplo.test>'})]
        [p.start() for p in self._p]
        self.addCleanup(lambda: [p.stop() for p in self._p])
        self.u = self.web.signup()
        self.slug = self.web.one('SELECT slug FROM agencies WHERE id=?', self.u['aid'])[0]
        con = db.connect()
        self.zone = 'Zona%dY' % self.u['aid']
        self.lid = con.execute("INSERT INTO listings(agency_id, ref, slug, status, title, colonia, municipio, estado, operation, property_type) "
                               "VALUES (?, 'W-1','depto-condesa','activa','Depto en la Condesa',?,'Cuauhtémoc','CDMX','venta','departamento')",
                               (self.u['aid'], self.zone)).lastrowid
        con.commit()
        con.close()

    def body(self, msg, kind='plain'):
        return msg.get_body((kind,)).get_content()

    def test_new_lead_email_then_tap_then_no_reminder(self):
        s, _, _ = self.web.req('/contacto', {'listing': self.lid, 'name': 'Carla Ruiz', 'phone': '55 4444 5555', 'email': 'carla@visita.test',
                                              'message': '¿Sigue disponible?', 'consent': '1'}, host='%s.fichaunica.localhost' % self.slug)
        self.assertEqual(s, 303)
        mail, = self.mails
        link = re.search(r'%s(/w/[A-Za-z0-9._-]+)' % re.escape(db.origin('app')), self.body(mail)).group(1)
        self.assertIn(link, self.body(mail, 'html'))
        # the reminder, 10 minutes later, is for a lead nobody answered: the scanner's GET does not change that
        for _ in range(2):
            self.web.req(link)
        con = db.connect()
        try:
            self.assertEqual(len([x for x in lw.overdue(con, 5, now=datetime.datetime.utcnow() + datetime.timedelta(minutes=10))]), 1)
            s, _, h = self.web.req(link, {})
            self.assertEqual(s, 303)
            self.assertIn('https://wa.me/525544445555?text=', h['Location'])
            self.assertEqual(lw.remind(con, now=datetime.datetime.utcnow() + datetime.timedelta(minutes=10)), 0)
            self.assertEqual(len(self.mails), 1)                                # no "sin respuesta" email either
        finally:
            con.close()

    def test_reminder_email_carries_a_working_link_too(self):
        con = db.connect()
        try:
            created = (datetime.datetime.utcnow() - datetime.timedelta(minutes=8)).strftime(lw.FMT)
            lid = con.execute("INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, created_at) "
                              "VALUES (?,?,?,?,?,?,?,?)", (self.u['aid'], self.u['aid'], self.lid, 'Marta Pérez', PHONE, 'm@c.test', 'Hola', created)).lastrowid
            con.commit()
            self.assertEqual(lw.remind(con), 1)
            mail, = self.mails
            self.assertEqual(mail['Subject'], 'Sin respuesta: Marta, 8 min')
            self.assertNotIn('wa.me', self.body(mail) + self.body(mail, 'html'))
            link = re.search(r'%s(/w/[A-Za-z0-9._-]+)' % re.escape(db.origin('app')), self.body(mail)).group(1)
            s, _, h = self.web.req(link, {})
            self.assertEqual(s, 303)
            self.assertTrue(h['Location'].startswith('https://wa.me/525511119999?text='))
            self.assertEqual(con.execute('SELECT status FROM leads WHERE id=?', (lid,)).fetchone()[0], 'contactado')
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()
