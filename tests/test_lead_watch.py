import datetime, json, os, tempfile, unittest
from llave import db, lead_watch as lw

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0)


def ago(**kw):
    return (NOW - datetime.timedelta(**kw)).strftime(lw.FMT)


class T(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        lw.ensure_columns(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'a','Agencia A','+525500000001')")
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (2,'b','Agencia B','+525500000002')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,status,title) VALUES (1,1,'A-1','s1','activa','Depto Polanco')")
        c.commit()

    def lead(self, created, agency=1, owner=1, **kw):
        cur = self.con.execute(
            "INSERT INTO leads(agency_id,owner_agency_id,listing_id,name,phone,created_at,status,first_response_at,reminded_at)"
            " VALUES (?,?,1,'Marta Pérez','+525511112222',?,?,?,?)",
            (agency, owner, created, kw.get('status', 'nuevo'), kw.get('resp'), kw.get('rem')))
        self.con.commit()
        return cur.lastrowid

    def test_overdue_window(self):
        a4 = self.lead(ago(minutes=4)); a6 = self.lead(ago(minutes=6)); a8d = self.lead(ago(days=8))
        resp = self.lead(ago(minutes=10), resp=ago(minutes=5)); rem = self.lead(ago(minutes=10), rem=ago(minutes=1))
        ids = {x['id'] for x in lw.overdue(self.con, now=NOW)}
        self.assertEqual(ids, {a6})
        row = lw.overdue(self.con, now=NOW)[0]
        self.assertEqual(row['agency_whatsapp'], '+525500000001'); self.assertEqual(row['listing_ref'], 'A-1')

    def test_remind_idempotent_and_text(self):
        lid = self.lead(ago(minutes=7))
        self.assertEqual(lw.remind(self.con, now=NOW), 1)
        self.assertEqual(lw.remind(self.con, now=NOW), 0)
        rows = self.con.execute("SELECT * FROM outbox").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['kind'], rows[0]['status'], rows[0]['ref']), ('ghl.agent_alert', 'dry_run', 'lead_reminder:%d' % lid))
        p = json.loads(rows[0]['payload'])
        t = p['body']['text']
        for s in ('Marta', 'A-1', 'wa.me/525511112222', '7 min', 'Depto Polanco'):
            self.assertIn(s, t)
        self.assertEqual(p['to_whatsapp'], '+525500000001'); self.assertEqual(p['audience'], 'agency')
        self.assertIsNotNone(self.con.execute('SELECT reminded_at FROM leads WHERE id=?', (lid,)).fetchone()[0])

    def test_bolsa_alerts_receiver_only(self):
        self.lead(ago(minutes=9), agency=2, owner=1)
        self.assertEqual(lw.remind(self.con, now=NOW), 1)
        p = json.loads(self.con.execute('SELECT payload FROM outbox').fetchone()[0])
        self.assertEqual(p['to_whatsapp'], '+525500000002')

    def test_ownership(self):
        lid = self.lead(ago(minutes=9))
        self.assertFalse(lw.mark_responded(self.con, lid, 2))
        self.assertFalse(lw.set_status(self.con, lid, 2, 'cita'))
        self.assertEqual(self.con.execute('SELECT status FROM leads WHERE id=?', (lid,)).fetchone()[0], 'nuevo')
        self.assertTrue(lw.mark_responded(self.con, lid, 1, now=NOW))
        r = self.con.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((r['status'], r['first_response_at']), ('contactado', NOW.strftime(lw.FMT)))
        self.assertEqual(lw.remind(self.con, now=NOW), 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM audit WHERE action='lead_responded'").fetchone()[0], 1)

    def test_set_status(self):
        lid = self.lead(ago(minutes=9))
        self.assertFalse(lw.set_status(self.con, lid, 1, 'bogus'))
        self.assertTrue(lw.set_status(self.con, lid, 1, 'cita', now=NOW))
        r = self.con.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((r['status'], r['first_response_at']), ('cita', NOW.strftime(lw.FMT)))
        self.assertTrue(lw.mark_responded(self.con, lid, 1, now=NOW + datetime.timedelta(hours=1)))
        r = self.con.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((r['status'], r['first_response_at']), ('cita', NOW.strftime(lw.FMT)))


if __name__ == '__main__':
    unittest.main()
