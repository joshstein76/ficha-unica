import sqlite3
import unittest

from llave import db, formatos, operaciones as op


class Operaciones(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA foreign_keys = ON')
        db.init(self.con)
        for i in (1, 2):
            self.con.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (?,?,?,'+525500000001')", (i, 'a%d' % i, 'Agencia %d' % i))

    def test_venta_tasks_come_from_cierre(self):
        did = op.create(self.con, 1, 'Ana', 'venta')
        labels = [t['label'] for t in op.tasks(self.con, 1, did)]
        self.assertEqual(labels, [l[2:] for l in formatos.BY_KEY['cierre']['body'] if l.startswith('☐ ')])
        self.assertEqual(len(labels), 9)

    def test_renta_tasks(self):
        did = op.create(self.con, 1, 'Beto', 'renta')
        self.assertEqual([t['label'] for t in op.tasks(self.con, 1, did)], op.RENTA_TASKS)

    def test_validation(self):
        with self.assertRaises(ValueError):
            op.create(self.con, 1, '  ', 'venta')
        with self.assertRaises(ValueError):
            op.create(self.con, 1, 'Ana', 'trueque')

    def test_stage_task_counts(self):
        did = op.create(self.con, 1, 'Ana', 'venta')
        self.assertTrue(op.set_stage(self.con, 1, did, 'oferta'))
        with self.assertRaises(ValueError):
            op.set_stage(self.con, 1, did, 'nada')
        tid = op.tasks(self.con, 1, did)[0]['id']
        self.assertTrue(op.set_task(self.con, 1, did, tid, True))
        self.assertEqual(op.listing_all(self.con, 1)[0]['n_done'], 1)
        self.assertEqual(op.counts(self.con, 1)['oferta'], 1)
        self.assertEqual(len(op.listing_all(self.con, 1, 'visita')), 0)

    def test_agency_isolation(self):
        did = op.create(self.con, 1, 'Ana', 'venta')
        tid = op.tasks(self.con, 1, did)[0]['id']
        self.assertIsNone(op.get(self.con, 2, did))
        self.assertEqual(op.tasks(self.con, 2, did), [])
        self.assertEqual(op.listing_all(self.con, 2), [])
        self.assertFalse(op.set_stage(self.con, 2, did, 'cerrada'))
        self.assertFalse(op.set_notes(self.con, 2, did, 'hack'))
        self.assertFalse(op.set_task(self.con, 2, did, tid, True))
        self.assertFalse(op.add_task(self.con, 2, did, 'x'))
        self.assertEqual(op.get(self.con, 1, did)['stage'], 'interesado')
        self.assertEqual(op.tasks(self.con, 1, did)[0]['done'], 0)

    def test_foreign_listing_rejected_and_set_null(self):
        self.con.execute("INSERT INTO listings(id,agency_id,ref,slug,title) VALUES (5,2,'B-1','b-1','Casa B')")
        with self.assertRaises(ValueError):
            op.create(self.con, 1, 'Ana', 'venta', listing_id=5)
        self.con.execute("INSERT INTO listings(id,agency_id,ref,slug,title) VALUES (6,1,'A-1','a-1','Casa A')")
        did = op.create(self.con, 1, 'Ana', 'venta', listing_id=6)
        self.con.execute('DELETE FROM listings WHERE id=6')
        self.assertIsNone(op.get(self.con, 1, did)['listing_id'])


if __name__ == '__main__':
    unittest.main()
