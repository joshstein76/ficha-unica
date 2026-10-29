import datetime
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402
from llave.feeds import build_feed, validate  # noqa: E402
from llave.feeds import mercadolibre  # noqa: E402

SECRET = 'NOTA-SECRETA-INTERNA'
LONG = 'Departamento luminoso con vista al parque, cocina integrada y excelente ubicación. ' * 4


class FeedsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        c = self.con
        c.execute("INSERT INTO agencies(id, slug, name, email) VALUES (1,'vive','VIVE Polanco','a@x.mx')")
        c.execute("INSERT INTO users(id, agency_id, name, email, password_hash) VALUES (1,1,'Ana','ana@x.mx','x')")
        today = datetime.date.today().isoformat()
        c.execute("""INSERT INTO listings(id, agency_id, agent_id, ref, slug, status, operation, property_type, title,
            description, price_cents, price_date, m2_built, bedrooms, bathrooms, parking, colonia, municipio, estado,
            cp, street, lat, lng, show_exact_location, internal_note)
            VALUES (1,1,1,'V-1','depa-uno','activa','venta','departamento','Departamento en Polanco con terraza amplia',
            ?, 850000000, ?, 120, 2, 2.5, 2, 'Polanco','Miguel Hidalgo','CDMX','11560','Masaryk 100', 19.43, -99.19, 0, ?)""",
                  (LONG, today, SECRET))
        c.execute("""INSERT INTO listings(id, agency_id, ref, slug, status, operation, property_type, title, description,
            price_cents, m2_built, colonia, municipio, estado, lat, lng, show_exact_location, internal_note)
            VALUES (2,1,'V-2','depa-dos','activa','renta','casa','Casa en renta en Condesa muy bonita',
            'Casa', 3000000, 90, 'Condesa','Cuauhtémoc','CDMX', 19.4, -99.1, 1, ?)""", (SECRET,))
        c.execute("INSERT INTO listings(id, agency_id, ref, slug, status, title) VALUES (3,1,'V-3','borr','borrador','Borrador de propiedad larga')")
        for i in range(6):
            c.execute("INSERT INTO photos(listing_id, position, sha256, sizes) VALUES (1,?,?,?)",
                      (i, 's%d' % i, json.dumps({'1600': 'x/%d/1600.jpg' % i, '800': 'x/%d/800.jpg' % i, '400': 'x/%d/400.jpg' % i})))
        c.execute("INSERT INTO photos(listing_id, position, sha256, sizes) VALUES (2,0,'r0',?)",
                  (json.dumps({'1600': 'y/1600.jpg', '800': 'y/800.jpg', '400': 'y/400.jpg'}),))
        c.execute("INSERT INTO photos(listing_id, position, sha256, sizes) VALUES (3,0,'b0',?)",
                  (json.dumps({'1600': 'z/1600.jpg'}),))
        for lid in (1, 2, 3):
            c.execute("INSERT INTO portal_publications(listing_id, portal, enabled) VALUES (?,?,?)", (lid, 'trovit', 1))
        c.execute("INSERT INTO portal_publications(listing_id, portal, enabled) VALUES (1,'mitula',1)")
        c.execute("INSERT INTO portal_publications(listing_id, portal, enabled) VALUES (2,'mitula',0)")
        c.commit()

    def test_trovit_counts_and_privacy(self):
        ct, body = build_feed(self.con, 1, 'trovit')
        root = ET.fromstring(body)
        self.assertEqual(root.tag, 'trovit')
        ads = root.findall('ad')
        self.assertEqual(len(ads), 2)  # borrador excluded
        by = {a.findtext('id'): a for a in ads}
        self.assertEqual(by['V-1'].findtext('type'), 'For Sale')
        self.assertEqual(by['V-2'].findtext('type'), 'For Rent')
        self.assertEqual(by['V-1'].find('price').get('currency'), 'MXN')
        self.assertEqual(len(by['V-1'].findall('pictures/picture')), 6)
        self.assertIsNone(by['V-1'].find('latitude'))   # show_exact=0
        self.assertEqual(by['V-2'].findtext('latitude'), '19.4')
        self.assertIn(b'confirmar con Lifull Connect', body)
        row = self.con.execute("SELECT status, last_sync_at FROM portal_publications WHERE listing_id=1 AND portal='trovit'").fetchone()
        self.assertEqual(row['status'], 'en_feed')
        self.assertTrue(row['last_sync_at'])
        r3 = self.con.execute("SELECT status FROM portal_publications WHERE listing_id=3 AND portal='trovit'").fetchone()
        self.assertEqual(r3['status'], 'pendiente')

    def test_mitula_toggles(self):
        _, body = build_feed(self.con, 1, 'mitula')
        ads = ET.fromstring(body).findall('ad')
        self.assertEqual([a.findtext('id') for a in ads], ['V-1'])
        self.assertEqual(ads[0].findtext('type'), 'venta')
        self.assertEqual(ads[0].findtext('property_type'), 'Departamento')

    def test_llave_open_xml_json(self):
        _, body = build_feed(self.con, 1, 'llave_open')
        root = ET.fromstring(body)
        self.assertEqual(root.get('version'), '1')
        self.assertEqual(len(root.findall('listing')), 2)  # all public regardless of toggles
        self.assertNotIn(b'ana@x.mx', body)
        ct, jb = build_feed(self.con, 1, 'llave_open_json')
        self.assertTrue(ct.startswith('application/json'))
        data = json.loads(jb.decode('utf-8'))
        self.assertEqual(len(data['listings']), 2)
        self.assertNotIn('email', data['listings'][0]['agent'] or {})

    def test_internal_note_never_leaks(self):
        for p in ('trovit', 'mitula', 'nestoria', 'llave_open', 'llave_open_json', 'lamudi'):
            self.assertNotIn(SECRET.encode(), build_feed(self.con, 1, p)[1], p)
        self.assertNotIn(SECRET, json.dumps(mercadolibre.build_item(db.canonical(self.con, 1))))

    def test_stub_and_unknown(self):
        ct, body = build_feed(self.con, 1, 'inmuebles24')
        self.assertIn(b'NO activo', body)
        self.assertEqual(len(ET.fromstring(body)), 0)
        with self.assertRaises(ValueError):
            build_feed(self.con, 1, 'nope')

    def test_validate(self):
        self.assertEqual(validate(db.canonical(self.con, 1)), [])
        msgs = ' | '.join(validate(db.canonical(self.con, 2)))
        self.assertIn('1 foto', msgs)
        self.assertIn('descripción es corta', msgs)
        c = db.canonical(self.con, 1)
        c['price_date'] = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
        self.assertTrue(any(m.startswith('Confirma el precio (fecha ') for m in validate(c)))
        c['price'] = None; c['title'] = 'corto'; c['address']['colonia'] = None
        m = ' | '.join(validate(c))
        self.assertIn('Precio a consultar', m); self.assertIn('título es muy corto', m); self.assertIn('la colonia', m)

    def test_mercadolibre(self):
        c1 = db.canonical(self.con, 1)
        p = mercadolibre.dry_run_publish(self.con, 1)
        self.assertEqual(p['category_id'], mercadolibre.CATEGORIES[(c1['property_type'], c1['operation'])])
        self.assertLessEqual(len(p['title']), 60)
        self.assertEqual(p['currency_id'], 'MXN')
        self.assertEqual(len(p['pictures']), 6)
        self.assertTrue(p['pictures'][0]['source'].startswith('http'))
        ids = {a['id']: a['value_name'] for a in p['attributes']}
        self.assertEqual(ids['COVERED_AREA'], '120 m²')
        self.assertEqual(ids['BEDROOMS'], '2')
        self.assertEqual(p['location']['neighborhood']['name'], 'Polanco')
        self.assertIn('plain_text', p['description'])
        c2 = db.canonical(self.con, 2)
        self.assertEqual(mercadolibre.build_item(c2)['category_id'],
                         mercadolibre.CATEGORIES[(c2['property_type'], c2['operation'])])
        row = self.con.execute("SELECT * FROM outbox").fetchone()
        self.assertEqual((row['kind'], row['status'], row['ref']), ('portal.mercadolibre.create', 'dry_run', 'listing:1'))
        self.assertEqual(json.loads(row['payload'])['category_id'], p['category_id'])

    def test_mercadolibre_leaf_categories_and_contact(self):
        c = db.canonical(self.con, 1)
        for (pt, op), cat in [(('casa', 'venta'), 'MLM170527'), (('departamento', 'renta'), 'MLM1479'),
                              (('local', 'venta'), 'MLM1474'), (('bodega', 'renta'), 'MLM50744')]:
            c['property_type'], c['operation'] = pt, op
            self.assertEqual(mercadolibre.category(c), cat)
        c['property_type'] = 'rancho'
        self.assertEqual(mercadolibre.category(c), mercadolibre.PARENT)
        self.assertEqual(mercadolibre.split_phone('55 1234 5678'), ('52', '5512345678'))
        self.assertEqual(mercadolibre.split_phone('+1 (305) 555-0101'), ('1', '3055550101'))
        self.assertEqual(mercadolibre.split_phone('abc'), ('', ''))
        c['property_type'] = 'departamento'
        c['agent'] = {'name': 'Ana', 'whatsapp': '+52 1 55 1234 5678', 'email': 'ana@example.com'}
        sc = mercadolibre.build_item(c)['seller_contact']
        self.assertEqual((sc['country_code2'], sc['phone2'], sc['contact']), ('52', '5512345678', 'Ana'))
        self.assertTrue(sc['phone2'].isdigit())
        self.assertEqual(mercadolibre.blockers(mercadolibre.build_item(c)), [])
        c['agent'] = None; c['agency']['whatsapp'] = ''; c['photos'] = []
        it = mercadolibre.build_item(c)
        self.assertEqual(len(mercadolibre.blockers(it)), 2)
        self.assertIn('Falta un WhatsApp válido del agente (Mercado Libre lo exige)', it['_todo'])

    def test_skip_no_photos_no_title(self):
        self.con.execute("DELETE FROM photos WHERE listing_id=2")
        self.con.commit()
        ads = ET.fromstring(build_feed(self.con, 1, 'trovit')[1]).findall('ad')
        self.assertEqual([a.findtext('id') for a in ads], ['V-1'])


if __name__ == '__main__':
    unittest.main()
