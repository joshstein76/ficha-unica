"""Guard: every table/column the SQLite app creates (schema.sql + runtime migrations) exists in supabase/migrations.
Adding a column in db.init or a CREATE TABLE in a module without a Postgres migration fails here."""
import glob, os, re, unittest
from llave import db, lead_watch, alerts_buyers, photo_fetch, ml_oauth, eco
from llave.ai import budget
from llave.web import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENAMED = {'users': 'profiles'}                    # Supabase Auth: users -> profiles (uuid)
DROPPED_TABLES = {'sessions'}                      # Supabase Auth replaces it
DROPPED_COLS = {('users', 'password_hash'),        # lives in auth.users
                ('ml_accounts', 'access_token'),    # Postgres: access_token_secret_id -> vault.secrets
                ('ml_accounts', 'refresh_token'),   # Postgres: refresh_token_secret_id -> vault.secrets
                ('ml_accounts', 'expires_at'),      # Postgres: token_expires_at
                ('ml_accounts', 'connected_at')}    # Postgres: created_at
NOT_COLS = ('primary', 'unique', 'constraint', 'foreign', 'check')


def pg_schema():
    sql = ''
    for f in sorted(glob.glob(os.path.join(ROOT, 'supabase', 'migrations', '*.sql'))):
        with open(f, encoding='utf-8') as fh:
            sql += fh.read() + '\n'
    sql = re.sub(r'--[^\n]*', '', sql)
    tables = {}
    for m in re.finditer(r'create table (?:if not exists )?public\.(\w+)\s*\((.*?)\n\);', sql, re.S | re.I):
        cols = tables.setdefault(m.group(1), set())
        for line in m.group(2).split('\n'):
            w = line.strip().split()
            if w and w[0].lower() not in NOT_COLS:
                cols.add(w[0].strip(','))
    for m in re.finditer(r'alter table public\.(\w+)\s+add column (?:if not exists )?(\w+)', sql, re.I):
        tables.setdefault(m.group(1), set()).add(m.group(2))
    return tables


def sqlite_schema():
    con = db.connect(':memory:')
    db.init(con)
    lead_watch.ensure_columns(con)
    alerts_buyers.ensure_table(con)
    photo_fetch.ensure_table(con)
    ml_oauth.ensure_tables(con)
    budget.ensure_table(con)
    eco.ensure_tables(con)
    server._rate_table(con)
    server.team_invite(con, 'x')
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        out[t] = {r[1] for r in con.execute('PRAGMA table_info(%s)' % t)}
    return out


def runtime_table_names():
    """CREATE TABLE statements anywhere in llave/ (some only run inside a request handler)."""
    names = set()
    for f in glob.glob(os.path.join(ROOT, 'llave', '**', '*.py'), recursive=True) + [os.path.join(ROOT, 'llave', 'schema.sql')]:
        with open(f, encoding='utf-8') as fh:
            names.update(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\(', fh.read()))
    return names


class PgParity(unittest.TestCase):
    def test_every_runtime_table_has_a_pg_table(self):
        pg = pg_schema()
        missing = sorted(t for t in runtime_table_names() - DROPPED_TABLES if RENAMED.get(t, t) not in pg)
        self.assertEqual(missing, [], 'add these tables to a new supabase/migrations file')

    def test_every_sqlite_column_has_a_pg_column(self):
        pg = pg_schema()
        missing = []
        for t, cols in sqlite_schema().items():
            if t in DROPPED_TABLES:
                continue
            have = pg.get(RENAMED.get(t, t), set())
            missing += ['%s.%s' % (t, c) for c in sorted(cols) if (t, c) not in DROPPED_COLS and c not in have]
        self.assertEqual(missing, [], 'add these columns to a new supabase/migrations file')

    def test_new_pg_tables_have_rls(self):
        with open(os.path.join(ROOT, 'supabase', 'migrations', '0005_runtime_parity.sql'), encoding='utf-8') as fh:
            sql = fh.read()
        created = set(re.findall(r'create table if not exists public\.(\w+)', sql))
        rls = set(re.findall(r'alter table public\.(\w+)\s+enable row level security', sql))
        self.assertTrue(created)
        self.assertEqual(sorted(created - rls), [])

    def test_parser_sees_known_columns(self):  # the guard itself must not pass by reading nothing
        pg = pg_schema()
        self.assertIn('follow_up_on', pg['leads'])
        self.assertIn('attempts', pg['outbox'])
        self.assertIn('novedades_seen', pg['profiles'])
        self.assertIn('team_invites', runtime_table_names())  # only created inside a request handler
        self.assertNotIn('in', runtime_table_names())


if __name__ == '__main__':
    unittest.main()
