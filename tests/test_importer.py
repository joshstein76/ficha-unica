"""CSV importer. Uses a temp DB passed explicitly; never touches data/llave.db."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db, importer  # noqa: E402


def make(plan='gratis', slug='vive-polanco'):
    path = os.path.join(tempfile.mkdtemp(), 't.db')
    con = db.connect(path)
    db.init(con)
    aid = con.execute("INSERT INTO agencies(slug,name,plan) VALUES (?,?,?)", (slug, 'Test', plan)).lastrowid
    uid = con.execute("INSERT INTO users(agency_id,name,email,password_hash) VALUES (?,?,?,?)",
                      (aid, 'U', 'u@x.mx', 'x')).lastrowid
    con.commit()
    return con, aid, uid


ES = ('﻿Título;Descripción;Precio;Operación;Tipo de Propiedad;M2 Construcción;Superficie Terreno;Recámaras;Baños;'
      'Estacionamientos;Colonia;Alcaldía;CP;Amenidades;Fotos\r\n'
      'Departamento luminoso en Polanco;"Vista al parque";"$4,500,000";Venta;Depto;120;;3;2 y medio;2;Polanco;Miguel Hidalgo;11560;Gym|Alberca;http://a.mx/1.jpg | http://a.mx/2.jpg\r\n'
      'Casa en renta Coyoacán centro;;28 mil;Renta;Casa;250;300;4;3;1;Del Carmen;Coyoacán;04100;Jardín, Terraza;\r\n'
      'Corto;;1;Venta;Casa;1;1;1;1;1;X;Y;Z;;\r\n')

EN = ('title,description,price,currency,operation,property_type,construction_size,lot_size,bedrooms,bathrooms,parking_spaces,'
      'neighborhood,city,state,zip,public_url\n'
      'Beautiful loft in Roma Norte,Great,"US$699,000",,sale,apartment,90,,2,"2 1/2",1,Roma Norte,Cuauhtémoc,,06700,https://x.mx/p/1\n'
      'Warehouse near airport MX,,"3,200,000",MXN,rent,warehouse,800,1000,,,,Peñón,Venustiano Carranza,CDMX,15530,\n')


class ImporterTests(unittest.TestCase):
    def test_spanish_semicolon_bom(self):
        con, aid, uid = make()
        p = importer.preview(con, aid, ES)
        self.assertEqual(p['total'], 3)
        r0, r1, r2 = p['rows']
        self.assertEqual(r0['action'], 'crear')
        d = r0['data']
        self.assertEqual((d['price_cents'], d['currency'], d['operation'], d['property_type']),
                         (450000000, 'MXN', 'venta', 'departamento'))
        self.assertEqual(d['bathrooms'], 2.5)
        self.assertEqual(d['estado'], 'Ciudad de México')
        self.assertEqual(d['amenities'], ['Gym', 'Alberca'])
        self.assertEqual(d['photo_urls'], ['http://a.mx/1.jpg', 'http://a.mx/2.jpg'])
        self.assertEqual(r1['data']['price_cents'], 2800000)
        self.assertEqual(r1['data']['operation'], 'renta')
        self.assertEqual(r2['action'], 'omitir')
        self.assertEqual(r2['line'], 4)
        self.assertEqual(p['columns_detected']['title'], 'Título')
        self.assertEqual(p['columns_detected']['municipio'], 'Alcaldía')
        self.assertTrue(p['ok'])

    def test_english_easybroker(self):
        con, aid, uid = make()
        p = importer.preview(con, aid, EN)
        a, b = p['rows']
        self.assertEqual((a['data']['price_cents'], a['data']['currency']), (69900000, 'USD'))
        self.assertEqual(a['data']['bathrooms'], 2.5)
        self.assertEqual(a['data']['estado'], 'Ciudad de México')
        self.assertEqual(a['data']['source_url'], 'https://x.mx/p/1')
        self.assertEqual(a['data']['m2_built'], 90.0)
        self.assertEqual(b['data']['operation'], 'renta')
        self.assertEqual(b['data']['property_type'], 'bodega')
        self.assertEqual(b['data']['estado'], 'Ciudad de México')
        self.assertEqual(p['columns_detected']['parking'], 'parking_spaces')

    def test_price_formats(self):
        pp = importer.parse_price
        self.assertEqual(pp('$4,500,000'), (450000000, 'MXN', None))
        self.assertEqual(pp('4.5 mdp')[0], 450000000)
        self.assertEqual(pp('4,5 millones')[0], 450000000)
        self.assertEqual(pp('28 mil')[0], 2800000)
        self.assertEqual(pp('US$699,000')[:2], (69900000, 'USD'))
        self.assertEqual(pp('699000 USD')[:2], (69900000, 'USD'))
        self.assertEqual(pp('4.500.000')[0], 450000000)
        self.assertEqual(pp('1,234.56')[0], 123456)
        self.assertIsNone(pp('')[0])

    def test_baths_formats(self):
        for txt, v in (('2', 2), ('2.5', 2.5), ('2,5', 2.5), ('2 1/2', 2.5), ('2 y medio', 2.5), ('2½', 2.5), ('3', 3)):
            self.assertEqual(importer.parse_baths(txt), v, txt)

    def test_no_price_still_creates_with_warning(self):
        con, aid, uid = make()
        csv_ = 'titulo,colonia,municipio,estado\nCasa sin precio en Roma,Roma,Cuauhtémoc,\n'
        p = importer.preview(con, aid, csv_)
        self.assertEqual(p['rows'][0]['action'], 'crear')
        self.assertTrue(any('Precio a consultar' in x for x in p['rows'][0]['problems']))
        self.assertIsNone(p['rows'][0]['data']['price_cents'])

    def test_missing_location_skipped(self):
        con, aid, uid = make()
        p = importer.preview(con, aid, 'titulo,colonia,municipio\nCasa larga sin estado,Roma,Puebla\n')
        self.assertEqual(p['rows'][0]['action'], 'omitir')
        self.assertIn('estado', p['rows'][0]['problems'][0])

    def test_preview_writes_nothing(self):
        con, aid, uid = make()
        before = (con.execute('SELECT COUNT(*) FROM listings').fetchone()[0], con.execute('SELECT COUNT(*) FROM audit').fetchone()[0])
        importer.preview(con, aid, ES)
        after = (con.execute('SELECT COUNT(*) FROM listings').fetchone()[0], con.execute('SELECT COUNT(*) FROM audit').fetchone()[0])
        self.assertEqual(before, after)

    def test_commit_borrador_refs_slugs_audit_duplicates(self):
        con, aid, uid = make()
        res = importer.commit(con, aid, uid, ES)
        self.assertEqual(len(res['created']), 2)
        self.assertEqual(res['skipped'][0][0], 4)
        rows = con.execute('SELECT * FROM listings ORDER BY id').fetchall()
        self.assertEqual({r['status'] for r in rows}, {'borrador'})
        self.assertEqual([r['ref'] for r in rows], ['VIVE-0001', 'VIVE-0002'])
        self.assertEqual(rows[0]['slug'], 'departamento-luminoso-en-polanco')
        self.assertEqual(rows[0]['price_cents'], 450000000)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM audit WHERE action='listing_import'").fetchone()[0], 1)
        self.assertIn(res['created'][0], res['photo_urls'])
        # same file again: all duplicates
        res2 = importer.commit(con, aid, uid, ES)
        self.assertEqual(res2['created'], [])
        self.assertTrue(any(s[1].startswith('Ya existe') for s in res2['skipped']))
        self.assertEqual(con.execute('SELECT COUNT(*) FROM listings').fetchone()[0], 2)

    def test_same_title_different_price_gets_slug_suffix(self):
        con, aid, uid = make()
        csv_ = ('titulo,precio,colonia,municipio,estado\n'
                'Casa bonita en Condesa,1000000,Condesa,Cuauhtémoc,CDMX\n'
                'Casa bonita en Condesa,2000000,Condesa,Cuauhtémoc,CDMX\n'
                'Casa bonita en Condesa,2000000,Condesa,Cuauhtémoc,CDMX\n')
        res = importer.commit(con, aid, uid, csv_)
        self.assertEqual(len(res['created']), 2)
        slugs = [r['slug'] for r in con.execute('SELECT slug FROM listings ORDER BY id')]
        self.assertEqual(slugs, ['casa-bonita-en-condesa', 'casa-bonita-en-condesa-2'])
        self.assertEqual(res['skipped'][0][0], 4)

    def test_plan_limit_stops(self):
        con, aid, uid = make('gratis')
        lines = ['titulo,precio,colonia,municipio,estado']
        for i in range(13):
            lines.append('Propiedad numero %d en Polanco,%d,Polanco,Miguel Hidalgo,' % (i, 1000000 + i))
        res = importer.commit(con, aid, uid, '\n'.join(lines))
        self.assertEqual(len(res['created']), db.PLAN_LIMITS['gratis'])
        self.assertEqual(len(res['skipped']), 3)
        self.assertTrue(all(s[1] == 'Límite de tu plan' for s in res['skipped']))

    def test_plan_limit_ignores_sold(self):
        con, aid, uid = make('gratis')
        for i in range(10):
            con.execute("INSERT INTO listings(agency_id,ref,slug,title,status,colonia,municipio,estado) VALUES (?,?,?,?,?,?,?,?)",
                        (aid, 'R%d' % i, 's%d' % i, 'Vendida numero %d' % i, 'vendida', 'a', 'b', 'c'))
        con.commit()
        res = importer.commit(con, aid, uid, ES)
        self.assertEqual(len(res['created']), 2)

    def test_tab_delimiter_and_row_cap(self):
        con, aid, uid = make('agencia')
        rows = ['titulo\tcolonia\tmunicipio\testado'] + ['Propiedad %04d de prueba\tX\tY\tZ' % i for i in range(1100)]
        p = importer.preview(con, aid, '\n'.join(rows))
        self.assertEqual(p['total'], 1000)
        self.assertTrue(p['truncated'])


if __name__ == '__main__':
    unittest.main()
