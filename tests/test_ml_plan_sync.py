"""Mercado Libre pause / reactivate follows the plan (feeds/mercadolibre.sync_plan_limit) from every place a plan changes:
the Stripe webhook, the plan switch in the panel, tools/set_plan.py, and the hourly sweep. DRY RUN: outbox rows only, no network.
A problem in the sync must never break a plan change or a webhook."""
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import billing, db  # noqa: E402
from llave.feeds import mercadolibre  # noqa: E402
from tools import ml_plan_sync_run, set_plan  # noqa: E402
import web_harness  # noqa: E402

for _k in billing.SETTING_KEYS + ('LLAVE_STRIPE_LIVE', 'LLAVE_STRIPE_TEST_EMAILS'):
    os.environ.pop(_k, None)
os.environ['LLAVE_STRIPE_ENV_FILE'] = os.path.join(tempfile.mkdtemp(), 'no-stripe.env')

WHSEC = 'whsec_FAKEFAKE'
FULL = {'STRIPE_SECRET_KEY': 'sk_test_FAKEFAKE', 'STRIPE_WEBHOOK_SECRET': WHSEC, 'STRIPE_PRICE_PRO': 'price_pro_x', 'STRIPE_PRICE_IA': 'price_ia_x'}
EMPTY = {k: '' for k in FULL}


def conf(**kw):
    d = dict(FULL)
    d.update(kw)
    return mock.patch.object(billing, 'settings', lambda: dict(d))


def sign(raw):
    t = int(time.time())
    return 't=%d,v1=%s' % (t, hmac.new(WHSEC.encode(), b'%d.' % t + raw, hashlib.sha256).hexdigest())


def event(eid, etype, obj):
    return json.dumps({'id': eid, 'object': 'event', 'type': etype, 'data': {'object': obj}}).encode()


def cancelled(eid, sub):
    return event(eid, 'customer.subscription.deleted', {'object': 'subscription', 'id': sub, 'status': 'canceled', 'customer': 'cus_1', 'items': {'data': []}})


def paid_checkout(eid, agency_id, plan='pro', sub='sub_2'):
    return event(eid, 'checkout.session.completed', {'object': 'checkout.session', 'mode': 'subscription', 'payment_status': 'paid',
                                                     'client_reference_id': str(agency_id), 'customer': 'cus_1', 'subscription': sub,
                                                     'metadata': {'agency_id': str(agency_id), 'plan': plan}})


def seed(con, slug='casa', plan='pro', n=3, sub=None):
    """An agency with n public listings, newest last, each already published on Mercado Libre. Returns (agency id, [listing ids oldest first])."""
    aid = con.execute('INSERT INTO agencies(slug, name, email, plan, stripe_subscription_id) VALUES (?,?,?,?,?)',
                      (slug, 'Casa ' + slug, slug + '@ejemplo.test', plan, sub)).lastrowid
    ids = []
    for i in range(n):
        lid = con.execute("INSERT INTO listings(agency_id, ref, slug, title, status, operation, property_type, price_cents, currency, updated_at) "
                          "VALUES (?,?,?,?, 'activa','venta','casa', 100000000, 'MXN', datetime('now', ?))",
                          (aid, '%s-%d' % (slug, i), '%s-casa-%d' % (slug, i), 'Casa %d en %s' % (i, slug), '-%d hours' % (10 - i))).lastrowid
        con.execute("INSERT INTO portal_publications(listing_id, portal, enabled, status, external_id) VALUES (?,'mercadolibre',1,'publicada',?)",
                    (lid, 'MLM%d' % lid))
        ids.append(lid)
    con.commit()
    return aid, ids


def queued(con, aid=None):
    """[(kind suffix, listing id, status)] of the Mercado Libre pause / reactivate rows, oldest first."""
    rows = con.execute("SELECT o.kind, o.ref, o.status, o.payload FROM outbox o WHERE o.kind IN ('portal.mercadolibre.pause','portal.mercadolibre.reactivate') "
                       "ORDER BY o.id").fetchall()
    out = []
    for r in rows:
        lid = int(r['ref'].split(':')[1])
        if aid is None or con.execute('SELECT agency_id FROM listings WHERE id=?', (lid,)).fetchone()[0] == aid:
            out.append((r['kind'].rsplit('.', 1)[1], lid, r['status']))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 'ml.db'))
        db.init(self.con)
        p = mock.patch.object(urllib.request, 'urlopen', side_effect=AssertionError('the sync is a dry run: no network'))
        p.start()
        self.addCleanup(p.stop)

    def plan(self, aid):
        return self.con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0]

    def hook(self, raw):
        with conf():
            return billing.handle_event(self.con, raw, sign(raw))


class StripeWebhook(Base):
    def test_a_cancelled_subscription_pauses_what_gratis_hides_and_a_new_payment_brings_it_back(self):
        aid, ids = seed(self.con, sub='sub_1')                              # Pro: 3 shown, limit 5
        other, other_ids = seed(self.con, 'otra', plan='pro', n=3, sub='sub_9')
        self.assertEqual(queued(self.con), [])
        r = self.hook(cancelled('evt_1', 'sub_1'))
        self.assertEqual((r['status'], r['outcome'], self.plan(aid)), ('handled', 'plan:gratis', 'gratis'))
        # Gratis shows the newest listing only: the two older ones are paused on Mercado Libre
        self.assertEqual(queued(self.con), [('pause', ids[0], 'dry_run'), ('pause', ids[1], 'dry_run')])
        body = json.loads(self.con.execute("SELECT payload FROM outbox WHERE kind='portal.mercadolibre.pause' ORDER BY id").fetchone()[0])
        self.assertEqual((body['method'], body['path'], body['body'], body['_dry_run']), ('PUT', '/items/MLM%d' % ids[0], {'status': 'paused'}, True))
        self.assertEqual(self.plan(other), 'pro')
        self.assertEqual(queued(self.con, other), [])                        # another agency is untouched
        r = self.hook(cancelled('evt_1', 'sub_1'))                          # Stripe retries: nothing queued twice
        self.assertEqual(r['status'], 'duplicate')
        self.assertEqual(len(queued(self.con)), 2)
        r = self.hook(paid_checkout('evt_2', aid))                          # pays again: back to Pro
        self.assertEqual((r['outcome'], self.plan(aid)), ('plan:pro', 'pro'))
        self.assertEqual(queued(self.con)[2:], [('reactivate', ids[0], 'dry_run'), ('reactivate', ids[1], 'dry_run')])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM outbox WHERE status<>'dry_run' AND kind LIKE 'portal.mercadolibre.%'").fetchone()[0], 0)

    def test_an_event_that_changes_no_plan_does_not_sync(self):
        aid, ids = seed(self.con, sub='sub_1')
        raw = event('evt_a', 'customer.subscription.updated', {'object': 'subscription', 'id': 'sub_1', 'status': 'active', 'customer': 'cus_1',
                                                               'items': {'data': [{'price': {'id': 'price_pro_x'}}]}})
        with mock.patch.object(mercadolibre, 'sync_plan_limit_safe') as sync:
            self.assertEqual(self.hook(raw)['outcome'], 'sin_cambio')
            sync.assert_not_called()
        with mock.patch.object(mercadolibre, 'sync_plan_limit_safe') as sync:
            self.hook(cancelled('evt_b', 'sub_1'))
            sync.assert_called_once_with(self.con, aid)

    def test_a_failing_sync_never_breaks_the_webhook_or_the_plan_change(self):
        aid, ids = seed(self.con, sub='sub_1')
        err = io.StringIO()
        with mock.patch.object(mercadolibre, 'sync_plan_limit', side_effect=RuntimeError('boom')), mock.patch.object(sys, 'stderr', err), \
                mock.patch('llave.alerts.report') as report:
            r = self.hook(cancelled('evt_f', 'sub_1'))
        self.assertEqual((r['status'], r['outcome']), ('handled', 'plan:gratis'))
        self.assertEqual(self.plan(aid), 'gratis')
        self.assertEqual(self.con.execute("SELECT outcome FROM stripe_events WHERE event_id='evt_f'").fetchone()[0], 'plan:gratis')
        self.assertIn('RuntimeError', err.getvalue())
        report.assert_called_once()
        self.assertEqual(report.call_args[0][1], {'path': 'mercadolibre.sync_plan_limit'})      # no agency data, no personal data
        self.assertEqual(queued(self.con), [])
        # the next sweep catches up
        self.assertEqual(sorted(ml_plan_sync_run.main(self.con, out=lambda s: None)[aid]['pause']), ids[:2])

    def test_a_sync_that_dies_half_way_leaves_a_consistent_database(self):
        aid, ids = seed(self.con, sub='sub_1')
        real = mercadolibre.dry_run_update
        calls = []

        def flaky(con, lid, action):
            calls.append(lid)
            if len(calls) == 2:
                raise OSError('disk')
            return real(con, lid, action)

        with mock.patch.object(mercadolibre, 'dry_run_update', flaky), mock.patch.object(sys, 'stderr', io.StringIO()):
            r = self.hook(cancelled('evt_h', 'sub_1'))
        self.assertEqual(r['outcome'], 'plan:gratis')
        self.assertEqual(queued(self.con), [('pause', ids[0], 'dry_run')])
        mercadolibre.sync_plan_limit_safe(self.con, aid)                      # idempotent: only the missing one is queued
        self.assertEqual(queued(self.con), [('pause', ids[0], 'dry_run'), ('pause', ids[1], 'dry_run')])


class SetPlanTool(Base):
    def run_tool(self, *args):
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = set_plan.main(list(args), self.con)
        return code, out.getvalue()

    def test_set_plan_queues_pause_and_reactivate(self):
        aid, ids = seed(self.con, 'piloto', plan='pro')
        code, out = self.run_tool('piloto', 'gratis', '--reason', 'fin del piloto')
        self.assertEqual((code, self.plan(aid)), (0, 'gratis'))
        self.assertEqual(queued(self.con), [('pause', ids[0], 'dry_run'), ('pause', ids[1], 'dry_run')])
        code, _ = self.run_tool('piloto', 'ia', '--reason', 'compró')
        self.assertEqual((code, self.plan(aid)), (0, 'ia'))
        self.assertEqual([q[0] for q in queued(self.con)], ['pause', 'pause', 'reactivate', 'reactivate'])

    def test_set_plan_survives_a_failing_sync(self):
        aid, _ = seed(self.con, 'piloto', plan='pro')
        with mock.patch.object(mercadolibre, 'sync_plan_limit', side_effect=RuntimeError('boom')), mock.patch.object(sys, 'stderr', io.StringIO()):
            code, out = self.run_tool('piloto', 'gratis', '--reason', 'fin del piloto')
        self.assertEqual((code, self.plan(aid)), (0, 'gratis'))
        self.assertIn('ok: piloto ahora gratis', out)


class Sweep(Base):
    def test_the_sweep_catches_a_missed_sync_once_and_only_where_needed(self):
        a, ids_a = seed(self.con, 'a', plan='pro')
        b, ids_b = seed(self.con, 'b', plan='pro')
        self.con.execute("UPDATE agencies SET plan='gratis' WHERE id=?", (a,))          # a plan change that nobody synced
        self.con.commit()
        lines = []
        res = ml_plan_sync_run.main(self.con, out=lines.append)
        self.assertEqual(sorted(res), [a])
        self.assertEqual(queued(self.con), [('pause', ids_a[0], 'dry_run'), ('pause', ids_a[1], 'dry_run')])
        self.assertEqual(json.loads(lines[0].split(' ', 1)[1]), {'agencias': 1, 'pausar': 2, 'reactivar': 0})
        self.assertEqual(ml_plan_sync_run.main(self.con, out=lambda s: None), {})        # second run: nothing new
        self.assertEqual(len(queued(self.con)), 2)

    def test_agencies_without_a_published_item_are_skipped(self):
        aid = self.con.execute("INSERT INTO agencies(slug, name, plan) VALUES ('sola', 'Sola', 'gratis')").lastrowid
        self.con.commit()
        with mock.patch.object(mercadolibre, 'sync_plan_limit') as sync:
            self.assertEqual(mercadolibre.sync_all(self.con), {})
            sync.assert_not_called()


class PlanSwitchInThePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = web_harness.LocalServer('mlplan')

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.u = self.web.signup()
        self.con = db.connect()
        self.addCleanup(self.con.close)

    def post(self, path):
        return self.web.req(path, {'csrf': self.u['csrf']}, cookie=self.u['cookie'])

    def test_test_mode_switch_syncs_mercado_libre(self):
        aid = self.u['aid']
        self.con.execute("UPDATE agencies SET plan='pro', stripe_subscription_id='sub_1' WHERE id=?", (aid,))
        self.con.commit()
        _, ids = (aid, [])
        for i in range(3):
            lid = self.con.execute("INSERT INTO listings(agency_id, ref, slug, title, status, operation, property_type, price_cents, currency, updated_at) "
                                   "VALUES (?,?,?,?, 'activa','venta','casa', 100000000, 'MXN', datetime('now', ?))",
                                   (aid, 'P-%d' % i, 'casa-%d' % i, 'Casa %d' % i, '-%d hours' % (10 - i))).lastrowid
            self.con.execute("INSERT INTO portal_publications(listing_id, portal, enabled, status, external_id) VALUES (?,'mercadolibre',1,'publicada',?)",
                             (lid, 'MLM%d' % lid))
            ids.append(lid)
        self.con.commit()
        with conf(**EMPTY):                                                  # Stripe off: the free test-mode switch
            raw = cancelled('evt_p1', 'sub_1')
            with conf():
                billing.handle_event(self.con, raw, sign(raw))               # the webhook downgrades her and pauses two
            self.assertEqual(queued(self.con, aid), [('pause', ids[0], 'dry_run'), ('pause', ids[1], 'dry_run')])
            s, _, _ = self.post('/plan/pro')
            self.assertEqual(s, 200)
        self.assertEqual(self.con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0], 'pro')
        self.assertEqual([q[0] for q in queued(self.con, aid)], ['pause', 'pause', 'reactivate', 'reactivate'])

    def test_both_panel_paths_call_the_sync_after_the_change(self):
        aid = self.u['aid']
        with conf(**EMPTY), mock.patch.object(mercadolibre, 'sync_plan_limit_safe') as sync:
            s, _, _ = self.post('/plan/pro')                                 # test-mode switch
            self.assertEqual(s, 200)
            sync.assert_called_once()
            self.assertEqual(sync.call_args[0][1], aid)
        self.assertEqual(self.con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0], 'pro')
        with conf(), mock.patch.object(mercadolibre, 'sync_plan_limit_safe') as sync:
            s, _, _ = self.post('/plan/gratis')                              # Stripe on, no subscription: the step down to Gratis
            self.assertEqual(s, 200)
            sync.assert_called_once()
            self.assertEqual(sync.call_args[0][1], aid)
        self.assertEqual(self.con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0], 'gratis')

    def test_a_failing_sync_does_not_break_the_plan_page(self):
        aid = self.u['aid']
        with conf(**EMPTY), mock.patch.object(mercadolibre, 'sync_plan_limit', side_effect=RuntimeError('boom')), mock.patch.object(sys, 'stderr', io.StringIO()):
            s, page, _ = self.post('/plan/pro')
        self.assertEqual(s, 200)
        self.assertIn('Listo: ahora tienes el plan pro', page)
        self.assertEqual(self.con.execute('SELECT plan FROM agencies WHERE id=?', (aid,)).fetchone()[0], 'pro')


if __name__ == '__main__':
    unittest.main()
