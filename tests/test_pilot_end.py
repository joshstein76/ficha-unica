"""A free pilot ends: Gratis, nothing deleted, nothing sent. It waits while nobody can pay."""
import datetime
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from llave import billing, db  # noqa: E402
from llave.web import panel  # noqa: E402
import pilot_end_run  # noqa: E402


class PilotEnd(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        self.con = db.connect(self.path)
        self.addCleanup(self.con.close)
        db.init(self.con)

    def agency(self, slug, plan='pro', until=None, sub=None):
        self.con.execute('INSERT INTO agencies(slug, name, email, plan, plan_until, stripe_subscription_id) VALUES (?,?,?,?,?,?)',
                         (slug, slug, slug + '@ejemplo.test', plan, until, sub))
        self.con.commit()

    def plan(self, slug):
        return tuple(self.con.execute('SELECT plan, plan_until FROM agencies WHERE slug=?', (slug,)).fetchone())

    def run_it(self, is_open=True, today='2026-12-02'):
        with mock.patch.object(pilot_end_run, 'payments_open', lambda: is_open):
            return pilot_end_run.main(self.con, today)

    def test_an_ended_pilot_goes_to_gratis(self):
        self.agency('terminado', until='2026-12-01')
        self.run_it()
        self.assertEqual(self.plan('terminado'), ('gratis', None))
        row = self.con.execute("SELECT detail FROM audit WHERE action='plan_change'").fetchone()
        self.assertIn('terminado: pro -> gratis', row[0])

    def test_the_last_day_still_counts_and_others_are_left_alone(self):
        self.agency('hoy', until='2026-12-02')
        self.agency('futuro', until='2026-12-20')
        self.agency('sin-fecha')
        self.agency('paga', until='2026-11-01', sub='sub_1')
        self.run_it()
        self.assertEqual(self.plan('hoy'), ('pro', '2026-12-02'))
        self.assertEqual(self.plan('futuro'), ('pro', '2026-12-20'))
        self.assertEqual(self.plan('sin-fecha'), ('pro', None))
        self.assertEqual(self.plan('paga'), ('pro', '2026-11-01'))

    def test_it_waits_while_nobody_can_pay(self):
        self.agency('terminado', until='2026-12-01')
        self.run_it(is_open=False)
        self.assertEqual(self.plan('terminado'), ('pro', '2026-12-01'))

    def test_payments_open_needs_stripe_and_no_test_lock(self):
        for enabled, lock, want in ((True, False, True), (True, True, False), (False, False, False)):
            with mock.patch.object(billing, 'enabled', lambda: enabled), mock.patch.object(billing, 'test_lock_active', lambda: lock):
                self.assertEqual(pilot_end_run.payments_open(), want)

    def test_running_twice_changes_nothing_more(self):
        self.agency('terminado', until='2026-12-01')
        self.run_it()
        self.run_it()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM audit WHERE action='plan_change'").fetchone()[0], 1)

    def test_a_syncing_failure_never_stops_the_run(self):
        self.agency('a', until='2026-12-01')
        self.agency('b', until='2026-12-01')
        with mock.patch('llave.ghl_live.plan_changed', lambda con, aid: None):
            self.run_it()
        self.assertEqual((self.plan('a')[0], self.plan('b')[0]), ('gratis', 'gratis'))

    def test_the_notice_tells_the_truth_while_payments_are_closed(self):
        ended = {'plan_until': (datetime.date(2026, 12, 2) - datetime.timedelta(days=1)).isoformat()}
        with mock.patch.object(panel.billing, 'enabled', lambda: False):
            closed = panel.pilot_notice(ended, datetime.date(2026, 12, 2))
        self.assertIn('sigues con todo', closed)
        self.assertNotIn('Elige tu plan', closed)
        with mock.patch.object(panel.billing, 'enabled', lambda: True), mock.patch.object(panel.billing, 'test_lock_active', lambda: False):
            opened = panel.pilot_notice(ended, datetime.date(2026, 12, 2))
        self.assertIn('Elige tu plan', opened)


if __name__ == '__main__':
    unittest.main()
