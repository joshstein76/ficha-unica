"""tools/funnel.py: the numbers the team reads. Read-only, counts only, no personal data, clean on an empty database."""
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, lead_watch  # noqa: E402
from tools import funnel  # noqa: E402

NOW = datetime.datetime(2026, 11, 3, 18, 30)
# Things that must never come out of the tool, however the database is filled.
SECRETS = ['Marta Pérez', 'marta@cliente.test', '5511119999', 'Casa Rosa', 'Roma Norte 123', 'Hola, quiero verlo', 'tagline-secreto', 'sobre-secreto']


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        code = funnel.main(list(args), out=lambda s: out.write(s + '\n'), now=NOW)
    run.err = err.getvalue()
    return code, out.getvalue()


def make_db(path):
    con = db.connect(path)
    db.init(con)
    lead_watch.ensure_columns(con)      # what the running app adds on its first request (leads.first_response_at)
    return con


def agency(con, slug, created='2026-10-01 10:00:00', plan='gratis', tagline=None, about=None, sub=None, demo=0, until=None):
    return con.execute('INSERT INTO agencies(slug, name, whatsapp, email, plan, tagline, about, stripe_subscription_id, is_demo, plan_until, created_at) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?)', (slug, 'Casa Rosa ' + slug, '+525511119999', 'marta@cliente.test', plan, tagline, about, sub, demo, until, created)).lastrowid


def listing(con, aid, n, status='activa', created='2026-10-01 10:30:00'):
    return con.execute("INSERT INTO listings(agency_id, ref, slug, title, status, street, internal_note, created_at) VALUES (?,?,?,?,?,?,?,?)",
                       (aid, 'R-%d-%d' % (aid, n), 'casa-%d-%d' % (aid, n), 'Casa Rosa en Roma Norte', status, 'Roma Norte 123', 'nota-privada', created)).lastrowid


def lead(con, aid, status='nuevo', created='2026-10-01 12:00:00', answered=None):
    return con.execute("INSERT INTO leads(agency_id, owner_agency_id, name, phone, email, message, status, first_response_at, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (aid, aid, 'Marta Pérez', '+525511119999', 'marta@cliente.test', 'Hola, quiero verlo', status, answered, created)).lastrowid


class Empty(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'vacia.db')
        make_db(self.path).close()

    def test_zeros_cleanly_in_text(self):
        code, out = run('--db', self.path)
        self.assertEqual(code, 0)
        self.assertNotIn('None', out)
        self.assertNotIn('Traceback', out)
        self.assertNotIn('nan', out.lower())
        for label in ('Agencias (sin demo)', 'Con sitio personalizado', 'Con 1+ propiedad pública', 'Con 1+ cliente', 'Con un cliente respondido',
                      'En plan de pago', 'Con suscripción en Stripe'):
            self.assertRegex(out, r'%s\s+0\b' % re.escape(label))
        self.assertEqual(out.count('sin datos todavía'), 2)
        self.assertNotIn('%', out)                                  # no percentages of zero
        self.assertNotIn('demostración', out)

    def test_zeros_cleanly_in_json(self):
        code, out = run('--db', self.path, '--json')
        f = json.loads(out)
        self.assertEqual(code, 0)
        for k in ('agencies', 'site_personalized', 'with_public_listing', 'with_lead', 'with_lead_answered', 'on_paid_plan', 'on_stripe_subscription',
                  'demo_agencies_left_out'):
            self.assertEqual(f[k], 0, k)
        self.assertEqual(f['signup_to_first_listing_min'], {'median': None, 'n': 0})
        self.assertEqual(f['signup_to_first_lead_min'], {'median': None, 'n': 0})
        self.assertEqual(f['generated_at'], '2026-11-03T18:30:00Z')

    def test_a_file_with_no_tables_is_zeros_too(self):
        blank = os.path.join(tempfile.mkdtemp(), 'blank.db')
        sqlite3.connect(blank).close()
        code, out = run('--db', blank, '--json')
        self.assertEqual((code, json.loads(out)['agencies']), (0, 0))


class Counting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(tempfile.mkdtemp(), 'embudo.db')
        con = make_db(cls.path)
        agency(con, 'demo', demo=1, plan='ia', tagline='x', about='y', sub='sub_demo')
        agency(con, 'demo2', demo=1)
        con.execute("INSERT INTO listings(agency_id, ref, slug, title, status) SELECT id, 'D-1', 'd-1', 'Demo', 'activa' FROM agencies WHERE slug='demo'")
        lead(con, con.execute("SELECT id FROM agencies WHERE slug='demo'").fetchone()[0], status='contactado', answered='2026-10-01 12:01:00')
        a = agency(con, 'a')                                                             # signed up, nothing else
        b = agency(con, 'b', tagline='tagline-secreto', about='sobre-secreto')           # personalised the site
        c = agency(con, 'c', tagline='t', about='s')                                     # public listing + a lead nobody answered
        listing(con, c, 1, created='2026-10-01 10:30:00')
        lead(con, c, created='2026-10-01 12:00:00')
        d = agency(con, 'd', plan='pro', until='2026-11-30', created='2026-10-02 08:00:00')   # pilot: Pro for free, answered a lead
        listing(con, d, 1, created='2026-10-02 09:30:00')
        lead(con, d, status='contactado', created='2026-10-02 10:00:00', answered='2026-10-02 10:04:00')
        e = agency(con, 'e', plan='ia', sub='sub_real', created='2026-10-03 08:00:00')   # pays through Stripe
        listing(con, e, 1, status='apartada', created='2026-10-03 08:10:00')
        listing(con, e, 2, created='2026-10-04 08:00:00')
        lead(con, e, status='cita', created='2026-10-03 11:00:00', answered='2026-10-03 11:02:00')
        f = agency(con, 'f', plan='agencia')                                             # retired plan name = ia
        listing(con, f, 1, status='borrador', created='2026-10-01 10:05:00')             # a draft: first listing yes, public no
        g = agency(con, 'g')
        lead(con, g, status='descartado', created='2026-10-01 11:00:00')                 # blocked / discarded untouched: not a lead
        h = agency(con, 'h')
        lead(con, h, status='descartado', created='2026-10-01 11:30:00', answered='2026-10-01 11:40:00')   # discarded by the agent: a lead, not answered
        con.commit()
        con.close()
        cls.f = funnel.collect(funnel.open_ro(cls.path))

    def test_each_step(self):
        f = self.f
        self.assertEqual(f['agencies'], 8)                                  # a..h; the two demo agencies are left out
        self.assertEqual(f['demo_agencies_left_out'], 2)
        self.assertEqual(f['site_personalized'], 2)                         # b, c
        self.assertEqual(f['with_public_listing'], 3)                       # c, d, e (f has only a draft)
        self.assertEqual(f['with_lead'], 4)                                 # c, d, e, h (g's blocked lead does not count)
        self.assertEqual(f['with_lead_answered'], 2)                        # d, e (h discarded its lead)
        self.assertEqual(f['on_paid_plan'], 3)                              # d (pilot Pro), e (ia), f (agencia -> ia)
        self.assertEqual(f['on_stripe_subscription'], 1)                    # e only: the pilot is not a payer, and the demo is left out

    def test_medians(self):
        # signup -> first listing: c 30 min, d 90 min, e 10 min, f 5 min -> median (10 + 30) / 2 = 20
        self.assertEqual(self.f['signup_to_first_listing_min'], {'median': 20.0, 'n': 4})
        # signup -> first lead: c 120, d 120, e 180, h 90 (g's blocked one is not a lead) -> median (120 + 120) / 2 = 120
        self.assertEqual(self.f['signup_to_first_lead_min'], {'median': 120.0, 'n': 4})

    def test_text_and_json_agree_and_never_carry_personal_data(self):
        code, text = run('--db', self.path)
        code2, js = run('--db', self.path, '--json')
        self.assertEqual((code, code2), (0, 0))
        parsed = json.loads(js)
        for k, v in self.f.items():
            self.assertEqual(parsed[k], v, k)
        self.assertRegex(text, r'Con sitio personalizado\s+2\s+25%')
        self.assertRegex(text, r'Con 1\+ propiedad pública\s+3\s+38%')
        self.assertIn('Del registro a la primera propiedad: 20 min (4 agencias)', text)
        self.assertIn('Del registro al primer cliente:      2.0 h (4 agencias)', text)
        self.assertIn('(2 agencias de demostración no se cuentan)', text)
        for secret in SECRETS:
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, js)
        self.assertNotRegex(text + js, r'@|\+52|\d{9,}')                    # no email, no phone number, no long number of any kind
        # every value in the JSON is a number, a null or the timestamp: nothing else can carry text out
        def leaves(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k != 'generated_at':
                        yield from leaves(v)
            else:
                yield x
        self.assertTrue(all(v is None or isinstance(v, (int, float)) for v in leaves(parsed)))

    def test_does_not_touch_the_database(self):
        def digest():
            with open(self.path, 'rb') as fh:
                return hashlib.sha256(fh.read()).hexdigest(), os.stat(self.path).st_mtime_ns
        before = digest()
        run('--db', self.path)
        run('--db', self.path, '--json')
        self.assertEqual(digest(), before)
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.path))), ['embudo.db'])     # no journal, no -wal, nothing left behind

    def test_the_connection_is_read_only(self):
        con = funnel.open_ro(self.path)
        for sql in ("INSERT INTO agencies(slug, name) VALUES ('x', 'x')", "UPDATE agencies SET plan='ia'", 'DELETE FROM leads',
                    'CREATE TABLE nope (a)', 'PRAGMA journal_mode=WAL'):
            try:
                con.execute(sql)
                con.commit()
            except sqlite3.Error:
                pass
            else:
                if sql.startswith('PRAGMA'):
                    continue                                                # reports the current mode, changes nothing on a read-only file
                self.fail('the read-only connection accepted: ' + sql)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM agencies').fetchone()[0], 10)
        con.close()

    def test_a_read_only_file_works(self):
        copy = os.path.join(tempfile.mkdtemp(), 'copia.db')
        with open(self.path, 'rb') as src, open(copy, 'wb') as dst:
            dst.write(src.read())
        os.chmod(copy, 0o444)
        code, out = run('--db', copy, '--json')
        self.assertEqual((code, json.loads(out)['agencies']), (0, 8))


class Errors(unittest.TestCase):
    def test_a_missing_database_is_an_error_and_is_never_created(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, 'no-existe.db')
        code, out = run('--db', path)
        self.assertEqual((code, out), (2, ''))
        self.assertIn('solo lectura', run.err)
        self.assertEqual(os.listdir(d), [])

    def test_a_path_with_spaces_and_odd_characters(self):
        d = os.path.join(tempfile.mkdtemp(), 'mi base #1 ?')
        os.makedirs(d)
        path = os.path.join(d, 'llave.db')
        make_db(path).close()
        self.assertEqual(run('--db', path, '--json')[0], 0)

    def test_an_old_database_without_the_newer_columns(self):
        """Created from schema.sql alone: no leads.first_response_at, no agencies.stripe_subscription_id."""
        path = os.path.join(tempfile.mkdtemp(), 'vieja.db')
        con = sqlite3.connect(path)
        with open(os.path.join(ROOT, 'llave', 'schema.sql'), encoding='utf-8') as fh:
            con.executescript(fh.read())
        con.execute("INSERT INTO agencies(id, slug, name, plan) VALUES (1,'v','V','pro')")
        con.execute("INSERT INTO leads(agency_id, name, status) VALUES (1,'Marta Pérez','contactado')")
        con.execute("INSERT INTO leads(agency_id, name, status) VALUES (1,'Marta Pérez','descartado')")
        con.commit()
        con.close()
        code, out = run('--db', path, '--json')
        f = json.loads(out)
        self.assertEqual((code, f['agencies'], f['with_lead'], f['with_lead_answered'], f['on_paid_plan'], f['on_stripe_subscription']), (0, 1, 1, 1, 1, 0))

    def test_defaults_to_the_apps_own_database(self):
        path = os.path.join(tempfile.mkdtemp(), 'app.db')
        make_db(path).close()
        old, db.DB_PATH = db.DB_PATH, path
        try:
            self.assertEqual(json.loads(run('--json')[1])['agencies'], 0)
        finally:
            db.DB_PATH = old


class AsAScript(unittest.TestCase):
    def test_runs_on_its_own_and_reads_llave_db(self):
        path = os.path.join(tempfile.mkdtemp(), 'script.db')
        con = make_db(path)
        agency(con, 'solo')
        con.commit()
        con.close()
        env = dict(os.environ, LLAVE_DB=path)
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'funnel.py'), '--json'], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['agencies'], 1)
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'funnel.py')], capture_output=True, text=True,
                           env=dict(os.environ, LLAVE_DB=os.path.join(os.path.dirname(path), 'nada.db')), timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn('solo lectura', r.stderr)


if __name__ == '__main__':
    unittest.main()
