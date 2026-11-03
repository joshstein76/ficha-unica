"""Pro -> Gratis (pilot ends, card cancelled): the public site shows only what the plan allows and the own domain points
to the free address. Nothing is deleted; everything comes back on upgrade."""
import os
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db, feeds  # noqa: E402
from llave.web import panel, portal, site  # noqa: E402
from llave.web.server import Handler  # noqa: E402

TMP = tempfile.mkdtemp()
PORT = 8712


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(host, path):
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, path), headers={'Host': host})
    try:
        resp = urllib.request.build_opener(NoRedirect).open(r, timeout=10)
        return resp.status, resp.read().decode(), dict(resp.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode(), dict(ex.headers)


class PlanDowngrade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'd.db'), os.path.join(TMP, 'media'), PORT
        con = db.connect()
        db.init(con)
        con.execute("INSERT INTO agencies(id,slug,name,whatsapp,plan,custom_domain,domain_verified_at) "
                    "VALUES (1,'rosa','Rosa Bienes','+525577778888','pro','rosabienes.mx',datetime('now'))")
        for i in range(1, 6):  # 5 public listings, newest = 5
            con.execute("INSERT INTO listings(id,agency_id,ref,slug,title,status,operation,property_type,updated_at) "
                        "VALUES (?,1,?,?,?,'activa','venta','casa',datetime('now', ?))",
                        (i, 'R%d' % i, 'casa-%d' % i, 'Casa %d' % i, '-%d hours' % (10 - i)))
            con.execute("INSERT INTO photos(listing_id,position,sha256,sizes,width,height) VALUES (?,0,'s',?,800,600)",
                        (i, '{"1600": "x.jpg", "800": "x.jpg", "400": "x.jpg"}'))
        con.commit()
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def set_plan(self, plan):
        con = db.connect()
        con.execute('UPDATE agencies SET plan=? WHERE id=1', (plan,))
        con.commit()
        con.close()

    def agency(self, con):
        return con.execute('SELECT * FROM agencies WHERE id=1').fetchone()

    def test_pro_shows_all_five_on_own_domain(self):
        self.set_plan('pro')
        con = db.connect()
        self.assertEqual(db.public_listing_ids(con, 1), [5, 4, 3, 2, 1])
        self.assertEqual(db.site_url(self.agency(con)), 'https://rosabienes.mx')
        con.close()
        s, body, _ = get('rosabienes.mx', '/')
        self.assertEqual(s, 200)
        self.assertIn('Casa 1', body)

    def test_gratis_shows_newest_only_and_free_address(self):
        self.set_plan('gratis')
        try:
            con = db.connect()
            a = self.agency(con)
            self.assertEqual(db.public_listing_ids(con, 1), [5])
            self.assertNotIn('rosabienes.mx', db.site_url(a))
            home = site.home(con, a)
            self.assertIn('Casa 5', home)
            self.assertNotIn('Casa 1<', home)
            self.assertNotIn('casa-1', site.sitemap(con, a))
            self.assertEqual([c['id'] for c in feeds._select(con, 1, 'llave_open')], [5])
            self.assertEqual(portal.search(con, {}), [5])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=1 AND status='activa'").fetchone()[0], 5)
            saved, panel.layout = panel.layout, (lambda title, body, *a, **k: body)
            try:
                page = panel.plans(con, {'agency': a, 'csrf': 'x'})
            finally:
                panel.layout = saved
            self.assertIn('Tu sitio muestra solo la más reciente', page)
            con.close()
            s, _, h = get('rosabienes.mx', '/propiedad/casa-5?x=1')  # own domain -> free address, same path
            self.assertEqual(s, 302)
            self.assertTrue(h['Location'].endswith('/propiedad/casa-5?x=1'))
            self.assertNotIn('rosabienes.mx', h['Location'])
            self.assertEqual(get('rosa.fichaunica.localhost', '/propiedad/casa-5')[0], 200)
            self.assertEqual(get('rosa.fichaunica.localhost', '/propiedad/casa-1')[0], 404)  # saved, not public
        finally:
            self.set_plan('pro')
        con = db.connect()
        self.assertEqual(len(db.public_listing_ids(con, 1)), 5)  # upgrade brings everything back
        con.close()


if __name__ == '__main__':
    unittest.main()
