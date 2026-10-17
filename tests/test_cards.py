import io
import os
import tempfile
import unittest

from PIL import Image

from llave import cards, db, photos
from tests.test_photos import make_jpeg


class CardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = db.MEDIA_DIR
        db.MEDIA_DIR = os.path.join(self.tmp, 'media')
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(slug,name,whatsapp,accent) VALUES('a','VIVE Polanco','+525578358858','#0b2a4a')")
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title,operation,price_cents,currency,price_date,"
                         "m2_built,bedrooms,bathrooms,parking,colonia,municipio,updated_at) VALUES "
                         "(1,'R1','l1','Departamento con vista al parque','venta',450000000,'MXN','2026-10-17',"
                         "120,2,2,1,'Polanco','Miguel Hidalgo','2026-10-17 10:00:00')")
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title,operation,price_cents,currency,updated_at) "
                         "VALUES (1,'R2','l2','Penthouse','renta',69900000,'USD','2026-10-17 10:00:00')")
        self.con.commit()

    def tearDown(self):
        db.MEDIA_DIR = self._old
        self.con.close()

    def test_sizes_jpeg_no_exif_no_photos(self):
        for kind, size in (('post', (1080, 1350)), ('story', (1080, 1920))):
            im = Image.open(io.BytesIO(cards.render(self.con, 1, kind)))
            self.assertEqual(im.format, 'JPEG')
            self.assertEqual(im.size, size)
            self.assertEqual(len(im.getexif()), 0)
            self.assertNotIn('icc_profile', im.info)

    def test_with_photo(self):
        photos.ingest(self.con, 1, make_jpeg((1800, 1200)))
        data = cards.render(self.con, 1, 'post')
        self.assertEqual(Image.open(io.BytesIO(data)).size, (1080, 1350))
        self.assertEqual(len(Image.open(io.BytesIO(data)).getexif()), 0)

    def test_texts_usd_and_mxn(self):
        _, t1 = cards.render(self.con, 1, return_texts=True)
        self.assertIn('$4,500,000 MXN', t1)
        self.assertIn('EN VENTA', t1)
        self.assertIn('Precio al 17 oct 2026', t1)
        self.assertIn('55 7835 8858', t1)
        _, t2 = cards.render(self.con, 2, 'story', return_texts=True)
        self.assertIn('US$699,000', t2)
        self.assertIn('EN RENTA', t2)

    def test_long_title_wrapped(self):
        title = 'Espectacular departamento remodelado con terraza privada vista panorámica ' * 5
        self.con.execute('UPDATE listings SET title=? WHERE id=1', (title,))
        self.con.commit()
        _, texts = cards.render(self.con, 1, return_texts=True)
        lines = [t for t in texts if t.startswith('Espectacular') or t.startswith('privada') or 'terraza' in t]
        self.assertLessEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith('…'))
        cards.render(self.con, 1, 'story')
        self.con.execute('UPDATE listings SET title=? WHERE id=1', ('X' * 300,))
        cards.render(self.con, 1)

    def test_cache(self):
        p1 = cards.render_cached(self.con, 1, 'post')
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, p1)))
        self.assertEqual(p1, cards.render_cached(self.con, 1, 'post'))
        self.con.execute("UPDATE listings SET updated_at='2026-10-18 09:00:00' WHERE id=1")
        self.con.commit()
        p2 = cards.render_cached(self.con, 1, 'post')
        self.assertNotEqual(p1, p2)
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, p2)))


if __name__ == '__main__':
    unittest.main()
