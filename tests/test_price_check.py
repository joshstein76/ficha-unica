import datetime, json, os, tempfile, unittest
from llave import db, price_check as pc

TODAY = datetime.date(2026, 10, 17)


def d(n):
    return (TODAY - datetime.timedelta(days=n)).isoformat()


class T(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'a','A','+525500000001')")
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (2,'b','B','+525500000002')")
        self.n = 0

    def add(self, ag, date, status='activa', price=1500000):
        self.n += 1
        self.con.execute("INSERT INTO listings(id,agency_id,ref,slug,status,title,price_cents,price_date) "
                         "VALUES (?,?,?,?,?,?,?,?)", (self.n, ag, 'R-%d' % self.n, 's%d' % self.n, status,
                                                      'Depto %d' % self.n, price * 100, date))
        self.con.commit()
        return self.n

    def test_stale(self):
        a = self.add(1, None)
        b = self.add(1, d(31))
        self.add(1, d(29))
        self.add(1, d(90), status='borrador')
        r = pc.stale_listings(self.con, today=TODAY)
        self.assertEqual({x['listing_id'] for x in r}, {a, b})
        self.assertEqual([x for x in r if x['listing_id'] == b][0]['days'], 31)
        self.assertEqual(pc.stale_listings(self.con, agency_id=2, today=TODAY), [])

    def test_confirm(self):
        a = self.add(1, d(60))
        self.assertFalse(pc.confirm(self.con, a, 2))
        self.assertEqual(self.con.execute('SELECT price_date FROM listings WHERE id=?', (a,)).fetchone()[0], d(60))
        self.assertTrue(pc.confirm(self.con, a, 1))
        self.assertEqual(self.con.execute('SELECT price_date FROM listings WHERE id=?', (a,)).fetchone()[0],
                         datetime.date.today().isoformat())
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM audit WHERE action='price_confirmed'").fetchone()[0], 1)

    def rows(self):
        return self.con.execute("SELECT * FROM outbox WHERE ref LIKE 'price_check:%' ORDER BY id").fetchall()

    def test_weekly(self):
        self.add(1, None)
        self.add(1, d(40))
        self.add(2, d(40))
        self.assertEqual(pc.weekly_run(self.con, TODAY), {'agencies': 2, 'listings': 3})
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        p = json.loads(rows[0]['payload'])
        self.assertEqual((rows[0]['kind'], rows[0]['status']), ('ghl.agent_alert', 'dry_run'))
        self.assertEqual((p['audience'], p['channel'], p['to_whatsapp']), ('agency', 'whatsapp', '+525500000001'))
        self.assertIn('R-1', p['body']['text'])
        self.assertIn('/precios', p['body']['text'])
        self.assertIn('-W42', rows[0]['ref'])
        # idempotent same week
        self.assertEqual(pc.weekly_run(self.con, TODAY - datetime.timedelta(days=2)), {'agencies': 0, 'listings': 0})
        self.assertEqual(len(self.rows()), 2)
        # new week
        self.assertEqual(pc.weekly_run(self.con, TODAY + datetime.timedelta(days=7))['agencies'], 2)
        self.assertEqual(len(self.rows()), 4)

    def test_max_five(self):
        for _ in range(8):
            self.add(1, d(45))
        pc.weekly_run(self.con, TODAY)
        t = json.loads(self.rows()[0]['payload'])['body']['text']
        self.assertEqual(t.count('R-'), 5)
        self.assertIn('y 3 más', t)


if __name__ == '__main__':
    unittest.main()
