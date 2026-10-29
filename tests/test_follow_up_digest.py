import datetime, json, os, tempfile, unittest
from llave import db, lead_watch as lw

# UTC; CDMX = UTC-6
MORNING = datetime.datetime(2026, 10, 28, 16, 0, 0)   # 10:00 a.m. CDMX
EARLY = datetime.datetime(2026, 10, 28, 13, 0, 0)     # 7:00 a.m. CDMX
NIGHT = datetime.datetime(2026, 10, 29, 2, 30, 0)     # 8:30 p.m. CDMX on 10-28


class T(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        lw.ensure_columns(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'a','Agencia A','+525500000001')")
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (2,'b','Agencia B','+525500000002')")
        c.commit()

    def lead(self, name, day, agency=1, status='contactado'):
        self.con.execute("INSERT INTO leads(agency_id,owner_agency_id,name,phone,status,follow_up_on) VALUES (?,?,?,?,?,?)",
                         (agency, agency, name, '+525511112222', status, day))
        self.con.commit()

    def outbox(self):
        return self.con.execute('SELECT * FROM outbox ORDER BY id').fetchall()

    def test_one_digest_per_agency_per_day(self):
        self.lead('Marta', '2026-10-28'); self.lead('Luis', '2026-10-27'); self.lead('Ana', '2026-10-28', agency=2)
        self.assertEqual(lw.follow_up_digest(self.con, now=MORNING), 2)
        self.assertEqual(lw.follow_up_digest(self.con, now=MORNING + datetime.timedelta(hours=3)), 0)
        rows = self.outbox()
        self.assertEqual([r['ref'] for r in rows], ['follow_up_digest:1:2026-10-28', 'follow_up_digest:2:2026-10-28'])
        self.assertTrue(all((r['kind'], r['status']) == ('ghl.agent_alert', 'dry_run') for r in rows))
        p = json.loads(rows[0]['payload'])
        self.assertEqual((p['to_whatsapp'], p['audience']), ('+525500000001', 'agency'))
        t = p['body']['text']
        for s in ('2 clientes', 'Luis', 'Marta', '/clientes?estado=hoy'):
            self.assertIn(s, t)
        self.assertNotIn('Ana', t)

    def test_skips_future_closed_and_cleared(self):
        self.lead('Futuro', '2026-10-29'); self.lead('Cerrado', '2026-10-28', status='cerrado'); self.lead('Sin', None)
        self.assertEqual(lw.follow_up_digest(self.con, now=MORNING), 0)
        self.assertEqual(self.outbox(), [])

    def test_quiet_hours(self):
        self.lead('Marta', '2026-10-28')
        self.assertEqual(lw.follow_up_digest(self.con, now=EARLY), 0)
        self.assertEqual(lw.follow_up_digest(self.con, now=NIGHT), 0)
        self.assertEqual(self.outbox(), [])

    def test_caps_names_at_three(self):
        for n in ('Ana', 'Beto', 'Carla', 'Dani', 'Eva'):
            self.lead(n, '2026-10-28')
        lw.follow_up_digest(self.con, now=MORNING)
        t = json.loads(self.outbox()[0]['payload'])['body']['text']
        self.assertIn('5 clientes: Ana, Beto, Carla y 2 más', t)
        self.assertNotIn('Eva', t)

    def test_next_day_sends_again(self):
        self.lead('Marta', '2026-10-28')
        lw.follow_up_digest(self.con, now=MORNING)
        self.assertEqual(lw.follow_up_digest(self.con, now=MORNING + datetime.timedelta(days=1)), 1)
        self.assertEqual(self.outbox()[1]['ref'], 'follow_up_digest:1:2026-10-29')


if __name__ == '__main__':
    unittest.main()
