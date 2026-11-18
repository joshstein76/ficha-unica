"""The Estudio look (LLAVE_LOOK=estudio, 2026-11-08): off by default, and when on, the panel + sign-up use it."""
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'llave', 'web', 'static')
sys.path.insert(0, ROOT)
from llave.web import styles  # noqa: E402

ESTUDIO_HEX = {'#0B1020', '#2F5BEA', '#F4F5F8', '#5B6478', '#E3E6EE', '#244AD0', '#CFD5E2', '#E8EEFF', '#0D0D0F', '#FFFFFF', '#F5F5F7', '#FF4F1F', '#2F5BEA', '#FFF1E8', '#1A9F55', '#EEF2FF', '#6E6E73', '#E5E5EA', '#26262B',
               '#D2D2D7', '#A1A1A6', '#E8F7EE', '#FFF0EC', '#FFF6E5', '#0F5132', '#9A2A0C', '#7A4A00', '#C2410C', '#F0F0F3', '#C7C7CC', '#FAFAFA'}


def render(code):
    env = dict(os.environ, LLAVE_LOOK='estudio', LLAVE_DB=':memory:')
    return subprocess.run([sys.executable, '-c', 'import sys;sys.path.insert(0,%r);' % ROOT + code], capture_output=True, text=True, env=env, timeout=60)


class EstudioLook(unittest.TestCase):
    def test_off_by_default(self):
        if os.environ.get('LLAVE_LOOK') in ('estudio', 'pulso'):
            self.skipTest('this run has a new look on')
        self.assertEqual(styles.LOOK, 'loteria')
        self.assertNotIn('Instrument+Serif', styles.PANEL_FONTS)

    def test_only_estudio_colours(self):
        found = {h.upper() for h in re.findall(r'#[0-9a-fA-F]{6}\b', styles.ESTUDIO_CSS + styles.PULSO_CSS)}
        self.assertEqual(found - ESTUDIO_HEX, set())

    def test_signup_in_estudio(self):
        r = render('from llave.web import panel;print(panel.signup())')
        self.assertEqual(r.returncode, 0, r.stderr)
        h = r.stdout
        self.assertIn('Crea tu página. <em>Gratis.</em>', h)
        self.assertIn('Crear mi página gratis', h)
        self.assertIn('Instrument+Serif', h)
        self.assertIn('<circle cx="50" cy="50" r="17" fill="#FFFFFF"/>', h)   # the Estudio mark
        self.assertNotIn('family=Shrikhand', h)                               # the lotería fonts are not loaded
        self.assertIn('action="/registro"', h)                                # same form, same fields
        for field in ('name="name"', 'name="agency"', 'name="whatsapp"', 'name="email"', 'name="password"', 'name="terms"', 'name="website"'):
            self.assertIn(field, h)

    def test_pulso_signup_and_default_site(self):
        env = dict(os.environ, LLAVE_LOOK='pulso', LLAVE_DB=':memory:')
        code = ('import sys;sys.path.insert(0,%r);from llave.web import panel, server;h=panel.signup();'
                'print(\'Tu página. <em>Gratis.</em>\' in h, \'Plus+Jakarta\' in h, \'family=Shrikhand\' in h, server.signup_design())' % ROOT)
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "True True False ('ciudad', '#2F5BEA')")

    def test_default_site_unchanged_when_off(self):
        if os.environ.get('LLAVE_LOOK') in ('estudio', 'pulso'):
            self.skipTest('this run has a new look on')
        from llave.web import server
        from llave import db
        self.assertEqual(server.signup_design(), (db.DEFAULT_DESIGN, db.DEFAULT_ACCENT))

    def test_kit_files(self):
        b = json.load(open(os.path.join(STATIC, 'ficha-unica-brand-estudio.json'), encoding='utf-8'))
        self.assertEqual(b['logo'], '/_s/fu-mark-estudio.svg')
        bp = json.load(open(os.path.join(STATIC, 'ficha-unica-brand-pulso.json'), encoding='utf-8'))
        self.assertEqual(bp['logo'], '/_s/fu-mark-pulso.svg')
        self.assertTrue(os.path.exists(os.path.join(STATIC, 'fu-mark-pulso.svg')))
        self.assertIn('.adk .adk-tabs { display: none; }', open(os.path.join(STATIC, 'ficha-pulso.css'), encoding='utf-8').read())
        self.assertTrue(os.path.exists(os.path.join(STATIC, 'fu-mark-estudio.svg')))
        css = open(os.path.join(STATIC, 'ficha-estudio.css'), encoding='utf-8').read()
        self.assertIn('.adk .adk-tabs { display: none; }', css)   # one nav on phones, like the lotería skin
        plain = json.load(open(os.path.join(STATIC, 'ficha-unica-brand.json'), encoding='utf-8'))
        self.assertEqual(set(b['labels']), set(plain['labels']))  # same words, only the look changes


if __name__ == '__main__':
    unittest.main()
