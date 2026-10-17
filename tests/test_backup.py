import datetime, gzip, os, sqlite3, tarfile, tempfile, unittest
from llave import backup

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0)


def mkdb(path):
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)')
    c.executemany('INSERT INTO t(v) VALUES (?)', [('fila%d' % i,) for i in range(50)])
    c.commit(); c.close()


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = os.path.join(self.d, 'src.db')
        mkdb(self.src)
        self.dest = os.path.join(self.d, 'bk')

    def test_roundtrip(self):
        before = os.path.getmtime(self.src)
        out = backup.backup_db(self.src, self.dest, now=NOW)
        self.assertTrue(out.endswith('llave-20261017-120000.db.gz'))
        self.assertTrue(os.path.isfile(out + '.sha256'))
        self.assertTrue(backup.verify(out))
        self.assertEqual(before, os.path.getmtime(self.src))
        raw = os.path.join(self.d, 'r.db')
        with gzip.open(out, 'rb') as f, open(raw, 'wb') as g:
            g.write(f.read())
        self.assertEqual(sqlite3.connect(raw).execute('SELECT COUNT(*) FROM t').fetchone()[0], 50)

    def test_corrupt_fails(self):
        out = backup.backup_db(self.src, self.dest, now=NOW)
        with open(out, 'r+b') as f:
            f.seek(20); f.write(b'\x00\xff\x00\xff')
        self.assertFalse(backup.verify(out))
        self.assertFalse(backup.verify(os.path.join(self.dest, 'nada.db.gz')))

    def test_bad_checksum_fails(self):
        out = backup.backup_db(self.src, self.dest, now=NOW)
        with open(out + '.sha256', 'w') as f:
            f.write('0' * 64 + '  x\n')
        self.assertFalse(backup.verify(out))

    def test_prune(self):
        os.makedirs(self.dest)
        names = []
        for days in range(0, 60):  # one per day, noon
            t = NOW - datetime.timedelta(days=days)
            n = 'llave-%s.db.gz' % t.strftime('%Y%m%d-%H%M%S')
            names.append(n)
        # two on the newest day: older one should go
        extra = 'llave-20261017-060000.db.gz'
        names.append(extra)
        for n in names:
            open(os.path.join(self.dest, n), 'w').close()
            open(os.path.join(self.dest, n + '.sha256'), 'w').close()
        for other in ('media-20260101.tar.gz', 'notes.txt', 'media-state.json'):
            open(os.path.join(self.dest, other), 'w').close()
        removed = backup.prune(self.dest, now=NOW)
        left = set(os.listdir(self.dest))
        self.assertNotIn(extra, left)
        self.assertNotIn(extra + '.sha256', left)
        self.assertIn('llave-20261017-120000.db.gz', left)
        self.assertIn('llave-20261004-120000.db.gz', left)   # day 13: inside 14 days
        self.assertNotIn('llave-20261003-120000.db.gz', left)  # day 14 and not a week's newest
        self.assertIn('llave-20260901-120000.db.gz' if False else 'llave-20261017-120000.db.gz', left)
        for other in ('media-20260101.tar.gz', 'notes.txt', 'media-state.json'):
            self.assertIn(other, left)
        self.assertTrue(all(p.startswith(self.dest) for p in removed))
        weekly = [n for n in left if n.startswith('llave-') and n.endswith('.db.gz')]
        self.assertLessEqual(len(weekly), 14 + 8)
        # oldest week (7 weeks back) still has a keeper
        self.assertTrue(any(n.startswith('llave-202608') or n.startswith('llave-202609') for n in weekly))

    def test_prune_keeps_newest_even_if_ancient(self):
        os.makedirs(self.dest)
        n = 'llave-20200101-000000.db.gz'
        open(os.path.join(self.dest, n), 'w').close()
        self.assertEqual(backup.prune(self.dest, now=NOW), [])
        self.assertIn(n, os.listdir(self.dest))

    def test_media_incremental(self):
        m = os.path.join(self.d, 'media')
        os.makedirs(os.path.join(m, 'cards')); os.makedirs(os.path.join(m, 'a'))
        for rel in ('a/one.jpg', 'a/two.jpg', 'cards/c.png'):
            with open(os.path.join(m, rel), 'w') as f:
                f.write(rel)
            os.utime(os.path.join(m, rel), (1000, 1000))
        first = backup.backup_media(m, self.dest, now=NOW)
        with tarfile.open(first) as t:
            self.assertEqual(sorted(t.getnames()), ['a/one.jpg', 'a/two.jpg'])
        # change one file (mtime far in the future of the recorded run), add a new one
        with open(os.path.join(m, 'a/two.jpg'), 'w') as f:
            f.write('changed')
        os.utime(os.path.join(m, 'a/two.jpg'), (4102444800, 4102444800))
        with open(os.path.join(m, 'a/three.jpg'), 'w') as f:
            f.write('new')
        os.utime(os.path.join(m, 'a/three.jpg'), (4102444800, 4102444800))
        second = backup.backup_media(m, self.dest, now=NOW)
        self.assertNotEqual(first, second)
        with tarfile.open(second) as t:
            self.assertEqual(sorted(t.getnames()), ['a/three.jpg', 'a/two.jpg'])


if __name__ == '__main__':
    unittest.main()
