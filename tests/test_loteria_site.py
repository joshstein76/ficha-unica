"""Lotería agent-site design (Josh 2026-11-03): light only, default for NEW sign-ups and unknown design keys,
every public page renders with it, the other three designs are untouched, and the picker offers it."""
import glob
import os
import tempfile
import unittest

from llave import db, photos
from llave.web import common, panel, server, site, styles
from tests.test_photos import make_jpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_DESIGNS = ('residencia', 'ciudad', 'costa')


class LoteriaSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._old_media = db.MEDIA_DIR
        db.MEDIA_DIR = os.path.join(cls.tmp, 'media')
        cls.con = db.connect(os.path.join(cls.tmp, 't.db'))
        db.init(cls.con)
        server.signup(cls.con, {'name': 'María López', 'agency': 'Casa Coyoacán', 'whatsapp': '55 1234 5678',
                                'email': 'maria@ejemplo.test', 'password': 'segura1234', 'terms': '1'})
        cls.con.execute("UPDATE agencies SET accent='#FFB800' WHERE id=1")
        cls.con.execute("UPDATE users SET slug='maria', zones='Narvarte, Del Valle', bio='Asesora en Narvarte.' WHERE id=1")
        cls.con.execute(
            "INSERT INTO listings(agency_id,agent_id,ref,slug,title,description,status,operation,price_cents,currency,price_date,"
            "m2_built,bedrooms,bathrooms,parking,colonia,municipio,estado,amenities,updated_at) VALUES "
            "(1,1,'CC-1','depa-narvarte','Depa con balcón en Narvarte',?,'activa','renta',1850000,"
            "'MXN','2026-11-01',72,2,1,1,'Narvarte','Benito Juárez','Ciudad de México','[\"Balcón\",\"Gimnasio\"]','2026-11-02 10:00:00')",
            ('Luminoso y con balcón. ' * 8,))
        cls.con.commit()
        for i in range(5):
            photos.ingest(cls.con, 1, make_jpeg((1800, 1200), color=(80 + i * 30, 120, 160), seed=i))

    @classmethod
    def tearDownClass(cls):
        db.MEDIA_DIR = cls._old_media
        cls.con.close()

    def agency(self, design=None):
        if design is not None:
            self.con.execute('UPDATE agencies SET design=? WHERE id=1', (design,))
            self.con.commit()
        return self.con.execute('SELECT * FROM agencies WHERE id=1').fetchone()

    def pages(self, design=None):
        a = self.agency(design)
        return a, site.home(self.con, a), site.listing(self.con, a, db.canonical(self.con, 1))

    # ---- default for new agencies -------------------------------------------------------------------------------
    def test_new_signup_defaults_to_loteria_and_existing_keep_theirs(self):
        self.assertEqual(db.DEFAULT_DESIGN, 'loteria')
        self.assertEqual(styles.DEFAULT_DESIGN_FALLBACK, db.DEFAULT_DESIGN)
        con = db.connect(':memory:')
        db.init(con)
        server.signup(con, {'name': 'Ana', 'agency': 'Nueva Agencia', 'whatsapp': '55 9999 0000', 'email': 'ana@ejemplo.test',
                            'password': 'segura1234', 'terms': '1'})
        self.assertEqual(con.execute("SELECT design FROM agencies WHERE slug='nueva-agencia'").fetchone()[0], 'loteria')
        # a fresh database also defaults to it when a row does not say
        con.execute("INSERT INTO agencies(slug,name) VALUES('sin-diseno','Sin diseño')")
        self.assertEqual(con.execute("SELECT design FROM agencies WHERE slug='sin-diseno'").fetchone()[0], 'loteria')
        # re-running db.init (every start-up) never rewrites an agency's design
        con.execute("UPDATE agencies SET design='costa' WHERE slug='nueva-agencia'")
        con.execute("INSERT INTO agencies(slug,name,design) VALUES('vieja','Vieja','ciudad')")
        db.init(con)
        self.assertEqual([r[0] for r in con.execute("SELECT design FROM agencies WHERE slug IN ('nueva-agencia','vieja') ORDER BY slug")],
                         ['costa', 'ciudad'])

    def test_signup_sets_loteria_even_on_a_database_made_before_the_new_default(self):
        """SQLite cannot change a column default in place, so on an old database a row that does not name its design still
        gets 'ciudad'. The sign-up INSERT names the design itself, so new sign-ups get Lotería there too."""
        with open(os.path.join(ROOT, 'llave', 'schema.sql'), encoding='utf-8') as f:
            new_sql = f.read()
        old_sql = new_sql.replace("design TEXT NOT NULL DEFAULT 'loteria'", "design TEXT NOT NULL DEFAULT 'ciudad'")
        self.assertNotEqual(old_sql, new_sql)
        con = db.connect(':memory:')
        con.executescript(old_sql)
        db.init(con)                                             # start-up on an existing database
        con.execute("INSERT INTO agencies(slug,name) VALUES('antes','Antes')")
        self.assertEqual(con.execute("SELECT design FROM agencies WHERE slug='antes'").fetchone()[0], 'ciudad')
        server.signup(con, {'name': 'Luis', 'agency': 'Despues', 'whatsapp': '55 8888 0000', 'email': 'luis@ejemplo.test',
                            'password': 'segura1234', 'terms': '1'})
        self.assertEqual(con.execute("SELECT design FROM agencies WHERE slug='despues'").fetchone()[0], 'loteria')
        self.assertEqual(con.execute("SELECT design FROM agencies WHERE slug='antes'").fetchone()[0], 'ciudad')   # existing keep theirs

    def test_unknown_design_key_renders_as_loteria(self):
        a, home, lp = self.pages('neon')
        for page in (home, lp):
            self.assertIn(styles.LOTERIA_CSS, page)
            self.assertNotIn('prefers-color-scheme', page)
            self.assertIn('Bricolage+Grotesque', page)
        self.assertEqual(styles.site_css('neon', '#123456'), styles.site_css('loteria', '#123456'))
        self.assertEqual(styles.resolve_design(None), 'loteria')
        self.assertEqual(styles.site_fonts_url('neon'), styles.site_fonts_url('loteria'))

    # ---- the design ---------------------------------------------------------------------------------------------
    def test_home_and_listing_render_with_loteria_css_and_no_dark_block(self):
        a, home, lp = self.pages('loteria')
        for name, page in (('home', home), ('listing', lp)):
            self.assertIn(styles.LOTERIA_CSS, page, name)
            self.assertNotIn('prefers-color-scheme', page, name)           # no dark-mode block, anywhere on the page
            self.assertIn('color-scheme:light', page, name)
            self.assertIn('<meta name="color-scheme" content="light">', page, name)
            self.assertIn('family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,800', page, name)
            self.assertNotIn('Shrikhand', page, name)
            self.assertIn('--accent:#ffb800', page, name)                   # the agent's colour is the highlight
            self.assertRegex(page, r'--on-accent:#[0-9A-Fa-f]{6}', name)
            self.assertRegex(page, r'<a class="wa" href="https://wa\.me/[^"]+" rel="nofollow"', name)   # still a plain link
            self.assertIn('<main id="main"', page, name)
            self.assertEqual(page.count('class="coin"'), 1, name)           # the ficha coin beside the credit
            self.assertRegex(page, r'<svg class="coin"[^>]*aria-hidden="true".*?</svg>Sitio creado con <a href="[^"]+\?source=sitio-casa-coyoacan" rel="nofollow">Ficha Única</a>', name)
        # SEO untouched: JSON-LD, canonical, FAQ and the form posts
        self.assertIn('"@type": "RealEstateAgent"', home)
        base = db.site_url(a)                                              # port differs when other test modules ran first
        self.assertIn('rel="canonical" href="%s/"' % base, home)
        self.assertIn('"@type": "RealEstateListing"', lp)
        self.assertIn('rel="canonical" href="%s/propiedad/depa-narvarte"' % base, lp)
        self.assertIn('<form method="post" action="/contacto">', lp)
        self.assertIn('<form class="box alertf" method="post" action="/alerta"', home)
        self.assertIn('<section class="hero"><picture>', home)
        self.assertIn('<div class="cap"><div class="in"><h1>Casa Coyoacán</h1>', home)

    def test_loteria_look_is_the_prototype(self):
        css = styles.LOTERIA_CSS
        for needle in ('font-stretch:80%', 'border:3px solid var(--fg)', '4px 4px 0 var(--fg)', '6px 6px 0 var(--fg)',
                       'background:var(--nopal)', 'color:var(--fg);box-shadow:3px 3px 0', 'translate(3px,3px)', 'translate(-1px,-1px)',
                       'prefers-reduced-motion:reduce', ':focus-visible{outline:3px solid var(--jac);outline-offset:3px}',
                       '.hero picture+.cap{position:absolute'):
            self.assertIn(needle, css)
        self.assertNotIn('gradient', css)                                   # hard shadows, no gradients
        self.assertNotRegex(css, r'box-shadow:[^;}]*\d+px \d+px [1-9]\d*px')  # no blurred shadows
        self.assertNotIn('prefers-color-scheme', css)
        self.assertIn('--fg:#1B1236', styles.DESIGN_TOKENS['loteria'])
        self.assertIn('color-scheme:light', styles.DESIGN_TOKENS['loteria'])
        self.assertNotIn('dark', styles.site_css('loteria', '#123456', dark_mode=True).lower())

    def test_other_designs_are_untouched(self):
        for d in OLD_DESIGNS:
            a, home, lp = self.pages(d)
            for page in (home, lp):
                self.assertIn('prefers-color-scheme:dark', page, d)
                self.assertNotIn('Bricolage', page, d)
                self.assertNotIn('class="coin"', page, d)
                self.assertNotIn('<meta name="color-scheme"', page, d)
                self.assertNotIn('.hero picture+.cap', page, d)
                self.assertIn('<span class="muted">Sitio creado con <a href="', page, d)
            self.assertIn(styles.SITE_BASE, home)
            self.assertIn(styles.DESIGN_TOKENS[d], home)
        self.agency('loteria')

    def test_every_public_page_renders_in_loteria(self):
        a = self.agency('loteria')
        c = db.canonical(self.con, 1)
        u = self.con.execute('SELECT * FROM users WHERE id=1').fetchone()
        home = site.home(self.con, a)
        self.assertIn('<h2>Equipo</h2><div class="team"><a class="agent" href="/asesor/maria">', home)   # team block
        self.assertIn('<h2>Propiedades</h2><div class="cards"><a class="lc" href="/propiedad/depa-narvarte">', home)
        pages = {
            'thanks': site.thanks(a, 'https://wa.me/525512345678'), 'thanks-msg': site.thanks(a, '', 'Listo.'),
            'privacy': site.privacy(a), '404': site.not_found(a), 'valuation': site.valuation(self.con, a),
            'valuation-error': site.valuation(self.con, a, error='Escriba los m² con números.'),
            'valuation-ok': site.valuation(self.con, a, {'ok': True, 'range_low': 1000000, 'range_high': 1200000, 'currency': 'MXN', 'note': 'n'}),
            'valuation-few': site.valuation(self.con, a, {'ok': False}), 'agent': site.agent_profile(self.con, a, u),
            'listing': site.listing(self.con, a, c), 'listing-error': site.listing(self.con, a, c, error='Revisa tu teléfono.'),
        }
        for name, page in pages.items():
            self.assertIn(styles.LOTERIA_CSS, page, name)
            self.assertNotIn('prefers-color-scheme', page, name)
            self.assertRegex(page, r'<body><a class="skip" href="#main">Saltar al contenido</a>', name)
            self.assertRegex(page, r'<main id="main"', name)
            self.assertIn('class="coin"', page, name)
        self.assertIn('<h1>', pages['404'])
        # the printable ficha: Lotería outline + accent bar, still noindex, still no internal notes
        fi = site.ficha(a, c)
        self.assertIn('noindex', fi)
        self.assertIn('Bricolage+Grotesque', fi)
        self.assertIn('print-color-adjust:exact', fi)
        self.assertRegex(fi, r':root\{--accent:#ffb800;--on-accent:#[0-9A-Fa-f]{6}\}')
        self.assertNotIn('prefers-color-scheme', fi)
        self.assertNotIn('Instrument+Serif', fi)                                 # the Residencia font is not loaded for Lotería
        # ...and the old designs' ficha is exactly as before
        fo = site.ficha(self.agency('ciudad'), c)
        self.assertIn('Instrument+Serif', fo)
        self.assertIn(':root{--accent:#FFB800}', fo)
        self.assertNotIn('Bricolage', fo)
        self.agency('loteria')

    # ---- readable on any accent ---------------------------------------------------------------------------------
    def test_text_contrast_on_any_accent(self):
        steps = range(0, 256, 17)
        for r in steps:
            for g in steps:
                for b in steps:
                    acc = '#%02x%02x%02x' % (r, g, b)
                    self.assertGreaterEqual(styles.contrast(styles.loteria_on_accent(acc), acc), 4.5, acc)
        self.assertEqual(styles.loteria_on_accent('#FFB800'), styles.TINTA)        # cempa gets tinta text, as in the prototype
        tinta, papel, blanco = '#1B1236', '#FFF9EE', '#ffffff'
        for fg, bg in ((tinta, blanco), (tinta, papel), ('#5E5478', blanco), ('#5E5478', papel), (tinta, '#0FB56D'), ('#5B2EE6', blanco)):
            self.assertGreaterEqual(styles.contrast(fg, bg), 4.5, (fg, bg))
        # a hostile accent value never reaches the CSS
        css = styles.site_css('loteria', 'red;}</style><script>')
        self.assertIn('--accent:#1f4e79', css)

    # ---- picker + migrations ------------------------------------------------------------------------------------
    def test_design_picker_and_save(self):
        self.assertEqual(common.DESIGNS[0][:2], ('loteria', 'Lotería'))
        self.assertEqual(set(common.DESIGN_KEYS), set(styles.DESIGN_TOKENS))
        self.assertEqual(len(common.DESIGN_KEYS), 4)
        a = self.agency('ciudad')
        u = self.con.execute('SELECT * FROM users WHERE id=1').fetchone()
        ctx = {'agency': a, 'user': u, 'token': 'tok'}
        html = panel.site_settings(self.con, ctx)
        self.assertRegex(html, r'name="design" value="loteria"> <span><b>Lotería</b>')
        self.assertRegex(html, r'name="design" value="ciudad" checked>')
        self.assertIn('<b>Lotería</b>', html)
        self.assertIn('<b>Residencia</b>', html)                              # the others are still offered, word for word
        self.assertIn('Moderno y limpio, ideal para departamentos', html)
        # an unknown stored key is shown as the design it renders as
        html = panel.site_settings(self.con, dict(ctx, agency=self.agency('neon')))
        self.assertRegex(html, r'name="design" value="loteria" checked>')
        # saving: Lotería is accepted, junk keeps the current one
        form = {'name': 'Casa Coyoacán', 'whatsapp': '55 1234 5678', 'accent': '#FFB800', 'design': 'loteria'}
        server.save_site(self.con, self.agency('ciudad'), form, {})
        self.assertEqual(self.agency()['design'], 'loteria')
        server.save_site(self.con, self.agency(), dict(form, design='hacker'), {})
        self.assertEqual(self.agency()['design'], 'loteria')
        server.save_site(self.con, self.agency(), dict(form, design='costa'), {})
        self.assertEqual(self.agency()['design'], 'costa')
        self.agency('loteria')

    def test_postgres_migration_allows_and_defaults_to_loteria(self):
        with open(os.path.join(ROOT, 'supabase', 'migrations', '0001_init.sql'), encoding='utf-8') as f:
            init = f.read()
        self.assertIn("design             text not null default 'loteria'", init)
        self.assertIn("check (design in ('loteria','ciudad','costa','residencia'))", init)
        with open(os.path.join(ROOT, 'supabase', 'migrations', '0006_design_loteria.sql'), encoding='utf-8') as f:
            mig = f.read()
        self.assertIn("alter column design set default 'loteria'", mig)
        self.assertIn("drop constraint if exists agencies_design_chk", mig)
        self.assertIn("check (design in ('loteria','ciudad','costa','residencia'))", mig)
        self.assertEqual(sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, 'supabase', 'migrations', '*.sql')))[-1],
                         '0006_design_loteria.sql')


if __name__ == '__main__':
    unittest.main()
