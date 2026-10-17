import io
import os
import sqlite3
import tempfile
import unittest

from PIL import Image

from llave import db, photos


def make_jpeg(size, color=(120, 90, 60), exif=True, seed=0):
    img = Image.new('RGB', size, color)
    for i in range(0, size[0], 50):  # make content unique per seed
        img.putpixel((min(i + seed, size[0] - 1), 5), (255, 0, 0))
    buf = io.BytesIO()
    kw = {}
    if exif:
        ex = Image.Exif()
        ex[0x010F] = 'FakeCam'
        ex[0x8825] = {1: 'N', 2: (19.0, 25.0, 0.0), 3: 'W', 4: (99.0, 10.0, 0.0)}  # GPS IFD
        kw['exif'] = ex
    img.save(buf, 'JPEG', quality=90, **kw)
    return buf.getvalue()


class PhotosTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = db.MEDIA_DIR
        db.MEDIA_DIR = os.path.join(self.tmp, 'media')
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(slug,name) VALUES('a','A')")
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title) VALUES(1,'R1','l1','L1')")
        self.con.commit()

    def tearDown(self):
        db.MEDIA_DIR = self._old
        self.con.close()

    def path(self, rel):
        return os.path.join(db.MEDIA_DIR, rel)

    def test_sizes_and_no_exif(self):
        src = make_jpeg((2000, 1500))
        self.assertTrue(Image.open(io.BytesIO(src)).getexif())  # source has exif
        pid = photos.ingest(self.con, 1, src, alt='sala')
        import json
        row = self.con.execute('SELECT * FROM photos WHERE id=?', (pid,)).fetchone()
        sizes = json.loads(row['sizes'])
        self.assertEqual(set(sizes), {'1600', '1600w', '800', '800w', '400', '400w'})
        self.assertEqual((row['width'], row['height']), (1600, 1200))
        self.assertEqual(row['position'], 0)
        for k, rel in sizes.items():
            self.assertTrue(os.path.exists(self.path(rel)), rel)
            im = Image.open(self.path(rel))
            self.assertEqual(len(im.getexif()), 0, rel)
            self.assertNotIn('exif', im.info, rel)
        self.assertEqual(Image.open(self.path(sizes['800'])).size[0], 800)
        self.assertEqual(Image.open(self.path(sizes['400w'])).size[0], 400)

    def test_never_upscale(self):
        pid = photos.ingest(self.con, 1, make_jpeg((1000, 700)))
        row = self.con.execute('SELECT width FROM photos WHERE id=?', (pid,)).fetchone()
        self.assertEqual(row['width'], 1000)

    def test_rejects(self):
        with self.assertRaises(ValueError) as c:
            photos.ingest(self.con, 1, make_jpeg((300, 300)))
        self.assertIn('600', str(c.exception))
        with self.assertRaises(ValueError) as c:
            photos.ingest(self.con, 1, make_jpeg((2400, 700)))
        self.assertIn('banner', str(c.exception))
        with self.assertRaises(ValueError):
            photos.ingest(self.con, 1, b'not an image')

    def test_dedupe_and_position(self):
        a = make_jpeg((1200, 900), seed=1)
        b = make_jpeg((1200, 900), seed=2)
        i1 = photos.ingest(self.con, 1, a)
        self.assertEqual(photos.ingest(self.con, 1, a), i1)
        i2 = photos.ingest(self.con, 1, b)
        pos = {r['id']: r['position'] for r in self.con.execute('SELECT id, position FROM photos')}
        self.assertEqual(pos, {i1: 0, i2: 1})
        photos.reorder(self.con, 1, [i2, i1])
        pos = {r['id']: r['position'] for r in self.con.execute('SELECT id, position FROM photos')}
        self.assertEqual(pos, {i2: 0, i1: 1})

    def test_watermark_default_off_and_optional(self):
        src = make_jpeg((1200, 900), color=(30, 30, 30))
        import json
        p0 = photos.ingest(self.con, 1, src)
        s0 = json.loads(self.con.execute('SELECT sizes FROM photos WHERE id=?', (p0,)).fetchone()['sizes'])
        im0 = Image.open(self.path(s0['1600'])).convert('RGB')
        self.assertLess(max(c[1] for c in im0.crop((900, 780, 1200, 900)).getextrema()), 60)  # still dark: no text
        self.con.execute('INSERT INTO listings(agency_id,ref,slug,title) VALUES(1,"R2","l2","L2")')
        p1 = photos.ingest(self.con, 2, src, watermark_text='VIVE Polanco')
        s1 = json.loads(self.con.execute('SELECT sizes FROM photos WHERE id=?', (p1,)).fetchone()['sizes'])
        im1 = Image.open(self.path(s1['1600'])).convert('RGB')
        self.assertGreater(max(c[1] for c in im1.crop((800, 760, 1200, 900)).getextrema()), 60)  # text drawn
        im4 = Image.open(self.path(s1['400'])).convert('RGB')
        self.assertLess(max(c[1] for c in im4.getextrema()), 60)  # none on 400

    def test_delete_removes_files_only_when_unused(self):
        import json
        self.con.execute('INSERT INTO listings(agency_id,ref,slug,title) VALUES(1,"R2","l2","L2")')
        src = make_jpeg((1200, 900))
        p1 = photos.ingest(self.con, 1, src)
        p2 = photos.ingest(self.con, 2, src)
        s = json.loads(self.con.execute('SELECT sizes FROM photos WHERE id=?', (p1,)).fetchone()['sizes'])
        photos.delete(self.con, p1)
        self.assertTrue(os.path.exists(self.path(s['1600'])))  # still used by listing 2
        photos.delete(self.con, p2)
        self.assertFalse(os.path.exists(self.path(s['1600'])))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM photos').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
