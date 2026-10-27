import datetime, os, tempfile, unittest
from llave import db, lead_watch as lw
from llave.web import panel

TODAY = datetime.date(2026, 10, 26)


class FollowUp(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        lw.ensure_columns(self.con)
        self.con.execute("INSERT INTO agencies(id,slug,name) VALUES (1,'a','Agencia A'),(2,'b','Agencia B')")
        self.con.commit()

    def lead(self, status='contactado', agency=1):
        cur = self.con.execute("INSERT INTO leads(agency_id,name,phone,status) VALUES (?,'Marta','+525511112222',?)", (agency, status))
        self.con.commit()
        return cur.lastrowid

    def fu(self, lid):
        return self.con.execute('SELECT follow_up_on FROM leads WHERE id=?', (lid,)).fetchone()[0]

    def test_set_and_clear(self):
        lid = self.lead()
        self.assertTrue(lw.set_follow_up(self.con, lid, 1, 3, TODAY))
        self.assertEqual(self.fu(lid), '2026-10-29')
        self.assertTrue(lw.set_follow_up(self.con, lid, 1, 0, TODAY))
        self.assertIsNone(self.fu(lid))

    def test_rejects_bad_days_and_other_agency(self):
        lid = self.lead()
        self.assertFalse(lw.set_follow_up(self.con, lid, 1, 5, TODAY))
        self.assertFalse(lw.set_follow_up(self.con, lid, 1, -1, TODAY))
        self.assertFalse(lw.set_follow_up(self.con, lid, 2, 1, TODAY))
        self.assertIsNone(self.fu(lid))

    def test_due_count_today_and_past_open_only(self):
        due = self.lead(); past = self.lead('cita'); later = self.lead(); closed = self.lead('cerrado'); other = self.lead(agency=2)
        lw.set_follow_up(self.con, due, 1, 1, TODAY - datetime.timedelta(days=1))
        lw.set_follow_up(self.con, past, 1, 1, TODAY - datetime.timedelta(days=5))
        lw.set_follow_up(self.con, later, 1, 7, TODAY)
        self.con.execute("UPDATE leads SET follow_up_on='2026-10-20' WHERE id IN (?,?)", (closed, other))
        self.assertEqual(lw.follow_up_count(self.con, 1, TODAY), 2)
        self.assertEqual(lw.follow_up_count(self.con, 1, TODAY + datetime.timedelta(days=7)), 3)

    def test_cdmx_day_is_utc_minus_6(self):
        self.assertEqual(lw.today_cdmx('2026-10-27 05:30:00'), datetime.date(2026, 10, 27))  # caller-provided local time
        self.assertEqual(panel._short_day('2026-10-29'), '29 oct')

    def test_list_shows_badge_and_buttons(self):
        lid = self.lead()
        lw.set_follow_up(self.con, lid, 1, 1, TODAY - datetime.timedelta(days=1))
        rows = self.con.execute('SELECT * FROM leads').fetchall()
        ctx = {'token': 't'}
        h = panel._leads_list(self.con, rows, ctx, today=TODAY)
        self.assertIn('seguimiento hoy', h)
        self.assertIn('/clientes/%d/seguimiento' % lid, h)
        self.assertIn('Quitar', h)
        h2 = panel._leads_list(self.con, rows, ctx, today=TODAY - datetime.timedelta(days=1))
        self.assertIn('seguimiento 26 oct', h2)
        self.con.execute("UPDATE leads SET status='cerrado'")
        h3 = panel._leads_list(self.con, self.con.execute('SELECT * FROM leads').fetchall(), ctx, today=TODAY)
        self.assertNotIn('Recordarme', h3)


if __name__ == '__main__':
    unittest.main()
