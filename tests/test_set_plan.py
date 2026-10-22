"""tools/set_plan.py: pilot agents get a plan by hand, with an end date and an audit row (Josh 10-21: Pro free in the pilot)."""
import datetime
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402
from tools import set_plan  # noqa: E402


class SetPlan(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 's.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(slug, name) VALUES ('piloto-uno', 'Piloto Uno')")
        self.con.commit()

    def run_tool(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = set_plan.main(list(args), self.con)
        return code, out.getvalue()

    def agency(self):
        return self.con.execute("SELECT * FROM agencies WHERE slug='piloto-uno'").fetchone()

    def test_pilot_pro_with_end_date_and_audit(self):
        code, _ = self.run_tool('piloto-uno', 'pro', '--reason', 'piloto', '--until', '2026-11-30')
        self.assertEqual(code, 0)
        a = self.agency()
        self.assertEqual((a['plan'], a['plan_until']), ('pro', '2026-11-30'))
        self.assertEqual(db.listing_limit(self.con, a), 5)
        self.assertTrue(db.plan_has(a, 'domain'))
        row = self.con.execute("SELECT detail FROM audit WHERE action='plan_change'").fetchone()
        self.assertIn('gratis -> pro', row['detail'])
        self.assertIn('piloto', row['detail'])
        self.assertEqual(db.plan_days_left(a, datetime.date(2026, 11, 23)), 7)
        _, listed = self.run_tool('--list')
        self.assertIn('piloto-uno', listed)

    def test_refuses_bad_input(self):
        self.assertEqual(self.run_tool('piloto-uno', 'agencia', '--reason', 'x')[0], 2)   # retired plan
        self.assertEqual(self.run_tool('piloto-uno', 'pro')[0], 2)                        # no reason
        self.assertEqual(self.run_tool('piloto-uno', 'pro', '--reason', 'x', '--until', '30/11')[0], 2)
        self.assertEqual(self.run_tool('nadie', 'pro', '--reason', 'x')[0], 1)
        self.assertEqual(self.agency()['plan'], 'gratis')

    def test_back_to_gratis_clears_date(self):
        self.run_tool('piloto-uno', 'pro', '--reason', 'piloto', '--until', '2026-11-30')
        self.run_tool('piloto-uno', 'gratis', '--reason', 'fin del piloto')
        a = self.agency()
        self.assertEqual((a['plan'], a['plan_until']), ('gratis', None))
        self.assertIsNone(db.plan_days_left(a))


if __name__ == '__main__':
    unittest.main()
