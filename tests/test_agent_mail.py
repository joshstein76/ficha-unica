"""Lead alerts by email (2026-11-03): new lead, 5-minute reminder, daily "Seguimiento hoy", buyer-alert match. AGENTS ONLY: never the client.
The WhatsApp dry-run rows stay as they were. Dedupe and hours are the existing ones. No real SMTP: `mailer._smtp_send` is patched."""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest
from html import unescape
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import agent_mail, alerts_buyers, auth, db, emails, lead_watch as lw, leads, mailer, replies, reply_link, whatsapp  # noqa: E402
import web_harness  # noqa: E402

SMTP = {'LLAVE_SMTP_HOST': 'smtp.ejemplo.test', 'LLAVE_SMTP_PORT': '587', 'LLAVE_SMTP_USER': 'avisos@ejemplo.test',
        'LLAVE_SMTP_PASSWORD': 'sup3r-secret-pw', 'LLAVE_SMTP_FROM': 'Ficha Única <avisos@ejemplo.test>'}
OFF = {k: '' for k in SMTP}
NOW = datetime.datetime(2026, 10, 28, 16, 0, 0)       # 10:00 a.m. CDMX
NIGHT = datetime.datetime(2026, 10, 29, 2, 30, 0)     # 8:30 p.m. CDMX


def mail_env(**kw):
    d = dict(SMTP)
    d.update(kw)
    return mock.patch.dict(os.environ, d)


def body(msg, kind='plain'):
    return msg.get_body((kind,)).get_content()


class Base(unittest.TestCase):
    def setUp(self):
        self.mails = []
        self._p = [mock.patch.object(mailer, '_smtp_send', lambda msg, cfg: self.mails.append(msg)), mock.patch.object(mailer, 'ASYNC', False),
                   mock.patch('smtplib.SMTP', side_effect=AssertionError('real SMTP')), mock.patch('smtplib.SMTP_SSL', side_effect=AssertionError('real SMTP'))]
        [p.start() for p in self._p]
        self.addCleanup(lambda: [p.stop() for p in self._p])
        self.env = mail_env()
        self.env.start()
        self.addCleanup(self.env.stop)
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 'a.db'))
        db.init(self.con)
        lw.ensure_columns(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id, slug, name, whatsapp, email) VALUES (1,'casa-rosa','Casa Rosa','+525511112222','publico@casa-rosa.test')")
        c.execute("INSERT INTO users(id, agency_id, name, email, password_hash, role) VALUES (1,1,'Rosa Pérez','rosa@casa-rosa.test',?, 'owner')", (auth.hash_password('x' * 10),))
        c.execute("INSERT INTO agencies(id, slug, name, whatsapp) VALUES (2,'otra','Otra Inmobiliaria','+525533334444')")
        c.execute("INSERT INTO users(id, agency_id, name, email, password_hash, role) VALUES (2,2,'Beto Gil','beto@otra.test',?, 'owner')", (auth.hash_password('x' * 10),))
        c.execute("INSERT INTO listings(id, agency_id, ref, slug, status, title, colonia, municipio, estado, price_cents, currency, operation, property_type) "
                  "VALUES (1,1,'CASA-0001','depto-roma','activa','Depto con terraza en Roma Norte','Roma Norte','Cuauhtémoc','CDMX',450000000,'MXN','venta','departamento')")
        c.commit()

    def lead(self, name='Ana López', phone='55 1234 5678', email='ana@cliente.test', message='Quiero verlo el sábado', listing=1, agency=1, **kw):
        return leads.create_lead(self.con, agency, listing, name, phone, email, message, kw.get('source', 'sitio'), True)

    def to(self):
        return [m['To'] for m in self.mails]

    def tap(self, msg):
        """What the big button does for this email: the /w/ link in it -> the wa.me link the agent ends up on (None for a dead link).
        Exactly one signed link must be in the text part, and the same one in the HTML."""
        link, = re.findall(r'%s/w/[A-Za-z0-9._-]+' % re.escape(db.origin('app')), body(msg))
        self.assertIn('href="%s"' % link, body(msg, 'html'))
        got = reply_link.resolve(self.con, link.rsplit('/', 1)[1])
        if not got:
            return None
        return lw.whatsapp_reply(self.con, got['lead']['id'], got['agency'], got['agent_name'], owner_ok=True)

    def outbox(self, kind_prefix=''):
        return self.con.execute("SELECT * FROM outbox WHERE kind LIKE ? ORDER BY id", (kind_prefix + '%',)).fetchall()

    def assert_agents_only(self, *client_emails):
        for m in self.mails:
            self.assertNotIn(m['To'].lower(), [c.lower() for c in client_emails], 'an email went to a client')
            for h in ('Cc', 'Bcc', 'Reply-To'):
                self.assertIsNone(m[h], h)
            self.assertNotIn(m['To'].lower(), ('ana@cliente.test',))


class NewLead(Base):
    def test_one_email_to_the_agent_with_the_facts_and_the_whatsapp_button(self):
        r = self.lead()
        self.assertFalse(r['duplicate'])
        self.assertEqual(self.to(), ['rosa@casa-rosa.test'])                      # the owner's login, not the public agency email, not the client
        m = self.mails[0]
        self.assertEqual(m['Subject'], 'Nuevo cliente: Ana')
        self.assertEqual(emails.check(m['Subject']), '')
        t = body(m)
        for s in ('Ana López', '+52 55 1234 5678', 'ana@cliente.test', 'Depto con terraza en Roma Norte (folio CASA-0001)', '“Quiero verlo el sábado”',
                  'Responder por WhatsApp', db.origin('app') + '/clientes'):
            self.assertIn(s, t)
        wa = whatsapp.wa_link('+525512345678', replies.render(dict(self.con.execute('SELECT * FROM agencies WHERE id=1').fetchone()),
                                                              'Ana López', 'Depto con terraza en Roma Norte', 'Rosa Pérez'))
        self.assertNotIn('wa.me', t)                                                # the button is the signed one-tap page, never a bare wa.me link
        self.assertEqual(self.tap(m), wa)                                           # which ends on the existing first-reply link, signed by the agent
        self.assertIn('Soy%20Rosa%20de%20Casa%20Rosa', wa)
        html = body(m, 'html')
        self.assertNotIn('wa.me', html)
        self.assertIn('>Responder por WhatsApp<', html)
        self.assertIn('href="%s/clientes"' % db.origin('app'), html)
        self.assert_agents_only('ana@cliente.test')
        row, = self.outbox('email.')
        self.assertEqual((row['kind'], row['status']), ('email.lead_nuevo', 'sent'))

    def test_html_is_simple_inline_and_brand_colored_with_no_hotlinks(self):
        self.lead()
        html = body(self.mails[0], 'html')
        for bad in ('<style', '<script', '<img', '<link', 'url(', '@import', 'fonts.googleapis'):
            self.assertNotIn(bad, html)
        self.assertEqual(sorted(set(re.findall(r'href="(https?://[^"/]+)', html))), [db.origin('app')])   # the button and the footer link: app host only
        for token in ('#1B1236', '#0FB56D', '#FFF9EE', 'font-size:20px', 'font-size:30px'):   # tinta, nopal, papel, big button + big name
            self.assertIn(token, html)
        self.assertIn('Ficha Única', html)
        self.assertNotRegex(html, r'(?i)color:\s*#fff(fff)?\b[^>]*>Responder')               # text on nopal is tinta, never white
        self.assertLess(len(html), 6000)

    def test_what_the_client_typed_is_escaped(self):
        self.lead(name='<b>Eva</b>', message='<script>alert(1)</script> & más')
        html = body(self.mails[0], 'html')
        self.assertNotIn('<script>', html)
        self.assertNotIn('<b>Eva</b>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertEqual(self.mails[0]['Subject'], 'Nuevo cliente en tu sitio')              # not a usable first name: no name in the subject

    def test_whatsapp_dry_run_rows_are_untouched(self):
        self.lead()
        kinds = [r['kind'] for r in self.con.execute("SELECT kind FROM outbox WHERE kind LIKE 'ghl.%' ORDER BY id")]
        self.assertEqual(kinds, ['ghl.contact_upsert', 'ghl.note', 'ghl.opportunity', 'ghl.agent_alert', 'ghl.lead_first_reply'])
        self.assertTrue(all(r['status'] == 'dry_run' for r in self.con.execute("SELECT status FROM outbox WHERE kind LIKE 'ghl.%'")))

    def test_without_smtp_it_is_a_dry_run_row_and_nothing_leaves(self):
        with mail_env(**OFF):
            self.lead()
        self.assertEqual(self.mails, [])
        row, = self.outbox('email.')
        self.assertEqual((row['kind'], row['status']), ('email.lead_nuevo', 'dry_run'))
        self.assertEqual(json.loads(row['payload'])['to'], 'rosa@casa-rosa.test')

    def test_a_dead_mail_server_never_breaks_the_lead(self):
        def down(msg, cfg):
            raise OSError('connection refused')

        with mock.patch.object(mailer, '_smtp_send', down):
            r = self.lead()
        self.assertFalse(r['duplicate'])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)
        self.assertEqual(self.outbox('email.')[0]['status'], 'error')

    def test_duplicate_blocked_and_discarded_leads_send_nothing(self):
        self.lead()
        self.assertTrue(self.lead()['duplicate'])                                  # the existing 10-minute guard
        self.assertEqual(len(self.mails), 1)
        r = self.lead(name='Persona Bloqueada', phone='55 9999 0000', email='p@x.test')  # blocklisted person
        self.assertTrue(r['blocked'])
        self.assertEqual(len(self.mails), 1)

    def test_lead_without_a_phone_has_no_whatsapp_button_but_the_email_contact(self):
        self.lead(phone='', email='solo-correo@cliente.test')
        t, html = body(self.mails[0]), body(self.mails[0], 'html')
        self.assertNotIn('wa.me', t + html)
        self.assertNotIn('Responder por WhatsApp', t + html)
        self.assertIn('solo-correo@cliente.test', t)
        self.assert_agents_only('solo-correo@cliente.test')

    def test_general_lead_without_a_listing(self):
        self.lead(listing=None, message='Busco casa en Coyoacán')
        t = body(self.mails[0])
        self.assertNotIn('Pregunta por', t)
        self.assertIn('Busco casa en Coyoacán', t)

    def test_bolsa_lead_reaches_both_agencies_with_the_split(self):
        self.con.execute("INSERT INTO shares(listing_id, sharing_agency_id, split_pct) VALUES (1, 2, 40)")
        self.con.commit()
        r = self.lead(agency=2)                                                     # a client of Otra Inmobiliaria, listing owned by Casa Rosa
        self.assertFalse(r['duplicate'])
        self.assertEqual(sorted(self.to()), ['beto@otra.test', 'rosa@casa-rosa.test'])
        by = {m['To']: body(m) for m in self.mails}
        self.assertIn('Reparto 40/60', by['beto@otra.test'])
        self.assertIn('Llegó por la Bolsa', by['rosa@casa-rosa.test'])
        self.assertIn('Reparto 60/40', by['rosa@casa-rosa.test'])
        msgs = {m['To']: m for m in self.mails}
        self.assertIn('Soy%20Beto%20de%20Otra%20Inmobiliaria', self.tap(msgs['beto@otra.test']))     # each agency's own first reply
        self.assertIn('Soy%20Rosa%20de%20Casa%20Rosa', self.tap(msgs['rosa@casa-rosa.test']))
        self.assert_agents_only('ana@cliente.test')

    def test_recipients_are_the_account_holders(self):
        self.con.execute("INSERT INTO users(id, agency_id, name, email, password_hash, role) VALUES (3,1,'Luis Ríos','luis@casa-rosa.test',?, 'owner')", (auth.hash_password('x' * 10),))
        self.con.execute("INSERT INTO users(id, agency_id, name, email, password_hash, role) VALUES (4,1,'Asesor Equipo','asesor@casa-rosa.test',?, 'agent')", (auth.hash_password('x' * 10),))
        self.con.commit()
        self.lead()
        self.assertEqual(sorted(self.to()), ['luis@casa-rosa.test', 'rosa@casa-rosa.test'])      # team members (role agent) are not emailed
        msgs = {m['To']: m for m in self.mails}
        self.assertIn('Soy%20Luis%20de%20Casa%20Rosa', self.tap(msgs['luis@casa-rosa.test']))
        self.assertIn('Soy%20Rosa%20de%20Casa%20Rosa', self.tap(msgs['rosa@casa-rosa.test']))

    def test_agency_email_is_the_fallback_and_no_address_means_no_email(self):
        self.con.execute('DELETE FROM users WHERE agency_id=1')
        self.con.commit()
        self.lead()
        self.assertEqual(self.to(), ['publico@casa-rosa.test'])
        self.con.execute("UPDATE agencies SET email=NULL WHERE id=1")
        self.con.commit()
        self.lead(phone='55 7777 0000', email='otro@cliente.test')
        self.assertEqual(len(self.mails), 1)                                        # nobody to tell: no email, no error

    def test_async_from_a_web_request_still_delivers(self):
        with mock.patch.object(mailer, 'ASYNC', True):
            self.lead()
            mailer.wait()
        self.assertEqual(self.to(), ['rosa@casa-rosa.test'])


class Reminder(Base):
    def make(self, minutes=7, **kw):
        created = (NOW - datetime.timedelta(minutes=minutes)).strftime(lw.FMT)
        cur = self.con.execute("INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, created_at, status, first_response_at) "
                               "VALUES (1,1,1,'Marta Pérez','+525511119999','marta@cliente.test','¿Sigue disponible?',?,?,?)",
                               (created, kw.get('status', 'nuevo'), kw.get('resp')))
        self.con.commit()
        return cur.lastrowid

    def test_one_email_when_the_reminder_row_is_queued_and_never_again(self):
        self.make()
        self.assertEqual(lw.remind(self.con, now=NOW), 1)
        self.assertEqual(self.to(), ['rosa@casa-rosa.test'])
        m = self.mails[0]
        self.assertEqual(m['Subject'], 'Sin respuesta: Marta, 7 min')
        self.assertEqual(emails.check(m['Subject']), '')
        t = body(m)
        for s in ('Marta Pérez', 'hace 7 min', 'Depto con terraza en Roma Norte', 'Responder por WhatsApp'):
            self.assertIn(s, t)
        self.assertNotIn('wa.me', t)
        self.assertIn('wa.me/525511119999', self.tap(m))
        self.assertEqual(lw.remind(self.con, now=NOW), 0)
        self.assertEqual(lw.remind(self.con, now=NOW + datetime.timedelta(hours=2)), 0)
        self.assertEqual(len(self.mails), 1)
        self.assertEqual(len(self.con.execute("SELECT * FROM outbox WHERE kind='ghl.agent_alert'").fetchall()), 1)   # the WhatsApp row, as before
        self.assert_agents_only('marta@cliente.test')

    def test_answered_or_too_fresh_leads_get_no_email(self):
        self.make(minutes=3)
        self.make(minutes=9, resp=(NOW - datetime.timedelta(minutes=5)).strftime(lw.FMT))
        self.assertEqual(lw.remind(self.con, now=NOW), 0)
        self.assertEqual(self.mails, [])

    def test_an_existing_reminder_row_blocks_the_email_too(self):
        lid = self.make()
        self.con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.agent_alert', ?, '{}', 'dry_run')", ('lead_reminder:%d' % lid,))
        self.con.commit()
        lw.remind(self.con, now=NOW)
        self.assertEqual(self.mails, [])


class Digest(Base):
    def due(self, name, day='2026-10-28', agency=1, listing=1):
        self.con.execute("INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, status, follow_up_on) VALUES (?,?,?,?,?,'contactado',?)",
                         (agency, agency, listing, name, '+525511112222', day))
        self.con.commit()

    def test_one_email_per_agency_per_day_with_the_existing_hours(self):
        self.due('Marta'); self.due('Luis', day='2026-10-27'); self.due('Ana Beta', agency=2, listing=None)
        self.assertEqual(lw.follow_up_digest(self.con, now=NOW), 2)
        self.assertEqual(sorted(self.to()), ['beto@otra.test', 'rosa@casa-rosa.test'])
        m = [x for x in self.mails if x['To'] == 'rosa@casa-rosa.test'][0]
        self.assertEqual(m['Subject'], 'Seguimiento hoy: 2 clientes')
        t = body(m)
        for s in ('Marta', 'Luis', 'Depto con terraza en Roma Norte', '/clientes?estado=hoy', 'Hoy toca dar seguimiento a 2 clientes'):
            self.assertIn(s, t)
        self.assertNotIn('Ana Beta', t)                                             # another agency's client
        self.assertIn('Ver Seguimiento hoy', body(m, 'html'))
        self.assertEqual(lw.follow_up_digest(self.con, now=NOW + datetime.timedelta(hours=3)), 0)
        self.assertEqual(len(self.mails), 2)                                        # same day: no second email
        self.assertEqual(lw.follow_up_digest(self.con, now=NOW + datetime.timedelta(days=1)), 2)
        self.assertEqual(len(self.mails), 4)

    def test_quiet_hours_and_nothing_due_send_nothing(self):
        self.due('Marta')
        self.assertEqual(lw.follow_up_digest(self.con, now=datetime.datetime(2026, 10, 28, 13, 0, 0)), 0)   # 7 a.m.
        self.assertEqual(lw.follow_up_digest(self.con, now=NIGHT), 0)
        self.con.execute("UPDATE leads SET follow_up_on='2026-10-29'")
        self.con.commit()
        self.assertEqual(lw.follow_up_digest(self.con, now=NOW), 0)
        self.assertEqual(self.mails, [])

    def test_a_long_list_is_capped_in_the_email(self):
        for i in range(11):
            self.due('Cliente%02d' % i)
        lw.follow_up_digest(self.con, now=NOW)
        t = body(self.mails[0])
        self.assertIn('11 clientes', t)
        self.assertIn('y 3 más', t)
        self.assertNotIn('Cliente10', t)


class BuyerMatch(Base):
    def test_the_agent_gets_the_match_and_the_forward_link_once(self):
        alerts_buyers.subscribe(self.con, 1, 'Iván Soto', '5598765432', operation='venta', colonia='Roma', consent=True)
        self.assertEqual(alerts_buyers.run(self.con), 1)
        self.assertEqual(self.to(), ['rosa@casa-rosa.test'])
        m = self.mails[0]
        self.assertEqual(m['Subject'], 'Coincidencia para Iván')
        t = body(m)
        for s in ('Depto con terraza en Roma Norte (folio CASA-0001)', '$4,500,000 MXN', 'Reenviar por WhatsApp', 'wa.me/525598765432', 'Tú decides'):
            self.assertIn(s, t)
        self.assertEqual(alerts_buyers.run(self.con), 0)
        self.assertEqual(len(self.mails), 1)
        self.assert_agents_only('ivan@x.test')
        self.assertEqual(self.mails[0]['To'], 'rosa@casa-rosa.test')                # never the buyer's number or address


class EveryEmail(Base):
    def test_subjects_follow_the_playbook_and_bodies_are_never_empty(self):
        self.lead(); self.lead(name='', phone='55 2222 3333', email='')
        lw.remind(self.con, now=datetime.datetime.utcnow() + datetime.timedelta(minutes=9))
        self.con.execute("UPDATE leads SET follow_up_on=date('now','-6 hours'), status='contactado' WHERE id=1")
        self.con.commit()
        lw.follow_up_digest(self.con, now=datetime.datetime.utcnow().replace(hour=16, minute=0, second=0))
        alerts_buyers.subscribe(self.con, 1, '', '5598765432', consent=True)
        alerts_buyers.run(self.con)
        self.assertGreaterEqual(len(self.mails), 4)
        for m in self.mails:
            self.assertEqual(emails.check(m['Subject']), '', m['Subject'])
            self.assertLessEqual(len(m['Subject']), 40)
            self.assertTrue(body(m).strip())
            self.assertTrue(unescape(re.sub(r'<[^>]+>', '', body(m, 'html'))).strip())
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM outbox WHERE kind LIKE 'email.%' AND status<>'sent'").fetchone()[0], 0)


class ThroughTheWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('agentmail')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.mails = []
        self._p = [mock.patch.object(mailer, '_smtp_send', lambda msg, cfg: self.mails.append(msg)), mock.patch.object(mailer, 'ASYNC', False),
                   mock.patch('smtplib.SMTP', side_effect=AssertionError('real SMTP'))]
        [p.start() for p in self._p]
        self.addCleanup(lambda: [p.stop() for p in self._p])
        self.u = self.web.signup()
        self.slug = self.web.one('SELECT slug FROM agencies WHERE id=?', self.u['aid'])[0]
        con = db.connect()
        self.zone = 'Zona%dX' % self.u['aid']   # unique, so the directory routes this request to this agency and no other
        self.lid = con.execute("INSERT INTO listings(agency_id, ref, slug, status, title, colonia, municipio, estado, operation, property_type) "
                               "VALUES (?, 'W-1','depto-condesa','activa','Depto en la Condesa',?,'Cuauhtémoc','CDMX','venta','departamento')",
                               (self.u['aid'], self.zone)).lastrowid
        con.commit()
        con.close()

    def test_site_form_emails_the_agent_not_the_visitor(self):
        with mail_env():
            s, _, h = self.web.req('/contacto', {'listing': self.lid, 'name': 'Carla Ruiz', 'phone': '55 4444 5555', 'email': 'carla@visita.test',
                                                 'message': '¿Sigue disponible?', 'consent': '1'}, host='%s.fichaunica.localhost' % self.slug)
        self.assertEqual(s, 303)
        self.assertEqual([m['To'] for m in self.mails], [self.u['email']])
        t = body(self.mails[0])
        self.assertIn('Carla Ruiz', t)
        self.assertIn('Depto en la Condesa', t)
        self.assertNotIn('wa.me', t)
        link = re.search(r'(/w/\S+)', t).group(1)
        s2, _, h2 = self.web.req(link, {})                                              # the second tap, as a POST
        self.assertEqual(s2, 303)
        self.assertIn('https://wa.me/525544445555?text=', h2['Location'])

    def test_directory_request_emails_the_routed_agency(self):
        with mail_env():
            s, page, _ = self.web.req('/busco', {'name': 'Diego Mena', 'phone': '55 6666 7777', 'message': 'Busco depa en %s' % self.zone, 'consent': '1'},
                                      host='fichaunica.localhost')
        self.assertEqual(s, 200, page[:200])
        self.assertEqual([m['To'] for m in self.mails], [self.u['email']])
        self.assertIn('Busco depa en %s' % self.zone, body(self.mails[0]))

    def test_clientes_empty_state_mentions_email_only_when_mail_works(self):
        with mail_env(**OFF):
            s, page, _ = self.web.req('/clientes', cookie=self.u['cookie'])
            self.assertIn('No hay clientes en esta vista.', page)
            self.assertNotIn('te llega un correo', page)
        with mail_env():
            s, page, _ = self.web.req('/clientes', cookie=self.u['cookie'])
            self.assertIn('No hay clientes en esta vista.', page)
            self.assertIn('te llega un correo a %s' % self.u['email'], page)
            s, page, _ = self.web.req('/clientes?estado=cita', cookie=self.u['cookie'])
            self.assertNotIn('te llega un correo', page)


if __name__ == '__main__':
    unittest.main()
