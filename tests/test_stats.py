import datetime, os, tempfile, unittest
from llave import db, lead_watch as lw, stats

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0)  # ISO week 2026-W42


def ago(**kw):
    return (NOW - datetime.timedelta(**kw)).strftime(lw.FMT)


class T(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        lw.ensure_columns(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name) VALUES (1,'a','A')")
        c.execute("INSERT INTO agencies(id,slug,name) VALUES (2,'b','B')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,title,colonia) VALUES (1,1,'A-1','s1','Uno','Polanco')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,title,colonia) VALUES (2,1,'A-2','s2','Dos','Condesa')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,title) VALUES (3,2,'B-1','s3','Otro')")
        c.commit()

    def lead(self, created, resp=None, listing=1, source='sitio', status='contactado', agency=1):
        self.con.execute("INSERT INTO leads(agency_id,listing_id,name,phone,source,status,created_at,first_response_at)"
                         " VALUES (?,?,'x','+525511112222',?,?,?,?)", (agency, listing, source, status, created, resp))
        self.con.commit()

    def test_views_and_bot(self):
        stats.record_view(self.con, 1, '2026-10-17'); stats.record_view(self.con, 1, '2026-10-17')
        stats.record_view(self.con, 1, '2026-10-16')
        self.assertEqual(self.con.execute('SELECT views FROM listing_views WHERE day=?', ('2026-10-17',)).fetchone()[0], 2)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM listing_views').fetchone()[0], 2)
        for ua in ('Googlebot/2.1', 'curl/8', 'python-requests', 'WhatsApp link Preview', 'Yahoo! Slurp', 'Mozilla spider'):
            self.assertTrue(stats.is_bot(ua), ua)
        self.assertFalse(stats.is_bot('Mozilla/5.0 (iPhone) Safari'))
        self.assertFalse(stats.is_bot(None))

    def test_stats(self):
        stats.record_view(self.con, 1, '2026-10-17'); stats.record_view(self.con, 1, '2026-10-17')
        stats.record_view(self.con, 2, '2026-10-10'); stats.record_view(self.con, 3, '2026-10-17')
        stats.record_view(self.con, 1, '2026-01-01')  # outside window
        self.lead(ago(hours=3), ago(hours=3) and (NOW - datetime.timedelta(hours=3) + datetime.timedelta(minutes=2)).strftime(lw.FMT))
        self.lead(ago(hours=2), (NOW - datetime.timedelta(hours=2) + datetime.timedelta(minutes=10)).strftime(lw.FMT), listing=2, source='bolsa')
        self.lead(ago(days=8), (NOW - datetime.timedelta(days=8) + datetime.timedelta(minutes=4)).strftime(lw.FMT))
        self.lead(ago(minutes=30), None, status='nuevo')
        self.lead(ago(days=60), None, status='nuevo')  # outside window, still counted as unanswered_now
        self.lead(ago(hours=1), None, status='nuevo', agency=2, listing=3)
        s = stats.agency_stats(self.con, 1, now=NOW)
        self.assertEqual(s['views_total'], 3)
        self.assertEqual(s['views_by_listing'][0], {'ref': 'A-1', 'title': 'Uno', 'views': 2, 'leads': 3})
        self.assertEqual(s['views_by_listing'][1]['ref'], 'A-2')
        self.assertEqual(s['leads_total'], 4)
        self.assertEqual(s['leads_by_source'], {'sitio': 3, 'bolsa': 1})
        self.assertEqual(len(s['leads_by_week']), 8)
        self.assertEqual(s['leads_by_week'][-1], {'week': '2026-W42', 'leads': 3})
        self.assertEqual(s['leads_by_week'][-2], {'week': '2026-W41', 'leads': 1})
        self.assertEqual(s['median_first_response_min'], 4.0)
        self.assertEqual(s['pct_answered_5min'], 50.0)
        self.assertEqual(s['unanswered_now'], 2)
        self.assertEqual(s['top_colonias'][0], ('Polanco', 3))


if __name__ == '__main__':
    unittest.main()
