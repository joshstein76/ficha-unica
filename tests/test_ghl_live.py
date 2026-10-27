import json, os, tempfile, unittest
from unittest import mock

from llave import db, ghl, ghl_live, leads
from llave.web import server

ENV = {'LLAVE_GHL_LIVE': '1', 'FU_GHL_TOKEN': 'secret-token-123', 'FU_GHL_LOCATION_ID': 'LOC1'}
PIPES = {'pipelines': [
    {'id': 'PA', 'name': 'Agentes', 'stages': [{'id': 'S0', 'name': 'Registrado'}, {'id': 'S1', 'name': 'Primera propiedad publicada'},
                                               {'id': 'S2', 'name': 'Pro'}, {'id': 'S3', 'name': 'Pro + IA'}]},
    {'id': 'PL', 'name': 'Leads de sitios', 'stages': [{'id': 'L0', 'name': 'Nuevo'}]}]}


class Resp:
    def __init__(self, data): self.data = json.dumps(data).encode()
    def read(self): return self.data
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Fake:
    """Stands in for urllib.request.urlopen: records (method, path, query, body, headers); answers by 'METHOD path'."""
    def __init__(self, answers=None, fail=None):
        self.calls, self.answers, self.fail = [], answers or {}, fail

    def __call__(self, req, timeout=None):
        path, _, q = req.full_url[len(ghl_live.BASE):].partition('?')
        body = json.loads(req.data) if req.data else None
        self.calls.append((req.get_method(), path, q, body, dict(req.header_items()), timeout))
        if self.fail:
            raise self.fail
        key = '%s %s' % (req.get_method(), path)
        if key in self.answers:
            return Resp(self.answers[key])
        if key.startswith('POST /contacts/upsert'):
            return Resp({'contact': {'id': 'C1'}, 'new': True})
        if key.startswith('GET /opportunities/pipelines'):
            return Resp(PIPES)
        if key.startswith('GET /opportunities/search'):
            return Resp({'opportunities': []})
        return Resp({})

    def paths(self):
        return ['%s %s' % (c[0], c[1]) for c in self.calls]


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.d, 't.db'))
        db.init(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp,email) VALUES (1,'vive','VIVE Polanco','+525500000001','a@vive.mx')")
        c.execute("INSERT INTO users(id,agency_id,name,email,whatsapp,password_hash) VALUES (1,1,'Ana Pérez López','ana@vive.mx','+525500000001','x')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,status,operation,title,colonia) VALUES (1,1,'V-1','depto','activa','renta','Depto','Polanco')")
        c.commit()
        ghl_live._pipelines.clear()
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)

    def rows(self, status=None):
        q = 'SELECT * FROM outbox WHERE kind LIKE "fu.%"' + (' AND status="%s"' % status if status else '') + ' ORDER BY id'
        return self.con.execute(q).fetchall()

    def drain(self, fake, **k):
        with mock.patch('urllib.request.urlopen', fake):
            return ghl_live.drain(self.con, **k)

    # ---- gating
    def test_enabled_needs_all_three(self):
        self.assertTrue(ghl_live.enabled())
        for k in ENV:
            with mock.patch.dict(os.environ, {k: ''}):
                self.assertFalse(ghl_live.enabled(), k)
        with mock.patch.dict(os.environ, {'LLAVE_GHL_LIVE': '0'}):
            self.assertFalse(ghl_live.enabled())

    def test_enqueue_only_when_enabled(self):
        self.assertIsNotNone(ghl_live.enqueue_agent(self.con, 1, 'signup'))
        self.assertEqual(len(self.rows('pending')), 1)
        with mock.patch.dict(os.environ, {'FU_GHL_TOKEN': ''}):
            self.assertIsNone(ghl_live.enqueue_agent(self.con, 1, 'signup'))
            self.assertIsNone(ghl_live.plan_changed(self.con, 1))
        self.assertEqual(len(self.rows()), 1)
        with mock.patch('urllib.request.urlopen', Fake()) as f:   # drain with the flag off never calls out
            with mock.patch.dict(os.environ, {'LLAVE_GHL_LIVE': ''}):
                ghl_live.drain(self.con)
            self.assertFalse(f.calls if hasattr(f, 'calls') else False)

    # ---- agent
    def test_agent_signup_payload_and_new_opportunity(self):
        ghl_live.enqueue_agent(self.con, 1, 'signup')
        f = Fake()
        self.assertEqual(self.drain(f)['sent'], 1)
        up = [c for c in f.calls if c[1] == '/contacts/upsert'][0]
        b = up[3]
        self.assertEqual((b['locationId'], b['firstName'], b['lastName'], b['email'], b['phone'], b['companyName'], b['source']),
                         ('LOC1', 'Ana', 'Pérez López', 'ana@vive.mx', '+525500000001', 'VIVE Polanco', 'Ficha Única app'))
        self.assertEqual(b['tags'], ['fu-agente', 'fu-plan-gratis'])
        cf = {x['key']: x['field_value'] for x in b['customFields']}
        self.assertEqual(cf['contact.fu_agency_slug'], 'vive')
        self.assertEqual(cf['contact.fu_plan'], 'gratis')
        self.assertEqual(cf['contact.fu_listings_published'], 1)
        self.assertIn('vive', cf['contact.fu_site_url'])
        h = up[4]
        self.assertEqual(h['Authorization'], 'Bearer secret-token-123')
        self.assertEqual(h['Version'], '2021-07-28')
        self.assertEqual(up[5], 20)
        opp = [c for c in f.calls if c[0] == 'POST' and c[1] == '/opportunities/'][0][3]
        self.assertEqual((opp['pipelineId'], opp['pipelineStageId'], opp['name'], opp['status'], opp['contactId']),
                         ('PA', 'S0', 'VIVE Polanco · vive', 'open', 'C1'))
        r = self.rows()[0]
        self.assertEqual((r['status'], r['response']), ('sent', 'sent'))
        self.assertNotIn('secret-token', json.dumps([dict(x) for x in self.rows()]))

    def test_first_publish_moves_existing_opportunity(self):
        ghl_live.enqueue_agent(self.con, 1, 'first_publish')
        f = Fake({'GET /opportunities/search': {'opportunities': [{'id': 'O9', 'pipelineStageId': 'S0'}]}})
        self.drain(f)
        put = [c for c in f.calls if c[0] == 'PUT'][0]
        self.assertEqual((put[1], put[3]['pipelineStageId']), ('/opportunities/O9', 'S1'))
        self.assertIn('pipeline_id=PA', [c for c in f.calls if c[1] == '/opportunities/search'][0][2])
        self.assertFalse([c for c in f.calls if c[0] == 'POST' and c[1] == '/opportunities/'])

    def test_first_publish_never_moves_a_paying_agent_backwards(self):
        ghl_live.enqueue_agent(self.con, 1, 'first_publish')
        f = Fake({'GET /opportunities/search': {'opportunities': [{'id': 'O9', 'pipelineStageId': 'S2'}]}})
        self.drain(f)
        self.assertFalse([c for c in f.calls if c[0] == 'PUT'])

    def test_plan_change_swaps_tags_and_moves_stage(self):
        self.con.execute("UPDATE agencies SET plan='ia' WHERE id=1"); self.con.commit()
        ghl_live.plan_changed(self.con, 1)
        f = Fake({'GET /opportunities/search': {'opportunities': [{'id': 'O9', 'pipelineStageId': 'S2'}]}})
        self.drain(f)
        up = [c for c in f.calls if c[1] == '/contacts/upsert'][0][3]
        self.assertEqual(up['tags'], ['fu-agente', 'fu-plan-ia'])
        d = [c for c in f.calls if c[0] == 'DELETE'][0]
        self.assertEqual((d[1], d[3]), ('/contacts/C1/tags', {'tags': ['fu-plan-gratis', 'fu-plan-pro']}))
        self.assertEqual([c for c in f.calls if c[0] == 'PUT'][0][3]['pipelineStageId'], 'S3')

    def test_plan_change_to_gratis_leaves_the_stage(self):
        ghl_live.plan_changed(self.con, 1)   # agency is gratis
        f = Fake({'GET /opportunities/search': {'opportunities': [{'id': 'O9', 'pipelineStageId': 'S2'}]}})
        self.drain(f)
        self.assertFalse([c for c in f.calls if c[0] in ('PUT',) or c[1].startswith('/opportunities')])
        self.assertTrue([c for c in f.calls if c[0] == 'DELETE'])
        self.assertEqual(self.rows()[0]['status'], 'sent')

    def test_missing_pipeline_still_does_the_contact(self):
        ghl_live.enqueue_agent(self.con, 1, 'signup')
        f = Fake({'GET /opportunities/pipelines': {'pipelines': []}})
        self.drain(f)
        self.assertIn('POST /contacts/upsert', f.paths())
        self.assertNotIn('POST /opportunities/', f.paths())
        self.assertEqual(self.rows()[0]['response'], 'sent (no pipeline)')
        self.assertEqual(self.rows()[0]['status'], 'sent')

    # ---- retries
    def test_failure_keeps_pending_then_fails_after_five(self):
        import urllib.error
        ghl_live.enqueue_agent(self.con, 1, 'signup')
        f = Fake(fail=urllib.error.URLError('boom'))
        for i in range(1, 5):
            self.assertEqual(self.drain(f)['retry'], 1)
            r = self.rows()[0]
            self.assertEqual((r['status'], r['attempts']), ('pending', i))
        self.assertEqual(self.drain(f)['failed'], 1)
        r = self.rows()[0]
        self.assertEqual((r['status'], r['attempts']), ('failed', 5))
        self.assertNotIn('secret-token', r['response'])
        self.assertEqual(self.drain(f), {'sent': 0, 'retry': 0, 'failed': 0})   # failed rows are not retried

    def test_http_error_is_recorded_without_token(self):
        import urllib.error, io
        ghl_live.enqueue_agent(self.con, 1, 'signup')
        err = urllib.error.HTTPError('u', 401, 'no', {}, io.BytesIO(b'bad token secret-token-123'))
        self.drain(Fake(fail=err))
        r = self.rows()[0]
        self.assertIn('401', r['response'])
        self.assertNotIn('secret-token', r['response'])

    def test_oldest_first_and_limit(self):
        for _ in range(3):
            ghl_live.enqueue_agent(self.con, 1, 'signup')
        self.drain(Fake(), limit=2)
        self.assertEqual([r['status'] for r in self.rows()], ['sent', 'sent', 'pending'])

    # ---- first_publish once
    def test_first_publish_fires_once_per_agency(self):
        self.assertIsNotNone(ghl_live.first_publish(self.con, 1))
        self.assertIsNone(ghl_live.first_publish(self.con, 1))
        self.assertEqual(ghl_live.sweep_first_publish(self.con), 0)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(json.loads(self.rows()[0]['payload'])['event'], 'first_publish')

    def test_first_publish_needs_a_public_listing(self):
        self.con.execute("UPDATE listings SET status='borrador'"); self.con.commit()
        self.assertIsNone(ghl_live.first_publish(self.con, 1))
        self.assertEqual(len(self.rows()), 0)
        self.con.execute("UPDATE listings SET status='activa'"); self.con.commit()
        self.assertEqual(ghl_live.sweep_first_publish(self.con), 1)

    # ---- wiring
    def test_signup_enqueues(self):
        server.signup(self.con, {'name': 'Luis Gómez', 'agency': 'Casas Luis', 'email': 'luis@x.mx', 'whatsapp': '55 1111 2222',
                                 'password': 'password123', 'terms': '1'})
        r = self.rows('pending')[0]
        self.assertEqual(json.loads(r['payload'])['event'], 'signup')

    def test_set_plan_tool_enqueues(self):
        from tools import set_plan
        set_plan.main(['vive', 'pro', '--reason', 'piloto'], con=self.con)
        self.assertEqual(json.loads(self.rows('pending')[0]['payload'])['event'], 'plan_change')

    # ---- leads
    def mk_lead(self, **k):
        a = dict(agency_id=1, listing_id=1, name='Carla Ruiz', phone='55 1234 5678', message='¿Sigue disponible?', consent=True)
        a.update(k)
        return leads.create_lead(self.con, **a)

    def test_lead_enqueued_next_to_dry_run_rows_and_payload(self):
        r = self.mk_lead()
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM outbox WHERE status='dry_run'").fetchone()[0], 0)
        self.assertEqual(len(self.rows('pending')), 1)
        f = Fake({'GET /opportunities/search': {'opportunities': []}})
        self.drain(f)
        up = [c for c in f.calls if c[1] == '/contacts/upsert'][0][3]
        self.assertEqual(up['tags'], ['fu-lead', 'fu-agencia-vive', 'fu-renta'])
        self.assertEqual((up['source'], up['firstName'], up['lastName'], up['phone']), ('Sitio de VIVE Polanco', 'Carla', 'Ruiz', '+525512345678'))
        cf = {x['key']: x['field_value'] for x in up['customFields']}
        self.assertEqual((cf['contact.fu_listing_ref'], cf['contact.fu_agent']), ('V-1', 'vive'))
        self.assertIn('/propiedad/depto', cf['contact.fu_listing_url'])
        note = [c for c in f.calls if c[1] == '/contacts/C1/notes'][0][3]['body']
        self.assertIn('¿Sigue disponible?', note)
        self.assertIn('V-1', note)
        opp = [c for c in f.calls if c[0] == 'POST' and c[1] == '/opportunities/'][0][3]
        self.assertEqual((opp['pipelineId'], opp['pipelineStageId'], opp['name']), ('PL', 'L0', 'Carla Ruiz · V-1'))
        self.assertEqual(self.rows()[0]['status'], 'sent')

    def test_lead_not_enqueued_when_off(self):
        with mock.patch.dict(os.environ, {'LLAVE_GHL_LIVE': ''}):
            self.mk_lead()
        self.assertEqual(len(self.rows()), 0)

    def test_blocked_and_discarded_leads_are_skipped(self):
        b = self.mk_lead(name='Paulina Sierra', phone='55 9999 0000')
        self.assertTrue(b['blocked'])
        self.assertEqual(len(self.rows()), 0)
        r = self.mk_lead()
        self.con.execute("UPDATE leads SET status='descartado' WHERE id=?", (r['id'],)); self.con.commit()
        f = Fake()
        self.drain(f)   # discarded after queueing: drain skips it without calling GHL
        self.assertEqual(f.calls, [])
        self.assertEqual(self.rows()[0]['response'], 'skipped')

    def test_no_messaging_endpoints_ever(self):
        self.mk_lead()
        ghl_live.enqueue_agent(self.con, 1, 'plan_change')
        f = Fake()
        self.drain(f)
        self.assertFalse([p for p in f.paths() if 'conversations' in p or 'messages' in p])


if __name__ == '__main__':
    unittest.main()
