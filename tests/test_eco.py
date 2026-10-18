import datetime, json, os, tempfile, unittest
from llave import db, eco

T0 = datetime.datetime(2026, 10, 17, 12, 0, 0)


class T(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(os.path.join(tempfile.mkdtemp(), 't.db'))
        db.init(self.con)
        eco.ensure_tables(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'a','Agencia A','+525500000001')")
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (2,'b','Agencia B','+525500000002')")
        c.execute("INSERT INTO users(agency_id,name,email,whatsapp,password_hash) VALUES (1,'Ana','Ana@Mail.com','55 1234 5678','x')")
        c.execute("INSERT INTO users(agency_id,name,email,whatsapp,password_hash) VALUES (2,'Beto','beto@mail.com','+525599998888','x')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,title,colonia,municipio) VALUES (1,1,'A-1','a1','Depto','Polanco','Miguel Hidalgo')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,title,colonia,municipio) VALUES (2,2,'B-1','b1','Casa','Roma Norte','Cuauhtémoc')")
        c.commit()

    def earn(self, agency, credits_key=('vive', 'referido_cerrado'), ref='r1'):
        e = eco.record_event(self.con, credits_key[0], credits_key[1], ref, agency, confirmed=True, now=T0)
        return e

    def test_idempotent_record(self):
        a = eco.record_event(self.con, 'vive', 'referido_enviado', 'x1', 1)
        b = eco.record_event(self.con, 'vive', 'referido_enviado', 'x1', 1)
        self.assertTrue(a['created']); self.assertFalse(b['created']); self.assertEqual(a['id'], b['id'])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM eco_events').fetchone()[0], 1)
        with self.assertRaises(ValueError):
            eco.record_event(self.con, 'vive', 'nope', 'x2', 1)

    def test_confirm_balance_once(self):
        e = eco.record_event(self.con, 'rentapoliza', 'poliza_emitida', 'F1', 1)
        self.assertEqual(eco.balance(self.con, 1), 0)  # claim alone gives nothing
        self.assertTrue(eco.confirm_event(self.con, e['id'], 'admin'))
        self.assertFalse(eco.confirm_event(self.con, e['id'], 'admin'))
        self.assertEqual(eco.balance(self.con, 1), 30)

    def test_reject(self):
        e = eco.record_event(self.con, 'cerquito', 'pedido', 'P1', 1)
        self.assertTrue(eco.reject_event(self.con, e['id'], 'admin', 'falso'))
        self.assertFalse(eco.confirm_event(self.con, e['id'], 'admin'))
        self.assertEqual(eco.balance(self.con, 1), 0)

    def test_redeem_insufficient_ok_and_boost_window(self):
        with self.assertRaises(eco.InsufficientCredits):
            eco.redeem(self.con, 1, 'destacar_7d', 1, now=T0)
        self.earn(1)  # +50
        with self.assertRaises(ValueError):
            eco.redeem(self.con, 1, 'destacar_7d', 2, now=T0)  # not their listing
        r = eco.redeem(self.con, 1, 'destacar_7d', 1, now=T0)
        self.assertEqual(r['balance'], 30)
        self.assertEqual(eco.balance(self.con, 1), 30)
        self.assertTrue(eco.active_boost(self.con, 1, now=T0 + datetime.timedelta(days=6, hours=23)))
        self.assertFalse(eco.active_boost(self.con, 1, now=T0 + datetime.timedelta(days=7)))
        self.assertFalse(eco.active_boost(self.con, 1, now=T0 - datetime.timedelta(minutes=1)))
        neg = self.con.execute('SELECT delta FROM eco_ledger WHERE delta<0').fetchall()
        self.assertEqual([x[0] for x in neg], [-20])
        eco.redeem(self.con, 1, 'extra_10_listings_30d', now=T0)
        self.assertEqual(eco.extra_listing_slots(self.con, 1, now=T0), 10)
        self.assertEqual(eco.extra_listing_slots(self.con, 1, now=T0 + datetime.timedelta(days=31)), 0)

    def test_priority_ordering(self):
        self.earn(1, ref='a1'); self.earn(1, ref='a2')         # 100
        self.earn(2, ref='b1')                                 # 50
        self.earn(1, ('fichaunica', 'colega_publica'), 'a3')   # 110
        self.assertEqual(eco.priority_agencies(self.con, now=T0), [])
        eco.redeem(self.con, 2, 'prioridad_leads_30d', now=T0)  # B: 50-40=10
        self.assertEqual([x['agency_id'] for x in eco.priority_agencies(self.con, now=T0)], [2])
        eco.redeem(self.con, 1, 'prioridad_leads_30d', now=T0)  # A: 110-40=70
        self.assertEqual([x['agency_id'] for x in eco.priority_agencies(self.con, now=T0)], [1, 2])
        self.assertEqual([x['agency_id'] for x in eco.priority_agencies(self.con, colonia='polanco', now=T0)], [1])
        self.assertEqual([x['agency_id'] for x in eco.priority_agencies(self.con, municipio='Cuauhtemoc', now=T0)], [2])
        self.assertEqual(eco.priority_agencies(self.con, now=T0 + datetime.timedelta(days=31)), [])

    def test_signature_and_replay(self):
        body = b'{"event":"poliza.emitida"}'
        ts = 1_800_000_000
        sig = eco.sign('s3', body, ts)
        self.assertTrue(eco.verify_webhook('s3', body, sig, ts, now=ts + 10))
        self.assertTrue(eco.verify_webhook('s3', body, sig[7:], ts, now=ts + 10))        # bare hex ok
        self.assertFalse(eco.verify_webhook('s3', body, sig, ts, now=ts + 301))           # replay window
        self.assertFalse(eco.verify_webhook('otro', body, sig, ts, now=ts))               # wrong secret
        self.assertFalse(eco.verify_webhook('s3', body + b' ', sig, ts, now=ts))          # tampered
        self.assertFalse(eco.verify_webhook('s3', body, sig, ts + 1, now=ts))             # ts is signed
        self.assertFalse(eco.verify_webhook('s3', body, '', ts, now=ts))
        self.assertTrue(eco.verify_webhook('s3', body, eco.sign('s3', body)))             # no-timestamp form

    def test_rentapoliza_webhook(self):
        b = {'event': 'poliza.emitida', 'folio': 'RP-1', 'agent_email': 'ana@mail.com', 'agent_phone': '',
             'listing_ref': 'A-1', 'tenant_name': 'NO DEBE GUARDARSE'}
        r = eco.handle_rentapoliza_webhook(self.con, b, now=T0)
        self.assertEqual((r['ok'], r['code']), (True, 'confirmado'))
        self.assertEqual(eco.balance(self.con, 1), 30)
        r2 = eco.handle_rentapoliza_webhook(self.con, b, now=T0)
        self.assertEqual(r2['code'], 'duplicado'); self.assertEqual(eco.balance(self.con, 1), 30)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM outbox WHERE kind='ghl.tag'").fetchone()[0], 1)
        p = json.loads(self.con.execute("SELECT payload FROM outbox WHERE kind='ghl.tag'").fetchone()[0])
        self.assertEqual(p['body']['tags'], ['eco-source-rentapoliza', 'eco-referral-fichaunica-rentapoliza'])
        self.assertEqual(p['mode'], 'dry_run')
        self.assertNotIn('NO DEBE', self.con.execute('SELECT meta FROM eco_events').fetchone()[0])
        # by phone (different formatting), agency 2
        r3 = eco.handle_rentapoliza_webhook(self.con, {'event': 'poliza.emitida', 'folio': 'RP-2', 'agent_phone': '55 9999 8888'}, now=T0)
        self.assertEqual(r3['code'], 'confirmado'); self.assertEqual(eco.balance(self.con, 2), 30)
        self.assertEqual(eco.handle_rentapoliza_webhook(self.con, {'event': 'poliza.emitida', 'folio': 'RP-3', 'agent_email': 'x@y.com'})['code'], 'asesor_no_encontrado')
        self.assertEqual(eco.handle_rentapoliza_webhook(self.con, {'event': 'otra'})['code'], 'evento_no_soportado')

    def test_owner_report(self):
        self.earn(1, ref='v1'); self.earn(1, ('cerquito', 'pedido'), 'p1'); self.earn(2, ('cerquito', 'pedido'), 'p2')
        eco.record_event(self.con, 'cerquito', 'pedido', 'p3', 2, now=T0)  # pending
        eco.record_event(self.con, 'cerquito', 'pedido', 'old', 2, now=T0 - datetime.timedelta(days=90))
        rep = eco.owner_report(self.con, 30, now=T0)
        self.assertEqual(rep['by_brand']['cerquito'], {'events': 3, 'confirmed': 2, 'credits': 10})
        self.assertEqual(rep['by_brand']['vive']['credits'], 50)
        self.assertEqual(rep['by_pair']['fichaunica→cerquito'], 2)
        self.assertEqual(rep['by_pair']['fichaunica→vive'], 1)
        self.assertEqual(rep['top_agencies'][0]['agency_id'], 1)

    def test_planner_and_definition(self):
        from tools import eco_ghl_tags
        p = eco_ghl_tags.plan()
        self.assertTrue(any('eco-referral-vive-fichaunica' in s['tags'] for s in p))
        self.assertIn('no garantizamos', eco.FREE_LEADS_DEFINITION.lower())


if __name__ == '__main__':
    unittest.main()
