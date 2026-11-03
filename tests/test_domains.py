"""Own domain (Pro): input cleanup, the DNS check with an injected resolver (no network), verify / lose / recover, routing on a real
local server (www serves, bare 301s, free address 301s, Gratis 302s), /_tls/ask, the Mi sitio card and the cron tool."""
import datetime
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db, domains, kit_home  # noqa: E402
from llave.web import panel  # noqa: E402
from llave.web.server import Handler, tls_allowed  # noqa: E402

TMP = tempfile.mkdtemp()
PORT = 8761
OURS = '203.0.113.10'
OTHER = '198.51.100.7'
T0 = datetime.datetime(2026, 11, 3, 12, 0, 0)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(host, path, data=None, cookie=None, method=None):
    headers = {'Host': host}
    if cookie:
        headers['Cookie'] = cookie
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), data=body, headers=headers, method=method)
    try:
        resp = OPENER.open(r, timeout=10)
        return resp.status, resp.read().decode('utf-8', 'replace'), resp.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode('utf-8', 'replace'), ex.headers


def dns(table):
    """A fake resolver: {host: [ips]}; a missing host has no record; the value None means 'the lookup failed'."""
    return lambda host: table.get(host, [])


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'dom.db'), os.path.join(TMP, 'media'), PORT
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def setUp(self):
        env = mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': OURS, 'LLAVE_CNAME_TARGET': '', 'LLAVE_OWN_DOMAINS': '', 'LLAVE_DOMAIN_WARM': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.con = db.connect()
        self.addCleanup(self.con.close)
        self.n = getattr(Base, '_n', 0) + 1
        Base._n = self.n

    def agency(self, plan='pro', domain=None, verified=False, **extra):
        Base._slugs = getattr(Base, '_slugs', 0) + 1
        slug = 'ag%d' % Base._slugs
        cur = self.con.execute("INSERT INTO agencies(slug,name,whatsapp,plan,custom_domain,domain_verified_at,domain_claimed_at) "
                               "VALUES (?,?,?,?,?,?,?)", (slug, 'Agencia %d' % Base._slugs, '+525577778888', plan, domain,
                                                          '2026-11-03 10:00:00' if verified else None, '2026-11-03 09:00:00' if domain else None))
        for k, v in extra.items():
            self.con.execute('UPDATE agencies SET %s=? WHERE id=?' % k, (v, cur.lastrowid))
        self.con.commit()
        return self.row(cur.lastrowid)

    def row(self, aid):
        return self.con.execute('SELECT * FROM agencies WHERE id=?', (aid,)).fetchone()


class Normalize(unittest.TestCase):
    def test_strips_scheme_path_www_port_case_and_credentials(self):
        for raw in ('micasa.mx', ' MiCasa.MX ', 'https://www.micasa.mx/', 'http://micasa.mx/propiedades?x=1#top', 'www.micasa.mx',
                    'www.www.micasa.mx', 'micasa.mx:8080', 'https://user:pw@www.micasa.mx:443/a/b', 'micasa.mx.', 'HTTPS://WWW.MICASA.MX'):
            self.assertEqual(domains.normalize(raw), 'micasa.mx', raw)
        self.assertEqual(domains.normalize('www.mi-casa.com.mx'), 'mi-casa.com.mx')
        self.assertEqual(domains.normalize('méxico.mx'), 'xn--mxico-bsa.mx')       # what DNS and certificates use
        self.assertEqual(domains.normalize(''), '')
        self.assertEqual(domains.normalize(None), '')
        self.assertEqual(domains.normalize('   '), '')

    def test_rejects_anything_invalid(self):
        for raw in ('micasa', 'mi casa.mx', 'http://', 'www.', 'www', '203.0.113.10', 'micasa.m', '-casa.mx', 'casa-.mx', 'a..mx',
                    'mi_casa.mx', 'micasa.123', 'x' * 64 + '.mx', ('a.' * 130) + 'mx', 'micasa.local', 'casa.localhost', 'casa.test',
                    'ñ' * 70 + '.mx', 'micasa.mx\nbcc:x', 'javascript:alert(1)'):
            with self.assertRaises(ValueError, msg=raw):
                domains.normalize(raw)
        with self.assertRaises(ValueError):
            domains.normalize('com.mx')                                              # a public suffix, not a domain

    def test_rejects_our_own_domains(self):
        for raw in ('fichaunica.mx', 'www.fichaunica.mx', 'sitio.fichaunica.mx', 'app.fichaunica.mx', 'fichaunica.com', db.BASE_DOMAIN,
                    'x.' + db.BASE_DOMAIN, 'https://FichaUnica.MX/registro'):
            with self.assertRaises(ValueError, msg=raw) as cm:
                domains.normalize(raw)
            self.assertIn('Ficha Única', str(cm.exception), raw)
        self.assertEqual(domains.normalize('fichaunica.mx.evil.com'), 'fichaunica.mx.evil.com')   # a different domain
        self.assertEqual(domains.normalize('mifichaunica.mx'), 'mifichaunica.mx')
        with mock.patch.dict(os.environ, {'LLAVE_OWN_DOMAINS': 'ciaobellamarketing.com, otra.mx'}):
            for raw in ('ciaobellamarketing.com', 'www.otra.mx', 'blog.otra.mx'):
                with self.assertRaises(ValueError, msg=raw):
                    domains.normalize(raw)
        with mock.patch.object(db, 'MARKETING_URL', 'https://www.marca.example.org'):
            with self.assertRaises(ValueError):
                domains.normalize('marca.example.org')


class Claim(Base):
    def test_save_replace_and_remove(self):
        a = self.agency()
        self.assertEqual(domains.claim(self.con, a, 'https://WWW.Casa-%d.mx/x' % self.n), 'casa-%d.mx' % self.n)
        r = self.row(a['id'])
        self.assertEqual(r['custom_domain'], 'casa-%d.mx' % self.n)
        self.assertIsNone(r['domain_verified_at'])
        self.assertTrue(r['domain_claimed_at'])
        self.assertIsNone(domains.claim(self.con, r, ''))
        self.assertIsNone(self.row(a['id'])['custom_domain'])
        actions = [x[0] for x in self.con.execute("SELECT action FROM audit WHERE detail LIKE ?", ('%' + 'casa-%d.mx' % self.n + '%',))]
        self.assertIn('domain_claimed', actions)
        self.assertIn('domain_removed', actions)

    def test_saving_the_same_domain_keeps_it_verified_changing_it_does_not(self):
        a = self.agency(domain='quedate%d.mx' % self.n, verified=True)
        domains.claim(self.con, a, 'www.quedate%d.mx' % self.n)
        self.assertTrue(self.row(a['id'])['domain_verified_at'])
        domains.claim(self.con, self.row(a['id']), 'otro%d.mx' % self.n)
        r = self.row(a['id'])
        self.assertEqual(r['custom_domain'], 'otro%d.mx' % self.n)
        self.assertIsNone(r['domain_verified_at'])

    def test_one_agency_per_domain(self):
        holder = self.agency(domain='unico%d.mx' % self.n, verified=True)
        other = self.agency()
        for raw in ('unico%d.mx' % self.n, 'www.UNICO%d.mx' % self.n, 'https://unico%d.mx/' % self.n):
            with self.assertRaises(ValueError) as cm:
                domains.claim(self.con, other, raw)
            self.assertIn('otra cuenta', str(cm.exception))
        self.assertEqual(self.row(holder['id'])['custom_domain'], 'unico%d.mx' % self.n)
        self.assertIsNone(self.row(other['id'])['custom_domain'])

    def test_a_fresh_unverified_claim_is_protected_a_stale_one_can_be_taken(self):
        holder = self.agency(domain='espera%d.mx' % self.n)
        other = self.agency()
        now = datetime.datetime(2026, 11, 3, 12, 0, 0)                                # holder claimed it 3 hours ago
        with self.assertRaises(ValueError):
            domains.claim(self.con, other, 'espera%d.mx' % self.n, now=now)
        later = now + datetime.timedelta(days=domains.CLAIM_DAYS)
        self.assertEqual(domains.claim(self.con, other, 'espera%d.mx' % self.n, now=later), 'espera%d.mx' % self.n)
        self.assertIsNone(self.row(holder['id'])['custom_domain'])                    # nothing else of the holder is touched
        self.assertEqual(self.row(holder['id'])['name'], holder['name'])
        self.assertTrue(self.con.execute("SELECT 1 FROM audit WHERE action='domain_claim_lapsed'").fetchone())

    def test_a_lost_domain_keeps_its_protection_for_a_while(self):
        a = self.agency(domain='perdido%d.mx' % self.n, verified=True)
        for i in range(domains.FAIL_LIMIT):
            domains.check(self.con, a, dns({}), now=T0 + datetime.timedelta(minutes=10 * i), warm=False)
        self.assertIsNone(self.row(a['id'])['domain_verified_at'])
        with self.assertRaises(ValueError):                                          # claim clock restarted when it was lost
            domains.claim(self.con, self.agency(), 'perdido%d.mx' % self.n, now=T0 + datetime.timedelta(days=5))


class Check(Base):
    def test_pending_becomes_verified_only_when_www_resolves_only_to_us(self):
        d = 'verifica%d.mx' % self.n
        a = self.agency(domain=d)
        w = 'www.' + d
        for table, www in (({}, 'sin_registro'), ({w: [OTHER]}, 'otra'), ({w: [OURS, OTHER]}, 'mixto'), ({w: None}, 'desconocido')):
            res = domains.check(self.con, a, dns(table), now=T0, warm=False)
            self.assertEqual((res['state'], res['www'], res['event']), ('pendiente', www, None), table)
            self.assertIsNone(self.row(a['id'])['domain_verified_at'])
        res = domains.check(self.con, a, dns({w: [OURS]}), now=T0, warm=False)
        self.assertEqual((res['state'], res['event'], res['www']), ('verificado', 'verified', 'ok'))
        r = self.row(a['id'])
        self.assertEqual(r['domain_verified_at'], '2026-11-03 12:00:00')
        self.assertEqual(json.loads(r['domain_check'])['apex'], 'sin_registro')
        self.assertTrue(self.con.execute("SELECT 1 FROM audit WHERE action='domain_verified' AND detail LIKE ?", ('%' + d + '%',)).fetchone())

    def test_the_bare_name_is_optional_and_recorded(self):
        d = 'opcional%d.mx' % self.n
        a = self.agency(domain=d)
        res = domains.check(self.con, a, dns({'www.' + d: [OURS], d: [OTHER]}), now=T0, warm=False)
        self.assertEqual((res['state'], res['apex']), ('verificado', 'otra'))
        self.assertEqual(json.loads(self.row(a['id'])['domain_check'])['apex_ips'], [OTHER])
        res = domains.check(self.con, a, dns({'www.' + d: [OURS], d: [OURS]}), now=T0, warm=False)
        self.assertEqual(res['apex'], 'ok')

    def test_without_a_configured_ip_the_cname_target_tells_us_where_we_are(self):
        d = 'sinip%d.mx' % self.n
        a = self.agency(domain=d)
        with mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': ''}):
            self.assertEqual(domains.cname_target(), 'sites.' + db.BASE_DOMAIN)
            res = domains.check(self.con, a, dns({'www.' + d: [OURS], 'sites.' + db.BASE_DOMAIN: [OURS]}), now=T0, warm=False)
            self.assertEqual(res['state'], 'verificado')
            b = self.agency(domain='sinip2%d.mx' % self.n)                                # nothing known about our own address: never verifies
            res = domains.check(self.con, b, dns({'www.sinip2%d.mx' % self.n: [OURS]}), now=T0, warm=False)
            self.assertEqual((res['state'], res['www']), ('pendiente', 'desconocido'))

    def test_cname_target_comes_from_env(self):
        with mock.patch.dict(os.environ, {'LLAVE_CNAME_TARGET': 'Sitios.Ejemplo.MX.'}):
            self.assertEqual(domains.cname_target(), 'sitios.ejemplo.mx')
        with mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': 'no-es-ip, 2001:db8::1, 192.0.2.4 192.0.2.5, 192.0.2.4'}):
            self.assertEqual(domains.public_ips(), ['192.0.2.4', '192.0.2.5'])

    def test_three_failed_cron_checks_in_a_row_take_a_verified_domain_off_and_dns_coming_back_restores_it(self):
        d = 'cae%d.mx' % self.n
        a = self.agency(domain=d, verified=True)
        free = db.origin(a['slug'])
        self.assertEqual(db.site_url(a), 'https://www.' + d)
        bad = dns({'www.' + d: [OTHER]})
        for i in range(domains.FAIL_LIMIT - 1):
            res = domains.check(self.con, a, bad, now=T0 + datetime.timedelta(minutes=10 * i), warm=False)
            self.assertEqual((res['state'], res['fail_count']), ('verificado', i + 1))
        res = domains.check(self.con, a, dns({}), now=T0 + datetime.timedelta(minutes=30), warm=False)
        self.assertEqual((res['state'], res['event']), ('problema', 'lost'))
        r = self.row(a['id'])
        self.assertIsNone(r['domain_verified_at'])
        self.assertEqual(r['domain_lost_at'], '2026-11-03 12:30:00')
        self.assertEqual(r['custom_domain'], d)                                       # nothing lost: the name is still saved
        self.assertEqual(db.site_url(r), free)                                        # back on the free address
        self.assertFalse(db.own_domain_live(r))
        self.assertTrue(domains.lost_notice(r))
        self.assertEqual(domains.state_of(r), 'problema')
        res = domains.check(self.con, r, dns({'www.' + d: [OURS]}), now=T0 + datetime.timedelta(hours=2), warm=False)   # DNS fixed
        self.assertEqual((res['state'], res['event']), ('verificado', 'verified'))
        r = self.row(a['id'])
        self.assertIsNone(r['domain_lost_at'])
        self.assertEqual(db.site_url(r), 'https://www.' + d)
        self.assertFalse(domains.lost_notice(r))

    def test_failures_must_be_consecutive(self):
        d = 'flap%d.mx' % self.n
        a = self.agency(domain=d, verified=True)
        bad, good = dns({}), dns({'www.' + d: [OURS]})
        for resolver in (bad, bad, good, bad, bad):
            domains.check(self.con, a, resolver, warm=False)
        self.assertTrue(self.row(a['id'])['domain_verified_at'])
        self.assertEqual(self.row(a['id'])['domain_fail_count'], 2)
        domains.check(self.con, a, bad, warm=False)
        self.assertIsNone(self.row(a['id'])['domain_verified_at'])

    def test_a_resolver_that_cannot_answer_never_counts_against_the_agent(self):
        d = 'duda%d.mx' % self.n
        a = self.agency(domain=d, verified=True)
        broken = dns({'www.' + d: None})
        for _ in range(domains.FAIL_LIMIT + 2):
            res = domains.check(self.con, a, broken, warm=False)
            self.assertEqual((res['state'], res['www']), ('verificado', 'desconocido'))
        self.assertEqual(self.row(a['id'])['domain_fail_count'], 0)

        def raising(host):
            raise OSError('resolver down')
        for _ in range(domains.FAIL_LIMIT + 1):
            self.assertEqual(domains.check(self.con, a, raising, warm=False)['state'], 'verificado')

    def test_the_button_can_verify_but_never_takes_a_domain_off(self):
        d = 'boton%d.mx' % self.n
        a = self.agency(domain=d, verified=True)
        for _ in range(domains.FAIL_LIMIT + 2):
            res = domains.check(self.con, a, dns({}), source='boton', warm=False)
            self.assertEqual(res['state'], 'verificado')
        self.assertTrue(self.row(a['id'])['domain_verified_at'])
        self.assertEqual(self.row(a['id'])['domain_fail_count'], 0)

    def test_system_resolver_distinguishes_no_record_from_lookup_failure(self):
        import socket
        with mock.patch('llave.domains.socket.getaddrinfo', side_effect=socket.gaierror(socket.EAI_NONAME, 'nope')):
            self.assertEqual(domains.system_resolver('x.mx'), [])
        with mock.patch('llave.domains.socket.getaddrinfo', side_effect=socket.gaierror(socket.EAI_AGAIN, 'try again')):
            self.assertIsNone(domains.system_resolver('x.mx'))
        with mock.patch('llave.domains.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('203.0.113.10', 0)), (2, 1, 6, '', ('203.0.113.10', 0))]) as m:
            self.assertEqual(domains.system_resolver('x.mx'), ['203.0.113.10'])
            self.assertEqual(m.call_args[0][2], socket.AF_INET)


class Certificate(Base):
    def test_first_certificate_is_requested_right_after_verification_when_the_domain_is_already_approved(self):
        d = 'cert%d.mx' % self.n
        a = self.agency(domain=d)
        seen = []

        def warm(names):                                                              # what Caddy does when it receives the first handshake
            c = db.connect()
            try:
                seen.append((list(names), [tls_allowed(c, n) for n in names]))
            finally:
                c.close()
            return {n: True for n in names}
        res = domains.check(self.con, a, dns({'www.' + d: [OURS], d: [OURS]}), now=T0, warm=warm)
        self.assertEqual(res['state'], 'verificado')
        self.assertEqual(seen, [(['www.' + d, d], [True, True])])                     # both forms approved at the moment of the visit
        r = self.row(a['id'])
        self.assertEqual(r['domain_tls'], 'ok')
        self.assertTrue(db.own_domain_live(r))
        domains.check(self.con, r, dns({'www.' + d: [OURS], d: [OURS]}), now=T0, warm=warm)
        self.assertEqual(len(seen), 1)                                                # nothing left to warm: no second visit

    def test_a_failed_warm_up_keeps_the_free_address_and_is_retried(self):
        d = 'lento%d.mx' % self.n
        a = self.agency(domain=d)
        good = dns({'www.' + d: [OURS]})
        domains.check(self.con, a, good, now=T0, warm=lambda names: {n: False for n in names})
        r = self.row(a['id'])
        self.assertEqual((r['domain_tls'], bool(r['domain_verified_at'])), ('espera', True))
        self.assertFalse(db.own_domain_live(r))                                       # no redirect to a domain that has no certificate yet
        self.assertEqual(db.site_url(r), 'https://www.' + d)
        domains.check(self.con, r, good, now=T0 + datetime.timedelta(minutes=10), warm=lambda names: {n: True for n in names})
        r = self.row(a['id'])
        self.assertEqual(r['domain_tls'], 'ok')
        self.assertTrue(db.own_domain_live(r))

    def test_the_bare_name_never_blocks_the_redirect(self):
        d = 'apex%d.mx' % self.n
        a = self.agency(domain=d)
        both = dns({'www.' + d: [OURS], d: [OURS]})
        domains.check(self.con, a, both, now=T0, warm=lambda names: {n: n.startswith('www.') for n in names})
        self.assertEqual(self.row(a['id'])['domain_tls'], 'ok')                       # www is what matters
        calls = []
        domains.check(self.con, a, both, now=T0, warm=lambda names: calls.append(list(names)) or {n: True for n in names})
        self.assertEqual(calls, [[d]])                                                # only the bare name is retried

    def test_warm_up_is_off_outside_production_and_never_touches_the_network_in_tests(self):
        self.assertEqual(db.ENV, 'local')
        self.assertIsNone(domains.default_warm())
        with mock.patch.object(db, 'ENV', 'production'):
            self.assertIs(domains.default_warm(), domains.warm_tls)
            with mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': ''}):
                self.assertIsNone(domains.default_warm())
            with mock.patch.dict(os.environ, {'LLAVE_DOMAIN_WARM': '0'}):
                self.assertIsNone(domains.default_warm())
        with mock.patch('llave.domains.socket.create_connection', side_effect=OSError('no network in tests')) as m:
            self.assertEqual(domains.warm_tls(['www.x.mx', 'x.mx']), {'www.x.mx': False, 'x.mx': False})
            self.assertEqual(m.call_args[0][0], (OURS, 443))

    def test_the_free_address_keeps_serving_between_verification_and_the_certificate(self):
        d = 'puente%d.mx' % self.n
        a = self.agency(domain=d)
        with mock.patch.object(domains, 'default_warm', return_value=domains.warm_tls):       # production: a certificate will be requested
            res = domains.check(self.con, a, dns({'www.' + d: [OURS]}), source='boton', now=T0, warm=False)   # the button defers it to a thread
        r = self.row(a['id'])
        self.assertEqual((res['event'], r['domain_tls']), ('verified', 'espera'))
        self.assertFalse(db.own_domain_live(r))                                           # no redirect to a host that has no certificate yet
        domains.warm_agency(self.con, a['id'], warm=lambda names: {n: True for n in names})
        self.assertTrue(db.own_domain_live(self.row(a['id'])))
        b = self.agency(domain='local%d.mx' % self.n)                                       # no warm-up configured (local run): live at once
        domains.check(self.con, b, dns({'www.local%d.mx' % self.n: [OURS]}), now=T0, warm=False)
        self.assertTrue(db.own_domain_live(self.row(b['id'])))

    def test_warm_agency_for_the_button_thread(self):
        d = 'hilo%d.mx' % self.n
        a = self.agency(domain=d, verified=True, domain_check=json.dumps({'www': 'ok', 'apex': 'sin_registro', 'warmed': []}))
        domains.warm_agency(self.con, a['id'], warm=lambda names: {n: True for n in names})
        self.assertEqual(self.row(a['id'])['domain_tls'], 'ok')
        free = self.agency(plan='gratis', domain='gratishilo%d.mx' % self.n, verified=True)
        domains.warm_agency(self.con, free['id'], warm=lambda names: self.fail('Gratis has no own domain: nothing to warm'))


class RunAll(Base):
    def test_cron_run_checks_pro_domains_only_and_summarises(self):
        con = self.con
        con.execute("UPDATE agencies SET custom_domain=NULL, domain_verified_at=NULL")   # a clean slate for this test
        con.commit()
        pend = self.agency(domain='pend%d.mx' % self.n)
        ok = self.agency(domain='bien%d.mx' % self.n, verified=True)
        bad = self.agency(domain='mal%d.mx' % self.n, verified=True, domain_fail_count=domains.FAIL_LIMIT - 1)
        gratis = self.agency(plan='gratis', domain='gratis%d.mx' % self.n, verified=True)
        resolver = dns({'www.pend%d.mx' % self.n: [OURS], 'www.bien%d.mx' % self.n: [OURS]})
        summary = domains.run_all(con, resolver=resolver, now=T0, warm=False)
        self.assertEqual(summary, {'checked': 3, 'verificados': 1, 'perdidos': 1, 'ok': 1, 'pendientes': 0, 'sin_plan': 1, 'sin_tiempo': 0})
        self.assertTrue(self.row(pend['id'])['domain_verified_at'])
        self.assertTrue(self.row(ok['id'])['domain_verified_at'])
        self.assertIsNone(self.row(bad['id'])['domain_verified_at'])
        self.assertTrue(self.row(gratis['id'])['domain_verified_at'])                 # untouched while on Gratis; comes back on upgrade
        self.assertIsNone(self.row(gratis['id'])['domain_checked_at'])

    def test_least_recently_checked_goes_first_and_the_time_budget_stops_the_run(self):
        self.con.execute("UPDATE agencies SET custom_domain=NULL, domain_verified_at=NULL")
        self.con.commit()
        old = self.agency(domain='viejo%d.mx' % self.n, domain_checked_at='2026-11-01 00:00:00')
        new = self.agency(domain='nuevo%d.mx' % self.n, domain_checked_at='2026-11-03 00:00:00')
        never = self.agency(domain='nunca%d.mx' % self.n)
        order = []

        def resolver(host):
            order.append(host)
            return []
        ticks = iter([0, 0, 1000, 1000])
        summary = domains.run_all(self.con, resolver=resolver, warm=False, budget_s=10, clock=lambda: next(ticks))
        self.assertEqual((summary['checked'], summary['sin_tiempo']), (1, 2))
        self.assertTrue(order[0].endswith('nunca%d.mx' % self.n))                      # never checked = first in line
        self.assertTrue(self.row(never['id'])['domain_checked_at'])
        self.assertEqual(self.row(old['id'])['domain_checked_at'], '2026-11-01 00:00:00')   # ran out of time: these wait for the next run
        self.assertEqual(self.row(new['id'])['domain_checked_at'], '2026-11-03 00:00:00')

    def test_cron_tool(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import domain_check_run
        self.con.execute("UPDATE agencies SET custom_domain=NULL, domain_verified_at=NULL")
        self.con.commit()
        self.agency(domain='tool%d.mx' % self.n)
        lines = []
        summary = domain_check_run.main(con=self.con, resolver=dns({'www.tool%d.mx' % self.n: [OURS]}), warm=False, now=T0, out=lines.append)
        self.assertEqual(summary['verificados'], 1)
        self.assertTrue(lines[0].startswith('domain_check {'))
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'deploy', 'crontab.example'), encoding='utf-8') as fh:
            self.assertRegex(fh.read(), r'\*/10 \* \* \* \* .*tools/domain_check_run\.py')


class Routing(Base):
    def setUp(self):
        super().setUp()
        self.d = 'rosa%d.mx' % self.n
        self.a = self.agency(domain=self.d, verified=True)
        self.free = '%s.%s' % (self.a['slug'], db.BASE_DOMAIN)
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title,status,operation,property_type,updated_at) "
                         "VALUES (?,?,?,?, 'activa','venta','casa',datetime('now'))", (self.a['id'], 'R1', 'casa-uno', 'Casa Uno'))
        lid = self.con.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.con.execute("INSERT INTO photos(listing_id,position,sha256,sizes,width,height) VALUES (?,0,'s','{\"1600\":\"x.jpg\",\"800\":\"x.jpg\",\"400\":\"x.jpg\"}',800,600)", (lid,))
        self.con.commit()

    def test_www_serves_the_site_and_everything_public_says_www(self):
        www = 'https://www.' + self.d
        s, home, _ = req('www.' + self.d, '/')
        self.assertEqual(s, 200)
        self.assertIn('Casa Uno', home)
        self.assertIn('<link rel="canonical" href="%s/">' % www, home)
        self.assertNotIn(self.free, home)
        s, page, _ = req('www.' + self.d, '/propiedad/casa-uno')
        self.assertEqual(s, 200)
        self.assertIn('<link rel="canonical" href="%s/propiedad/casa-uno">' % www, page)
        self.assertIn('"url": "%s' % www, page.replace('":"', '": "'))                  # JSON-LD
        _, sitemap, _ = req('www.' + self.d, '/sitemap.xml')
        self.assertIn('<loc>%s/propiedad/casa-uno</loc>' % www, sitemap)
        self.assertNotIn(self.free, sitemap)
        _, robots, _ = req('www.' + self.d, '/robots.txt')
        self.assertIn('Sitemap: %s/sitemap.xml' % www, robots)
        _, llms, _ = req('www.' + self.d, '/llms.txt')
        self.assertIn('%s/propiedad/casa-uno' % www, llms)
        self.assertNotIn(self.free, llms)
        s, feed, _ = req('www.' + self.d, '/feeds/llave_open.json')
        if s == 200:
            self.assertIn(www, feed)
            self.assertNotIn(self.free, feed)
        c = db.canonical(self.con, self.con.execute('SELECT id FROM listings WHERE agency_id=?', (self.a['id'],)).fetchone()[0])
        self.assertEqual(c['url'], www + '/propiedad/casa-uno')
        self.assertTrue(c['photos'][0]['url'].startswith(www + '/media/'))
        self.assertEqual(c['agency']['site_url'], www)

    def test_bare_domain_redirects_to_www_keeping_path_and_query(self):
        for method in ('GET', 'HEAD'):
            s, _, h = req(self.d, '/propiedad/casa-uno?utm=1', method=method)
            self.assertEqual(s, 301, method)
            self.assertEqual(h['Location'], 'https://www.%s/propiedad/casa-uno?utm=1' % self.d)
            self.assertEqual(h['Cache-Control'], 'max-age=3600')                       # never cached for years: the domain can be taken off
        s, _, h = req(self.d, '/contacto', data={'name': 'x'})
        self.assertEqual((s, h['Location']), (308, 'https://www.%s/contacto' % self.d))   # a form keeps its method

    def test_free_address_redirects_to_the_own_domain_once_live(self):
        s, _, h = req(self.free, '/propiedad/casa-uno?utm=1')
        self.assertEqual(s, 301)
        self.assertEqual(h['Location'], 'https://www.%s/propiedad/casa-uno?utm=1' % self.d)
        self.assertEqual(h['Cache-Control'], 'max-age=3600')
        s, _, h = req(self.free, '/')
        self.assertEqual((s, h['Location']), (301, 'https://www.%s/' % self.d))
        s, _, h = req(self.free, '/contacto', data={'name': 'x'})
        self.assertEqual((s, h['Location']), (308, 'https://www.%s/contacto' % self.d))
        s, _, _ = req('app.' + db.BASE_DOMAIN, '/entrar')                                # the panel never redirects
        self.assertEqual(s, 200)

    def test_the_free_address_keeps_serving_when_the_own_domain_is_not_ready(self):
        def free_status():
            return req(self.free, '/')[0]
        self.assertEqual(free_status(), 301)
        self.con.execute("UPDATE agencies SET domain_tls='espera' WHERE id=?", (self.a['id'],))     # verified, certificate not confirmed
        self.con.commit()
        self.assertEqual(free_status(), 200)
        self.assertEqual(req('www.' + self.d, '/')[0], 200)
        self.con.execute("UPDATE agencies SET domain_tls='ok' WHERE id=?", (self.a['id'],))
        self.con.commit()
        self.assertEqual(free_status(), 301)
        self.con.execute('UPDATE agencies SET domain_verified_at=NULL, domain_lost_at=? WHERE id=?', ('2026-11-03 12:00:00', self.a['id']))   # lost
        self.con.commit()
        self.assertEqual(free_status(), 200)                                               # back on the free address, nothing deleted
        self.assertEqual(req('www.' + self.d, '/')[0], 404)
        self.assertEqual(req(self.d, '/')[0], 404)
        s, home, _ = req(self.free, '/')
        self.assertIn('Casa Uno', home)
        self.assertIn('<link rel="canonical" href="%s/">' % db.origin(self.a['slug']), home)

    def test_gratis_goes_to_the_free_address_with_302_and_the_free_address_does_not_redirect(self):
        self.con.execute("UPDATE agencies SET plan='gratis' WHERE id=?", (self.a['id'],))
        self.con.commit()
        for host in ('www.' + self.d, self.d):
            s, _, h = req(host, '/propiedad/casa-uno?x=1')
            self.assertEqual(s, 302, host)
            self.assertEqual(h['Location'], '%s/propiedad/casa-uno?x=1' % db.origin(self.a['slug']))
        self.assertEqual(req(self.free, '/')[0], 200)
        self.con.execute("UPDATE agencies SET plan='pro' WHERE id=?", (self.a['id'],))
        self.con.commit()
        self.assertEqual(req('www.' + self.d, '/')[0], 200)                                # upgrade brings it back

    def test_unverified_and_unknown_hosts_are_404(self):
        pend = self.agency(domain='pendiente%d.mx' % self.n)
        for host in ('www.pendiente%d.mx' % self.n, 'pendiente%d.mx' % self.n, 'nadie.example.com', 'www.nadie.example.com', 'www.www.' + self.d):
            self.assertEqual(req(host, '/')[0], 404, host)
        self.assertTrue(pend)

    def test_tls_ask_approves_both_forms_only_for_verified_domains(self):
        d = self.d
        pend = 'pend%d.mx' % self.n
        self.agency(domain=pend)
        for dom, code in (('www.' + d, 200), (d, 200), ('WWW.' + d.upper(), 200), ('www.' + d + '.', 200),
                          ('www.' + pend, 404), (pend, 404), ('www.www.' + d, 404), ('sub.' + d, 404), ('x' + d, 404), (d + '.evil.com', 404),
                          ('evil.com', 404), ('www.evil.com', 404), ('', 404), ('app.' + db.BASE_DOMAIN, 200), (self.free, 200),
                          ('nadie.' + db.BASE_DOMAIN, 404), ('a.b.' + db.BASE_DOMAIN, 404)):
            s, _, _ = req('127.0.0.1', '/_tls/ask?domain=' + urllib.parse.quote(dom))
            self.assertEqual(s, code, repr(dom))
        self.assertEqual(req('127.0.0.1', '/_tls/ask')[0], 404)                         # no domain parameter
        self.con.execute('UPDATE agencies SET domain_verified_at=NULL WHERE id=?', (self.a['id'],))      # lost: no new certificates
        self.con.commit()
        for dom in (d, 'www.' + d):
            self.assertEqual(req('127.0.0.1', '/_tls/ask?domain=' + dom)[0], 404, dom)

    def test_hsts_does_not_pin_the_subdomains_of_an_agents_domain(self):
        with mock.patch.object(db, 'ENV', 'production'):
            _, _, own = req('www.' + self.d, '/')
            _, _, free = req(self.free, '/')
            self.assertEqual(own['Strict-Transport-Security'], 'max-age=31536000')
            self.assertEqual(free['Strict-Transport-Security'], 'max-age=31536000; includeSubDomains')


def signup(name, email, plan='pro'):
    s, _, h = req('app.' + db.BASE_DOMAIN, '/registro', {'name': 'Rosa Pérez', 'agency': name, 'whatsapp': '55 7777 8888',
                                                          'email': email, 'password': 'segura1234', 'terms': '1'})
    assert s == 303, s
    cookie = h['Set-Cookie'].split(';')[0]
    con = db.connect()
    con.execute('UPDATE agencies SET plan=? WHERE id=(SELECT agency_id FROM users WHERE email=?)', (plan, email))
    con.commit()
    con.close()
    _, body, _ = req('app.' + db.BASE_DOMAIN, '/perfil', cookie=cookie)
    return cookie, re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)


class PanelCard(Base):
    def setUp(self):
        super().setUp()
        self.cookie, self.csrf = signup('Panel Dominio %d' % self.n, 'dominio%d@ejemplo.test' % self.n)
        self.slug = self.con.execute('SELECT slug FROM agencies WHERE id=(SELECT agency_id FROM users WHERE email=?)',
                                     ('dominio%d@ejemplo.test' % self.n,)).fetchone()[0]
        self.aid = self.con.execute('SELECT id FROM agencies WHERE slug=?', (self.slug,)).fetchone()[0]
        self.host = 'app.' + db.BASE_DOMAIN

    def post(self, path, **data):
        return req(self.host, path, dict(data, csrf=self.csrf), cookie=self.cookie)

    def sitio(self, path='/sitio'):
        return req(self.host, path, cookie=self.cookie)[1]

    def test_steps_use_the_configured_values_and_the_old_placeholder_is_gone(self):
        d = 'panel%d.mx' % self.n
        s, _, h = self.post('/sitio/dominio', domain='HTTPS://WWW.%s/inicio' % d.upper())
        self.assertEqual((s, h['Location']), (303, '/sitio?d=guardado'))
        with mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': '192.0.2.77', 'LLAVE_CNAME_TARGET': 'sitios.ejemplo.mx'}):
            page = self.sitio('/sitio?d=guardado')
        self.assertIn('Guardamos tu dominio', page)
        self.assertIn('value="%s"' % d, page)
        self.assertIn('<code>sitios.ejemplo.mx</code>', page)                             # CNAME target from env, never hard-coded
        self.assertEqual(page.count('<code>192.0.2.77</code>'), 2)                         # A record for www and for the bare name
        self.assertIn('<b>www.%s</b>: todavía no lo hemos revisado' % d, page)
        self.assertIn('Verificar ahora', page)
        self.assertIn('Falta un paso', page)
        self.assertNotIn('se activa en producción', page)
        self.assertNotIn('llave-verify', page)
        self.assertNotIn('sites.%s' % db.BASE_DOMAIN, page)
        with mock.patch.dict(os.environ, {'LLAVE_PUBLIC_IP': '', 'LLAVE_CNAME_TARGET': ''}):
            page = self.sitio()
        self.assertIn('<code>sites.%s</code>' % db.BASE_DOMAIN, page)                    # default derived from the brand domain
        self.assertNotIn('tipo <b>A</b>', page)                                          # no IP configured: only the CNAME is offered

    def test_bad_input_and_other_peoples_domains_are_refused_with_a_reason(self):
        s, page, _ = self.post('/sitio/dominio', domain='no es un dominio')
        self.assertEqual(s, 400)
        self.assertIn('no parece válido', page)
        s, page, _ = self.post('/sitio/dominio', domain='sitio.' + db.BASE_DOMAIN)
        self.assertEqual(s, 400)
        self.assertIn('es de Ficha Única', page)
        self.agency(domain='ocupado%d.mx' % self.n, verified=True)
        s, page, _ = self.post('/sitio/dominio', domain='www.ocupado%d.mx' % self.n)
        self.assertEqual(s, 400)
        self.assertIn('ya está conectado a otra cuenta', page)
        self.assertIsNone(self.con.execute('SELECT custom_domain FROM agencies WHERE id=?', (self.aid,)).fetchone()[0])

    def test_pending_then_verified_then_problem_each_with_its_own_message(self):
        d = 'estados%d.mx' % self.n
        self.post('/sitio/dominio', domain=d)
        w = 'www.' + d
        with mock.patch.object(domains, 'system_resolver', dns({w: [OTHER]})):
            s, page, _ = self.post('/sitio/dominio/verificar')
        self.assertEqual(s, 200)
        self.assertIn('Todavía no vemos el cambio', page)
        self.assertIn('apunta a otra dirección (%s)' % OTHER, page)
        self.assertIn('Falta un paso', page)
        with mock.patch.object(domains, 'system_resolver', dns({})):
            self.assertIn('todavía no existe en tu proveedor', self.post('/sitio/dominio/verificar')[1])
        with mock.patch.object(domains, 'system_resolver', dns({w: [OURS], d: [OURS]})):
            s, page, _ = self.post('/sitio/dominio/verificar')
        self.assertIn('quedó activo', page)
        self.assertIn('Tu dominio está activo', page)
        self.assertIn('https://%s' % w, page)
        self.assertEqual(page.count('class="pill ok">Listo'), 2)                          # www and the bare name
        self.assertEqual(self.con.execute('SELECT domain_verified_at IS NOT NULL FROM agencies WHERE id=?', (self.aid,)).fetchone()[0], 1)
        self.assertIn('href="https://%s"' % w, self.sitio())                              # "Ver sitio" now points to the own domain
        a = self.con.execute('SELECT * FROM agencies WHERE id=?', (self.aid,)).fetchone()
        for i in range(domains.FAIL_LIMIT):
            domains.check(self.con, a, dns({}), warm=False)
        page = self.sitio()
        self.assertIn('dejó de apuntar a Ficha Única', page)
        self.assertIn('volvió a su dirección gratis', page)
        self.assertIn('no perdiste', page)
        self.assertIn('value="%s"' % d, page)                                              # the name is still there
        home = req(self.host, '/', cookie=self.cookie)[1]
        self.assertIn('dejó de apuntar a Ficha Única', home)                               # also on Inicio, where agents actually look
        data = kit_home.build(self.con, {'agency': self.con.execute('SELECT * FROM agencies WHERE id=?', (self.aid,)).fetchone(),
                                         'user': {'name': 'Rosa'}}, [], [])
        self.assertTrue(any('dejó de apuntar' in x['title'] and x['cta']['href'] == '/sitio' for x in data['alerts']))
        with mock.patch.object(domains, 'system_resolver', dns({w: [OURS]})):
            self.assertIn('quedó activo', self.post('/sitio/dominio/verificar')[1])
        self.assertNotIn('dejó de apuntar', self.sitio())
        self.assertNotIn('dejó de apuntar', req(self.host, '/', cookie=self.cookie)[1])

    def test_a_verified_domain_that_fails_the_button_check_is_warned_not_congratulated(self):
        d = 'aviso%d.mx' % self.n
        self.post('/sitio/dominio', domain=d)
        with mock.patch.object(domains, 'system_resolver', dns({'www.' + d: [OURS]})):
            self.assertIn('quedó activo', self.post('/sitio/dominio/verificar')[1])
        with mock.patch.object(domains, 'system_resolver', dns({'www.' + d: [OTHER]})):
            s, page, _ = self.post('/sitio/dominio/verificar')
        self.assertEqual(s, 200)
        self.assertIn('Ahora mismo no vemos tu dominio apuntando a Ficha Única', page)
        self.assertNotIn('Todo bien', page)
        self.assertIn('Ahora mismo <b>www.%s</b> no apunta a Ficha Única' % d, page)
        self.assertEqual(self.con.execute('SELECT domain_verified_at IS NOT NULL FROM agencies WHERE id=?', (self.aid,)).fetchone()[0], 1)

    def test_certificate_pending_note(self):
        d = 'candado%d.mx' % self.n
        self.post('/sitio/dominio', domain=d)
        self.con.execute("UPDATE agencies SET domain_verified_at=datetime('now'), domain_tls='espera' WHERE id=?", (self.aid,))
        self.con.commit()
        page = self.sitio()
        self.assertIn('Estamos activando el candado (HTTPS)', page)

    def test_the_button_is_rate_limited(self):
        self.post('/sitio/dominio', domain='limite%d.mx' % self.n)
        with mock.patch.object(domains, 'system_resolver', dns({})):
            codes = [self.post('/sitio/dominio/verificar')[0] for _ in range(6)]
        self.assertEqual(codes, [200] * 4 + [429] * 2)
        s, page, _ = self.post('/sitio/dominio/verificar')
        self.assertEqual(s, 429)
        self.assertIn('Espera unos minutos', page)

    def test_verify_needs_a_saved_domain_and_the_pro_plan(self):
        s, page, _ = self.post('/sitio/dominio/verificar')
        self.assertEqual(s, 400)
        self.assertIn('Primero escribe tu dominio', page)
        self.post('/sitio/dominio', domain='gratis%d.mx' % self.n)
        self.con.execute("UPDATE agencies SET plan='gratis' WHERE id=?", (self.aid,))
        self.con.commit()
        self.assertEqual(self.post('/sitio/dominio/verificar')[0], 403)
        self.assertEqual(self.post('/sitio/dominio', domain='otro%d.mx' % self.n)[0], 403)
        page = self.sitio()
        self.assertIn('queda guardado y se activa solo cuando vuelvas a Pro', page)
        self.assertNotIn('Verificar ahora', page)

    def test_remove_the_domain(self):
        self.post('/sitio/dominio', domain='quitar%d.mx' % self.n)
        s, _, h = self.post('/sitio/dominio', domain='')
        self.assertEqual((s, h['Location']), (303, '/sitio?d=quitado'))
        self.assertIsNone(self.con.execute('SELECT custom_domain FROM agencies WHERE id=?', (self.aid,)).fetchone()[0])
        self.assertIn('Quitamos tu dominio', self.sitio('/sitio?d=quitado'))

    def test_plans_no_longer_say_muy_pronto_for_the_domain(self):
        text = json.dumps(panel.PLANS, ensure_ascii=False)
        self.assertIn('Tu propio dominio', text)
        self.assertNotIn('Tu propio dominio (muy pronto)', text)


class Migration(unittest.TestCase):
    def test_columns_exist_and_init_is_repeatable(self):
        con = db.connect(':memory:')
        db.init(con)
        db.init(con)
        cols = {r[1]: r for r in con.execute('PRAGMA table_info(agencies)')}
        for c in ('domain_claimed_at', 'domain_checked_at', 'domain_check', 'domain_fail_count', 'domain_lost_at', 'domain_tls'):
            self.assertIn(c, cols)
        self.assertEqual(cols['domain_fail_count'][4], '0')
        con.execute("INSERT INTO agencies(slug,name) VALUES ('a','A')")
        self.assertEqual(con.execute('SELECT domain_fail_count FROM agencies').fetchone()[0], 0)

    def test_an_older_database_gets_the_columns(self):
        con = db.connect(':memory:')
        db.init(con)
        con.execute('ALTER TABLE agencies RENAME TO agencies_x')                           # simulate a table created before these columns
        con.execute("CREATE TABLE agencies AS SELECT id,slug,name,tagline,whatsapp,email,city,logo_path,design,accent,about,custom_domain,"
                    "domain_verified_at,plan,plan_until,ghl_location_id,first_reply,first_reply_noname,is_demo,created_at,referred_by,"
                    "stripe_customer_id,stripe_subscription_id FROM agencies_x")
        con.execute('DROP TABLE agencies_x')
        db.init(con)
        cols = {r[1] for r in con.execute('PRAGMA table_info(agencies)')}
        self.assertTrue({'domain_claimed_at', 'domain_checked_at', 'domain_check', 'domain_fail_count', 'domain_lost_at', 'domain_tls'} <= cols)

    def test_supabase_migration_mirrors_the_columns(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'supabase', 'migrations', '0008_custom_domain_checks.sql'), encoding='utf-8') as fh:
            sql = fh.read()
        for c in ('domain_claimed_at', 'domain_checked_at', 'domain_check', 'domain_fail_count', 'domain_lost_at', 'domain_tls'):
            self.assertIn('add column if not exists %s' % c, sql)
        self.assertIn('protect_agency_domain_fields', sql)


if __name__ == '__main__':
    unittest.main()
