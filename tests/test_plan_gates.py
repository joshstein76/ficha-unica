"""10-19 plans: Gratis 1 listing · Pro 499 (tools + domain) · Pro + IA 999 (AI). Locked tools show an upsell, never an error."""
import os
import re
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import ThreadingHTTPServer  # noqa: E402
from llave import db  # noqa: E402
from llave.web.server import Handler  # noqa: E402
import test_profile_plan as tp  # noqa: E402

TMP = tempfile.mkdtemp()
PORT = 8696


def req(host, path, data=None, cookie=None):
    saved = tp.BASE
    tp.BASE = 'http://127.0.0.1:%d' % PORT
    try:
        return tp.req(host, path, data, cookie)
    finally:
        tp.BASE = saved


class PlanGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (db.DB_PATH, db.MEDIA_DIR, db.PORT)
        db.DB_PATH, db.MEDIA_DIR, db.PORT = os.path.join(TMP, 'g.db'), os.path.join(TMP, 'media'), PORT
        con = db.connect()
        db.init(con)
        con.close()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        db.DB_PATH, db.MEDIA_DIR, db.PORT = cls.saved

    def signup(self, agency, email, plan='gratis'):
        s, _, h = req('app.fichaunica.localhost', '/registro', {'name': 'Rosa Pérez', 'agency': agency, 'whatsapp': '55 7777 8888',
                                                             'email': email, 'password': 'segura1234', 'terms': '1'})
        self.assertEqual(s, 303)
        cookie = h['Set-Cookie'].split(';')[0]
        con = db.connect()
        con.execute('UPDATE agencies SET plan=? WHERE id=(SELECT agency_id FROM users WHERE email=?)', (plan, email))
        con.commit()
        con.close()
        _, body, _ = req('app.fichaunica.localhost', '/perfil', cookie=cookie)
        return cookie, re.search(r'name="csrf" value="([0-9a-f]+)"', body).group(1)

    def test_limits_and_legacy_plans(self):
        self.assertEqual(db.PLAN_LIMITS, {'gratis': 1, 'pro': 5, 'ia': 25})
        self.assertEqual(db.plan_of({'plan': 'agencia'}), 'ia')
        self.assertEqual(db.plan_of({'plan': 'pro_crm'}), 'ia')
        self.assertTrue(db.plan_has({'plan': 'agencia'}, 'ai'))
        self.assertFalse(db.plan_has({'plan': 'pro'}, 'ai'))
        self.assertFalse(db.plan_has({'plan': 'ia'}, 'team'))

    def test_gratis_sees_upsells_not_errors(self):
        c, k = self.signup('Solo Gratis', 'gratis@ejemplo.test')
        for path, plan in (('/estadisticas', 'Pro'), ('/bolsa', 'Pro'), ('/propiedades/importar', 'Pro'), ('/que-publicar', 'Pro + IA')):
            s, page, _ = req('app.fichaunica.localhost', path, cookie=c)
            self.assertEqual(s, 200, path)
            self.assertIn('Ver el plan %s' % plan, page, path)
        s, page, _ = req('app.fichaunica.localhost', '/sitio/dominio', {'csrf': k, 'domain': 'misitio.mx'}, cookie=c)
        self.assertEqual(s, 403)                                  # own domain checked on the server, not just hidden
        con = db.connect()
        self.assertIsNone(con.execute("SELECT custom_domain FROM agencies WHERE slug='solo-gratis'").fetchone()[0])
        con.close()

    def test_pro_has_tools_not_ai(self):
        c, k = self.signup('Ya Soy Pro', 'pro@ejemplo.test', 'pro')
        s, page, _ = req('app.fichaunica.localhost', '/estadisticas', cookie=c)
        self.assertNotIn('Ver el plan', page)
        s, page, _ = req('app.fichaunica.localhost', '/que-publicar', cookie=c)
        self.assertIn('Ver el plan Pro + IA', page)
        s, _, _ = req('app.fichaunica.localhost', '/sitio/dominio', {'csrf': k, 'domain': 'yasoypro.mx'}, cookie=c)
        self.assertEqual(s, 303)
        s, page, _ = req('app.fichaunica.localhost', '/plan', cookie=c)
        for txt in ('$499 MXN', '$999 MXN', '5 propiedades', '25 propiedades', '1 propiedad'):
            self.assertIn(txt, page)

    def test_production_without_stripe_never_gives_a_paid_plan(self):
        c, k = self.signup('Sin Pagos', 'sinpagos@ejemplo.test')
        saved = db.ENV
        db.ENV = 'production'
        self.addCleanup(setattr, db, 'ENV', saved)
        for key in ('pro', 'ia'):
            s, page, _ = req('app.fichaunica.localhost', '/plan/' + key, {'csrf': k}, cookie=c)
            self.assertEqual(s, 503, key)
            self.assertIn('llega muy pronto', page)
        con = db.connect()
        self.assertEqual(con.execute("SELECT plan FROM agencies WHERE slug='sin-pagos'").fetchone()[0], 'gratis')
        con.close()

    def test_ia_has_everything(self):
        c, _ = self.signup('Con Ia', 'ia@ejemplo.test', 'ia')
        for path in ('/estadisticas', '/bolsa', '/que-publicar', '/propiedades/importar'):
            s, page, _ = req('app.fichaunica.localhost', path, cookie=c)
            self.assertEqual(s, 200, path)
            self.assertNotIn('Ver el plan', page, path)


if __name__ == '__main__':
    unittest.main()
