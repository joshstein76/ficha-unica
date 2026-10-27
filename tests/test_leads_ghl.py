import json, os, tempfile, unittest
from llave import db, ghl, leads, whatsapp


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.d, 't.db'))
        db.init(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'vive','VIVE','+525500000001')")
        c.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (2,'otra','Otra','+525500000002')")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,status,operation,title,price_cents,price_date,colonia,"
                  "share_in_bolsa,share_split_pct,rentapoliza_offer) VALUES (1,1,'V-1','heraclito','activa','renta',"
                  "'Depto Heráclito',2500000,'2026-10-01','Polanco',1,50,1)")
        c.execute("INSERT INTO listings(id,agency_id,ref,slug,status,title,colonia) VALUES (2,2,'O-1','casa','activa','Casa X','Roma')")
        c.execute("INSERT INTO shares(listing_id,sharing_agency_id,split_pct) VALUES (2,1,50)")
        c.commit()
        os.environ.pop('LLAVE_GHL_LIVE', None)

    def mk(self, **k):
        a = dict(agency_id=1, listing_id=1, name='Ana Pérez', phone='55 1234 5678', consent=True)
        a.update(k)
        return leads.create_lead(self.con, **a)

    def test_phone(self):
        n = whatsapp.norm_phone
        self.assertEqual(n('55 1234 5678'), '+525512345678')
        self.assertEqual(n('+52 1 55 1234 5678'), '+525512345678')
        self.assertEqual(n('+1 305 695 8257'), '+13056958257')
        self.assertEqual(n('abc'), '')

    def test_wa_link(self):
        self.assertEqual(whatsapp.wa_link('+525512345678', 'Hola ñ?'), 'https://wa.me/525512345678?text=Hola%20%C3%B1%3F')

    def test_consent(self):
        with self.assertRaises(ValueError):
            self.mk(consent=False)
        with self.assertRaises(ValueError):
            self.mk(phone='', email='')

    def test_dedupe_and_outbox(self):
        r1 = self.mk()
        r2 = self.mk()
        self.assertFalse(r1['duplicate']); self.assertTrue(r2['duplicate']); self.assertEqual(r1['id'], r2['id'])
        rows = self.con.execute('SELECT * FROM outbox').fetchall()
        self.assertTrue(rows and all(r['status'] == 'dry_run' and r['ref'] == 'lead:%d' % r1['id'] for r in rows))
        self.assertEqual(self.con.execute('SELECT ghl_status FROM leads').fetchone()[0], 'dry_run')
        for r in rows:
            p = json.loads(r['payload'])
            if p['kind'] == 'ghl.contact_upsert':
                self.assertEqual(p['body']['locationId'], 'DRY_RUN_NO_LOCATION')

    def test_blocked(self):
        r = self.mk(name='Sheila Test')
        self.assertTrue(r['blocked'])
        self.assertEqual(self.con.execute('SELECT status FROM leads WHERE id=?', (r['id'],)).fetchone()[0], 'descartado')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)

    def test_bolsa(self):
        r = self.mk(listing_id=2)
        l = self.con.execute('SELECT * FROM leads WHERE id=?', (r['id'],)).fetchone()
        self.assertEqual((l['owner_agency_id'], l['source']), (2, 'bolsa'))
        alerts = [json.loads(x['payload']) for x in self.con.execute("SELECT payload FROM outbox WHERE kind='ghl.agent_alert'")]
        self.assertEqual(len(alerts), 2)
        self.assertTrue(all('50/50' in a['body']['text'] for a in alerts))
        self.assertEqual({a['agency_slug'] for a in alerts}, {'vive', 'otra'})

    def test_never_messages_lead(self):
        self.mk()
        for x in self.con.execute('SELECT payload FROM outbox'):
            p = json.loads(x['payload'])
            if p['kind'] == 'ghl.agent_alert':
                self.assertEqual(p['audience'], 'agency'); self.assertNotEqual(p['to_whatsapp'], '+525512345678')
            if p['kind'] == 'ghl.lead_first_reply':
                self.assertEqual(p['status'], 'approved_template'); self.assertIn('gracias por escribir', p['body']['text'])
                self.assertNotIn('{', p['body']['text'])
            self.assertNotEqual(p['kind'], 'ghl.message')

    def test_live_flag_without_token_stays_dry_run(self):
        r = self.mk()
        os.environ['LLAVE_GHL_LIVE'] = '1'
        try:
            ghl.queue_for_lead(self.con, r['id'])   # no FU_GHL_TOKEN: nothing pending, nothing raised
        finally:
            os.environ.pop('LLAVE_GHL_LIVE', None)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0], 0)

    def test_rentapoliza(self):
        self.assertIn('RentaPóliza', leads.rentapoliza_offer(db.canonical(self.con, 1)))
        self.assertIsNone(leads.rentapoliza_offer(db.canonical(self.con, 2)))


if __name__ == '__main__':
    unittest.main()
