"""LLAVE_PLANS_V2: new plan limits behind ONE switch (docs/DECISIONS.md #74).
Off = today's plans, byte for byte. On = Gratis 3 / Pro 25 / Pro + IA sin límite, the Bolsa open to every plan, and the opt-in
agent-site section "Más propiedades de la Bolsa". Real routes over a local server; direct DB setup only for data a route would not make."""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llave import agent_mail, db, importer, lia  # noqa: E402
from llave.web import panel  # noqa: E402
import web_harness  # noqa: E402

PHOTO = '{"1600": "x.jpg", "800": "x.jpg", "400": "x.jpg"}'
OWNER_WA, OWNER_AGENT_WA, OWNER_EMAIL, OWNER_AGENT = '+525511223344', '+525500001111', 'contacto@owner-test.example', 'Zacarías Dueño'
SHARER_WA = '+525599887766'


def cards(html):
    return len(re.findall(r'class="lc"', html))


def section(html):
    m = re.search(r'<section class="sec" id="bolsa">.*?</section>', html, re.S)
    return m.group(0) if m else ''


def slugs_in(html):
    return re.findall(r'href="/propiedad/([^"/]+)"', html)


class Base(unittest.TestCase):
    def setUp(self):
        self.web = web_harness.LocalServer('plansv2')
        self.addCleanup(self.web.close)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('LLAVE_PLANS_V2', None)

    def v2(self, on=True):
        if on:
            os.environ['LLAVE_PLANS_V2'] = '1'
        else:
            os.environ.pop('LLAVE_PLANS_V2', None)

    def sql(self, query, *args):
        con = db.connect()
        try:
            con.execute(query, args)
            con.commit()
        finally:
            con.close()

    def agency(self, plan='gratis', whatsapp=None):
        u = self.web.signup()
        row = self.web.one('SELECT slug FROM agencies WHERE id=?', u['aid'])
        u['slug'], u['host'] = row[0], '%s.%s' % (row[0], db.BASE_DOMAIN)
        self.sql('UPDATE agencies SET plan=?, whatsapp=? WHERE id=?', plan, whatsapp or SHARER_WA, u['aid'])
        return u

    def listing(self, aid, key, share=False, split=50, status='activa', age=0, agent=None, slug=None, commission=None):
        con = db.connect()
        try:
            lid = con.execute(
                "INSERT INTO listings(agency_id,agent_id,ref,slug,title,status,operation,property_type,price_cents,currency,colonia,municipio,estado,"
                "share_in_bolsa,share_split_pct,commission_pct,updated_at) VALUES (?,?,?,?,?,?,'venta','departamento',350000000,'MXN',"
                "'Roma Norte','Cuauhtémoc','Ciudad de México',?,?,?,datetime('now', ?))",
                (aid, agent, 'R-' + key, slug or ('depa-' + key), 'Departamento %s en Roma Norte' % key, status, int(share), split, commission,
                 '-%d minutes' % age)).lastrowid
            con.execute("INSERT INTO photos(listing_id,position,sha256,sizes,width,height) VALUES (?,0,?,?,800,600)",
                        (lid, 's%d' % lid, PHOTO))
            con.commit()
            return lid
        finally:
            con.close()

    def many(self, aid, n, prefix='x', **kw):
        """n listings, the first one the newest."""
        return [self.listing(aid, '%s%02d' % (prefix, i), age=i, **kw) for i in range(n)]

    def public(self, aid, **kw):
        con = db.connect()
        try:
            return db.public_listing_ids(con, aid, **kw)
        finally:
            con.close()

    def pool(self, aid):
        con = db.connect()
        try:
            return db.pool_listing_ids(con, aid)
        finally:
            con.close()

    def site(self, a, path='/', data=None, host=None):
        return self.web.req(path, data, host=host or a['host'])

    def panel(self, u, path, data=None):
        d = dict(data or {})
        if data is not None:
            d['csrf'] = u['csrf']
        return self.web.req(path, d if data is not None else None, u['cookie'])

    def save_site(self, u, **extra):
        row = self.web.one('SELECT name, whatsapp FROM agencies WHERE id=?', u['aid'])
        d = {'name': row[0], 'whatsapp': row[1]}
        d.update(extra)
        s, page, _ = self.panel(u, '/sitio', d)
        self.assertEqual(s, 200, page[:400])
        return page

    def section_on(self, u, on=True):
        self.sql('UPDATE agencies SET bolsa_section=? WHERE id=?', int(on), u['aid'])


# ---------------------------------------------------------------------------------------------------------- the switch itself
class Switch(Base):
    def test_only_the_exact_value_turns_it_on(self):
        for val, want in (('1', True), ('0', False), ('', False), ('true', False), ('yes', False), (' 1', False)):
            os.environ['LLAVE_PLANS_V2'] = val
            self.assertEqual(db.plans_v2(), want, repr(val))
        os.environ.pop('LLAVE_PLANS_V2')
        self.assertFalse(db.plans_v2())

    def test_off_is_todays_plans_and_the_table_itself_never_changes(self):
        self.assertEqual(db.PLAN_LIMITS, {'gratis': 1, 'pro': 5, 'ia': 25})
        self.assertEqual(db.plan_limits(), db.PLAN_LIMITS)
        con = db.connect(':memory:')
        db.init(con)
        for plan, want in (('gratis', 1), ('pro', 5), ('ia', 25), ('agencia', 25), ('pro_crm', 25), ('whatever', 1)):
            self.assertEqual(db.listing_limit(con, {'id': 1, 'plan': plan}), want, plan)
        self.assertEqual(db.PLAN_FEATURES['bolsa'], db.PLAN_FEATURES['tools'])  # split out, but the same plans while the switch is off
        for plan, want in (('gratis', False), ('pro', True), ('ia', True)):
            self.assertEqual(db.plan_has({'plan': plan}, 'bolsa'), want, plan)
            self.assertEqual(db.plan_has({'plan': plan}, 'tools'), want, plan)

    def test_on_limits_and_the_bolsa_for_every_plan(self):
        self.v2()
        con = db.connect(':memory:')
        db.init(con)
        self.assertEqual([db.listing_limit(con, {'id': 1, 'plan': p}) for p in ('gratis', 'pro', 'ia')], [3, 25, db.UNLIMITED])
        self.assertEqual(db.listing_limit(con, {'id': 1, 'plan': 'agencia'}), db.UNLIMITED)  # a retired plan name is Pro + IA
        self.assertEqual(db.listing_limit(con, {'id': 1, 'plan': 'pro'}, 'gratis'), 3)         # the target plan of a change, not the current one
        self.assertTrue(db.is_unlimited(db.UNLIMITED) and not db.is_unlimited(25) and not db.is_unlimited(None))
        for plan in ('gratis', 'pro', 'ia'):
            self.assertTrue(db.plan_has({'plan': plan}, 'bolsa'), plan)
        # nothing else moved
        for feature, plans in (('tools', ('pro', 'ia')), ('domain', ('pro', 'ia')), ('ai', ('ia',)), ('lia', ('ia',)), ('team', ())):
            for plan in ('gratis', 'pro', 'ia'):
                self.assertEqual(db.plan_has({'plan': plan}, feature), plan in plans, (feature, plan))

    def test_unlimited_stays_unlimited_with_a_referral_bonus_and_extra_slots(self):
        self.v2()
        con = db.connect(':memory:')
        db.init(con)
        con.execute("INSERT INTO agencies(id,slug,name,plan) VALUES (1,'a','A','ia'),(2,'b','B','gratis')")
        con.execute("UPDATE agencies SET referred_by=1 WHERE id=2")
        con.execute("INSERT INTO listings(agency_id,ref,slug,title,status) VALUES (2,'R','r','Una propiedad','activa')")
        con.commit()
        self.assertEqual(db.qualified_referrals(con, 1), 1)
        self.assertEqual(db.listing_limit(con, con.execute('SELECT * FROM agencies WHERE id=1').fetchone()), db.UNLIMITED)
        self.assertEqual(db.listing_limit(con, con.execute('SELECT * FROM agencies WHERE id=2').fetchone()), 3)
        con.execute("UPDATE agencies SET plan='gratis' WHERE id=1")
        self.assertEqual(db.listing_limit(con, con.execute('SELECT * FROM agencies WHERE id=1').fetchone()), 3 + db.REFERRAL_BONUS_LISTINGS)

    def test_the_new_column_is_off_by_default_and_added_to_old_databases(self):
        u = self.agency()
        self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 0)
        old = db.connect(':memory:')
        db.init(old)
        old.execute('ALTER TABLE agencies DROP COLUMN bolsa_section')  # a database created before the column existed
        self.assertNotIn('bolsa_section', {r[1] for r in old.execute('PRAGMA table_info(agencies)')})
        db.init(old)  # the light migration adds it back, OFF
        self.assertIn('bolsa_section', {r[1] for r in old.execute('PRAGMA table_info(agencies)')})
        old.execute("INSERT INTO agencies(slug,name) VALUES ('x','X')")
        self.assertEqual(old.execute('SELECT bolsa_section FROM agencies').fetchone()[0], 0)


# ---------------------------------------------------------------------------------------------------------- listing limits on the real site
class Limits(Base):
    def test_gratis_site_shows_one_off_and_three_on_and_nothing_is_deleted(self):
        u = self.agency('gratis')
        self.many(u['aid'], 5)
        s, home, _ = self.site(u)
        self.assertEqual((s, cards(home)), (200, 1))
        self.v2()
        s, home, _ = self.site(u)
        self.assertEqual(cards(home), 3)
        self.assertEqual(self.public(u['aid']), self.public(u['aid'])[:3])
        self.assertIn('depa-x00', home)                                  # the newest three
        self.assertNotIn('depa-x03', home)
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', u['aid'])[0], 5)
        self.v2(False)
        self.assertEqual(cards(self.site(u)[1]), 1)                      # flip back: the old rule, still nothing lost
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', u['aid'])[0], 5)

    def test_pro_site_shows_five_off_and_twenty_five_on(self):
        u = self.agency('pro')
        self.many(u['aid'], 27)
        self.assertEqual(cards(self.site(u)[1]), 5)
        self.v2()
        self.assertEqual(cards(self.site(u)[1]), 25)

    def test_ia_has_no_limit_on_the_site_and_in_every_public_list(self):
        u = self.agency('ia')
        ids = self.many(u['aid'], 30)
        self.assertEqual(cards(self.site(u)[1]), 25)                     # off: 25
        self.v2()
        self.assertEqual(cards(self.site(u)[1]), 30)
        self.assertEqual(len(self.public(u['aid'])), 30)
        s, sitemap, _ = self.site(u, '/sitemap.xml')
        self.assertEqual(sitemap.count('/propiedad/'), 30)
        s, llms, _ = self.site(u, '/llms.txt')
        self.assertEqual(llms.count('/propiedad/'), 30)
        self.assertEqual(len(ids), 30)

    def test_creating_past_the_old_limit_is_refused_off_and_allowed_for_ia_on(self):
        u = self.agency('ia')
        self.many(u['aid'], 25)
        form = {'title': 'Departamento número veintiséis', 'operation': 'venta', 'property_type': 'departamento', 'status': 'activa',
                'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000'}
        s, page, _ = self.panel(u, '/propiedades/nueva', form)
        self.assertEqual(s, 403)
        self.assertIn('Llegaste al límite de tu plan (25 propiedades)', page)
        self.v2()
        s, page, _ = self.panel(u, '/propiedades/nueva', form)
        self.assertEqual(s, 303, page[:300])
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', u['aid'])[0], 26)

    def test_gratis_cap_message_and_reopen_use_the_new_number(self):
        u = self.agency('gratis')
        self.v2()
        self.many(u['aid'], 3)
        form = {'title': 'Departamento número cuatro', 'operation': 'venta', 'property_type': 'departamento', 'status': 'activa',
                'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000'}
        s, page, _ = self.panel(u, '/propiedades/nueva', form)
        self.assertEqual(s, 403)
        self.assertIn('Llegaste al límite de tu plan (3 propiedades)', page)
        sold = self.listing(u['aid'], 'vendida', status='vendida')
        form.update(title='Departamento vendido de antes')
        s, page, _ = self.panel(u, '/propiedades/%d' % sold, form)
        self.assertEqual(s, 400)
        self.assertIn('tu plan permite 3 propiedades y ya tienes 3 abiertas', page)

    def test_downgrade_from_unlimited(self):
        u = self.agency('ia')
        self.v2()
        ids = self.many(u['aid'], 30)
        # the plan page: no "X de 1000000", no 1000000 anywhere
        s, page, _ = self.panel(u, '/plan')
        self.assertIn('Usas 30 propiedades. Tu plan no tiene límite.', page)
        self.assertNotIn('1000000', page)
        self.assertNotIn(' de 1000000', page)
        self.assertNotIn('solo las', page)                               # no "your site shows only" warning
        # a plan switch that does not fit is refused, nothing changes
        s, page, _ = self.panel(u, '/plan/pro', {})
        self.assertEqual(s, 400)
        self.assertIn('Tienes 30 propiedades; este plan permite 25. Marca algunas como vendidas primero.', page)
        self.assertEqual(self.web.one('SELECT plan FROM agencies WHERE id=?', u['aid'])[0], 'ia')
        # six sold: 24 open fits Pro (25)
        for lid in ids[:6]:
            self.sql("UPDATE listings SET status='vendida' WHERE id=?", lid)
        s, page, _ = self.panel(u, '/plan/pro', {})
        self.assertEqual(s, 200, page[:300])
        self.assertEqual(self.web.one('SELECT plan FROM agencies WHERE id=?', u['aid'])[0], 'pro')
        self.assertEqual(len(self.public(u['aid'])), 24)
        # the subscription ends (what the billing webhook does): back to Gratis, 3 public, all 30 rows still there
        for lid in ids[:6]:
            self.sql("UPDATE listings SET status='activa' WHERE id=?", lid)
        self.sql("UPDATE agencies SET plan='gratis' WHERE id=?", u['aid'])
        self.assertEqual(len(self.public(u['aid'])), 3)
        self.assertEqual(cards(self.site(u)[1]), 3)
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', u['aid'])[0], 30)
        s, page, _ = self.panel(u, '/plan')
        self.assertIn('Usas 30 de 3 propiedades.', page)
        self.assertIn('Tu sitio muestra solo las 3 más recientes.', page)
        # and it all comes back on upgrade
        self.sql("UPDATE agencies SET plan='ia' WHERE id=?", u['aid'])
        self.assertEqual(len(self.public(u['aid'])), 30)

    def test_switching_the_flag_off_again_does_not_delete_a_thing(self):
        u = self.agency('pro')
        self.v2()
        self.many(u['aid'], 12)
        self.assertEqual(len(self.public(u['aid'])), 12)
        self.v2(False)
        self.assertEqual(len(self.public(u['aid'])), 5)
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', u['aid'])[0], 12)

    def test_the_importer_counts_slots_with_the_switch(self):
        u = self.agency('ia')
        self.many(u['aid'], 26)
        csv_text = 'titulo,precio,colonia,municipio,estado\n' + '\n'.join(
            'Departamento importado %d en la Roma,%d,Roma Norte,Cuauhtémoc,CDMX' % (i, 3000000 + i) for i in range(3))
        con = db.connect()
        try:
            off = importer.preview(con, u['aid'], csv_text)
            self.assertEqual([r['action'] for r in off['rows']], ['omitir'] * 3)
            self.v2()
            on = importer.preview(con, u['aid'], csv_text)
            self.assertEqual([r['action'] for r in on['rows']], ['crear'] * 3)
            self.assertEqual(importer._plan_limit(con, u['aid'])[0], db.UNLIMITED)
        finally:
            con.close()


# ---------------------------------------------------------------------------------------------------------- what people read
class Displays(Base):
    def plan_page(self, plan, n=0):
        u = self.agency(plan)
        if n:
            self.many(u['aid'], n)
        return self.panel(u, '/plan')[1]

    @staticmethod
    def plan_cards(page):
        return re.split(r'<div class="card plan', page[page.index('class="grid2 wide plans"'):])[1:4]

    def test_plan_page_off_is_todays_numbers(self):
        page = self.plan_page('gratis')
        self.assertIn('Usas 0 de 1 propiedad.', page)
        gratis, pro, ia = self.plan_cards(page)
        self.assertIn('<li>1 propiedad</li>', gratis)
        self.assertIn('<li>5 propiedades</li>', pro)
        self.assertIn('<li>25 propiedades</li>', ia)
        self.assertIn('Bolsa 50/50 con otros asesores', pro)                # the Bolsa is a Pro line...
        self.assertNotIn('Bolsa 50/50', gratis)                              # ...and not a Gratis one
        self.assertIn('$499 MXN', page)
        self.assertIn('$999 MXN', page)
        for txt in ('sin límite', '3 propiedades', 'Sin límite'):
            self.assertNotIn(txt, page)

    def test_plan_page_on_shows_the_new_numbers(self):
        self.v2()
        page = self.plan_page('gratis')
        self.assertIn('Usas 0 de 3 propiedades.', page)
        gratis, pro, ia = self.plan_cards(page)
        self.assertIn('<li>3 propiedades</li>', gratis)
        self.assertIn('Bolsa 50/50 con otros asesores', gratis)
        self.assertIn('<li>25 propiedades</li>', pro)
        self.assertNotIn('Bolsa 50/50', pro)
        self.assertIn('<li>Propiedades sin límite</li>', ia)
        for old in ('<li>1 propiedad</li>', '<li>5 propiedades</li>'):
            self.assertNotIn(old, page)
        self.assertNotIn('<li>25 propiedades</li>', ia)
        self.assertNotIn('1000000', page)
        self.assertIn('$499 MXN', page)
        self.assertIn('$999 MXN', page)

    def test_plan_page_on_for_each_plan_reads_right(self):
        self.v2()
        self.assertIn('Usas 2 de 25 propiedades.', self.plan_page('pro', 2))
        ia = self.plan_page('ia', 1)
        self.assertIn('Usas 1 propiedad. Tu plan no tiene límite.', ia)
        self.assertNotIn(' de ', re.search(r'<p class="muted">Usas[^<]*</p>', ia).group(0))

    def test_dashboard_x_of_y(self):
        u = self.agency('pro')
        self.many(u['aid'], 2)
        s, home, _ = self.panel(u, '/')
        self.assertIn('<b>2/5</b><small>Usadas en plan pro · cambiar</small>', home)
        self.v2()
        self.assertIn('<b>2/25</b><small>Usadas en plan pro · cambiar</small>', self.panel(u, '/')[1])
        self.sql("UPDATE agencies SET plan='ia' WHERE id=?", u['aid'])
        s, home, _ = self.panel(u, '/')
        self.assertIn('<b>2</b><small>Usadas, sin límite, en plan ia · cambiar</small>', home)
        self.assertNotIn('1000000', home)
        self.v2(False)
        self.assertIn('<b>2/25</b><small>Usadas en plan ia · cambiar</small>', self.panel(u, '/')[1])

    def test_public_plans_page_landing_and_faq_follow_the_switch(self):
        s, planes, _ = self.web.req('/planes')
        s, land, _ = self.web.req('/')
        for page in (planes, land):
            self.assertIn('<li><svg><use href="#i-ok"/></svg>1 propiedad</li>', page)
            self.assertIn('<li><svg><use href="#i-ok"/></svg>5 propiedades</li>', page)
            self.assertIn('<li><svg><use href="#i-ok"/></svg>25 propiedades</li>', page)
        self.assertIn('y 1 propiedad. No pedimos tarjeta', land)
        self.assertIn('Gratis con 1 propiedad, Pro $499 MXN', planes)
        self.v2()
        s, planes, _ = self.web.req('/planes')
        s, land, _ = self.web.req('/')
        for page in (planes, land):
            self.assertIn('<li><svg><use href="#i-ok"/></svg>3 propiedades</li>', page)
            self.assertIn('<li><svg><use href="#i-ok"/></svg>25 propiedades</li>', page)
            self.assertIn('<li><svg><use href="#i-ok"/></svg>Propiedades sin límite</li>', page)
            self.assertNotIn('>1 propiedad</li>', page)
            self.assertNotIn('>5 propiedades</li>', page)
            self.assertNotIn('1000000', page)
        self.assertIn('Gratis con 3 propiedades, Pro $499 MXN', planes)
        self.assertIn('y 3 propiedades. No pedimos tarjeta', land)                  # FAQ text and its JSON-LD copy
        self.assertEqual(land.count('y 3 propiedades. No pedimos tarjeta'), 2)
        self.assertNotIn('y 1 propiedad. No pedimos tarjeta', land)
        self.assertIn('$499', planes)
        self.assertIn('$999', planes)

    def test_upsell_pages_say_the_right_numbers(self):
        u = self.agency('gratis')
        s, page, _ = self.panel(u, '/bolsa')
        self.assertIn('Bolsa 50/50 y estadísticas completas, con 5 propiedades y tu propio dominio.', page)
        self.assertEqual(self.panel(u, '/que-publicar')[1].count('con 25 propiedades.'), 1)
        self.v2()
        s, page, _ = self.panel(u, '/estadisticas')
        self.assertIn('importar desde Excel y estadísticas completas, con 25 propiedades y tu propio dominio.', page)
        self.assertNotIn('Bolsa', page.split('<h1>')[1].split('</div>')[0])
        s, page, _ = self.panel(u, '/que-publicar')
        self.assertIn('qué publicar cada semana, con propiedades sin límite.', page)

    def test_academia_lesson_about_the_bolsa(self):
        u = self.agency('gratis')
        s, page, _ = self.panel(u, '/academia/compartir-en-la-bolsa')
        self.assertIn('Es una herramienta del plan Pro.', page)
        self.v2()
        s, page, _ = self.panel(u, '/academia/compartir-en-la-bolsa')
        self.assertIn('Viene incluida en todos los planes.', page)
        self.assertNotIn('herramienta del plan Pro', page)

    def test_listing_editor_checkbox_hint(self):
        u = self.agency('gratis')
        lid = self.listing(u['aid'], 'ed')
        self.assertIn('(plan Pro)', self.panel(u, '/propiedades/%d' % lid)[1])
        self.v2()
        self.assertNotIn('(plan Pro)', self.panel(u, '/propiedades/%d' % lid)[1])

    def test_no_competitor_names_in_anything_new(self):
        import guard_terms
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for path in ('tests/test_plans_v2.py', 'llave/db.py', 'llave/academia.py', 'llave/web/panel.py', 'llave/web/site.py', 'llave/web/landing.py',
                     'llave/web/common.py', 'supabase/migrations/0010_bolsa_section.sql', 'docs/DECISIONS.md', 'deploy/app.env.example'):
            with open(os.path.join(root, path), encoding='utf-8') as f:
                self.assertIsNone(guard_terms.RIVALS_AND_PORTALS.search(f.read()), path)


# ---------------------------------------------------------------------------------------------------------- the Bolsa gate
class BolsaGate(Base):
    def test_off_the_bolsa_is_pro_and_ia_only(self):
        gratis, pro = self.agency('gratis'), self.agency('pro')
        owner = self.agency('pro')
        lid = self.listing(owner['aid'], 'o1', share=True)
        s, page, _ = self.panel(gratis, '/bolsa')
        self.assertIn('Bolsa 50/50', page)
        self.assertIn('Ver el plan Pro', page)                           # the upsell page
        self.assertNotIn('Departamento o1', page)
        s, _, _ = self.panel(gratis, '/bolsa/%d/compartir' % lid, {})
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM shares')[0], 0)
        s, page, _ = self.panel(pro, '/bolsa')
        self.assertIn('Departamento o1', page)
        self.assertNotIn('Ver el plan Pro', page)
        # the listing checkbox is ignored on Gratis, honoured on Pro
        form = {'title': 'Departamento para compartir', 'operation': 'venta', 'property_type': 'departamento', 'status': 'activa',
                'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000', 'share_in_bolsa': '1'}
        for u, want in ((gratis, 0), (pro, 1)):
            self.panel(u, '/propiedades/nueva', form)
            self.assertEqual(self.web.one('SELECT share_in_bolsa FROM listings WHERE agency_id=?', u['aid'])[0], want)

    def test_on_every_plan_can_open_the_bolsa_share_and_be_shared(self):
        self.v2()
        owner, gratis = self.agency('gratis'), self.agency('gratis')
        form = {'title': 'Departamento para compartir', 'operation': 'venta', 'property_type': 'departamento', 'status': 'activa',
                'colonia': 'Roma Norte', 'municipio': 'Cuauhtémoc', 'estado': 'Ciudad de México', 'price': '3500000', 'share_in_bolsa': '1'}
        s, _, _ = self.panel(owner, '/propiedades/nueva', form)
        self.assertEqual(s, 303)
        lid = self.web.one('SELECT id FROM listings WHERE agency_id=?', owner['aid'])[0]
        self.assertEqual(self.web.one('SELECT share_in_bolsa FROM listings WHERE id=?', lid)[0], 1)   # a Gratis agent can open it to the Bolsa
        s, page, _ = self.panel(gratis, '/bolsa')
        self.assertIn('Departamento para compartir', page)
        self.assertNotIn('Ver el plan Pro', page)
        self.panel(gratis, '/bolsa/%d/compartir' % lid, {})
        row = self.web.one("SELECT sharing_agency_id, split_pct, status FROM shares WHERE listing_id=?", lid)
        self.assertEqual((row[0], row[1], row[2]), (gratis['aid'], 50, 'activa'))
        self.assertIn(lid, self.public(gratis['aid']))

    def test_on_the_rest_of_pro_stays_pro(self):
        self.v2()
        gratis = self.agency('gratis')
        for path in ('/estadisticas', '/propiedades/importar'):
            s, page, _ = self.panel(gratis, path)
            self.assertIn('Ver el plan Pro', page, path)
        s, page, _ = self.panel(gratis, '/que-publicar')
        self.assertIn('Ver el plan Pro + IA', page)
        lid = self.listing(gratis['aid'], 'g1')
        self.assertEqual(self.site(gratis, '/propiedad/depa-g1/tarjeta-post.jpg')[0], 200)   # the plain post card is the growth loop: Gratis gets it under V2
        self.assertEqual(self.site(gratis, '/propiedad/depa-g1/tarjeta-historia.jpg')[0], 404)   # the story card is still a Pro tool
        self.assertEqual(self.site(gratis, '/propiedad/depa-g1/ficha')[0], 404)
        self.assertEqual(self.site(gratis, '/propiedad/depa-g1')[0], 200)
        self.assertEqual(lid, self.public(gratis['aid'])[0])


# ---------------------------------------------------------------------------------------------------------- Mi sitio: the opt-in
class OptIn(Base):
    def test_default_off_and_only_offered_when_v2_is_on(self):
        u = self.agency('gratis')
        page = self.panel(u, '/sitio')[1]
        self.assertNotIn('bolsa_section', page)
        self.assertNotIn('Más propiedades de la Bolsa', page)
        self.v2()
        page = self.panel(u, '/sitio')[1]
        self.assertIn('Más propiedades de la Bolsa', page)
        self.assertIn('name="bolsa_section" value="1">', page)             # present and NOT checked
        self.assertNotIn('name="bolsa_section" value="1" checked', page)
        self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 0)

    def test_the_switch_saves_both_ways_and_is_offered_to_every_plan(self):
        self.v2()
        for plan in ('gratis', 'pro', 'ia'):
            u = self.agency(plan)
            self.assertIn('Más propiedades de la Bolsa', self.panel(u, '/sitio')[1], plan)
            page = self.save_site(u, bolsa_seen='1', bolsa_section='1')
            self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 1, plan)
            self.assertIn('name="bolsa_section" value="1" checked>', page)
            self.save_site(u, bolsa_seen='1')                                 # unchecked box sends nothing
            self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 0, plan)

    def test_saving_without_the_switch_in_the_form_leaves_it_alone(self):
        self.v2()
        u = self.agency('pro')
        self.section_on(u)
        self.save_site(u)                                                     # a form that did not carry the switch
        self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 1)

    def test_a_forged_post_with_v2_off_changes_nothing(self):
        u = self.agency('pro')
        self.save_site(u, bolsa_seen='1', bolsa_section='1')
        self.assertEqual(self.web.one('SELECT bolsa_section FROM agencies WHERE id=?', u['aid'])[0], 0)

    def test_panel_pages_are_todays_with_the_switch_off(self):
        u = self.agency('pro')
        for path in ('/sitio', '/bolsa', '/plan', '/'):
            before = self.panel(u, path)[1]
            self.section_on(u)
            after = self.panel(u, path)[1]
            self.section_on(u, False)
            self.assertEqual(re.sub(r'name="csrf" value="[0-9a-f]+"', '', before), re.sub(r'name="csrf" value="[0-9a-f]+"', '', after), path)
            for txt in ('Más propiedades de la Bolsa', 'Sale en tu sitio', 'sin límite', 'bolsa_section', 'puedes mostrar propiedades de la Bolsa'):
                self.assertNotIn(txt, before, (path, txt))


# ---------------------------------------------------------------------------------------------------------- the site section
class PoolSection(Base):
    def world(self, owner_plan='pro', sharer_plan='gratis', on=True):
        """owner (listings open to the Bolsa, a 37/63 split, a private commission, an agent with their own contact) and a sharer
        whose site has the section switched on. LLAVE_PLANS_V2 is on."""
        self.v2()
        self.owner, self.sharer = self.agency(owner_plan, OWNER_WA), self.agency(sharer_plan, SHARER_WA)
        self.sql('UPDATE agencies SET email=? WHERE id=?', OWNER_EMAIL, self.owner['aid'])
        self.sql('UPDATE users SET name=?, whatsapp=? WHERE id=?', OWNER_AGENT, OWNER_AGENT_WA, self.owner['uid'])
        self.sql('UPDATE users SET whatsapp=? WHERE id=?', SHARER_WA, self.sharer['uid'])
        self.o1 = self.listing(self.owner['aid'], 'o1', share=True, split=37, commission=6.35, agent=self.owner['uid'], age=1)
        self.section_on(self.sharer, on)
        self.mine = self.listing(self.sharer['aid'], 'mia', age=5)
        return self.o1

    def test_only_bolsa_listings_that_are_public(self):
        self.world()
        o2 = self.listing(self.owner['aid'], 'o2', share=False, age=2)                         # not opened to the Bolsa
        o3 = self.listing(self.owner['aid'], 'o3', share=True, status='borrador', age=3)
        o4 = self.listing(self.owner['aid'], 'o4', share=True, status='pausada', age=4)
        o5 = self.listing(self.owner['aid'], 'o5', share=True, status='vendida', age=5)
        o6 = self.listing(self.owner['aid'], 'o6', share=True, status='apartada', age=6)       # apartada is public
        self.assertEqual(self.pool(self.sharer['aid']), [self.o1, o6])
        s, home, _ = self.site(self.sharer)
        sec = section(home)
        self.assertIn('Más propiedades de la Bolsa', sec)
        self.assertEqual(sorted(slugs_in(sec)), ['depa-o1', 'depa-o6'])
        for slug in ('depa-o2', 'depa-o3', 'depa-o4', 'depa-o5'):
            self.assertNotIn(slug, home)
        self.assertEqual((o2 < o3 < o4 < o5 < o6), True)
        self.assertEqual(cards(sec), 2)
        self.assertIn('class="lc"', home)                                                       # own listing still in the main grid
        self.assertIn('depa-mia', home.replace(sec, ''))
        self.assertNotIn(self.mine, self.pool(self.sharer['aid']))                             # never your own

    def test_a_listing_the_owners_plan_hides_is_not_offered(self):
        self.world(owner_plan='gratis')                                                        # V2 Gratis shows 3
        newer = [self.listing(self.owner['aid'], 'n%d' % i, share=True, age=0) for i in range(3)]
        self.assertEqual(sorted(self.pool(self.sharer['aid'])), sorted(newer))                 # o1 (older) is over the owner's cap: hidden
        self.assertNotIn(self.o1, self.pool(self.sharer['aid']))
        self.sql("UPDATE agencies SET plan='ia' WHERE id=?", self.owner['aid'])
        self.assertIn(self.o1, self.pool(self.sharer['aid']))                                  # and back on upgrade
        self.sql("UPDATE agencies SET plan='gratis' WHERE id=?", self.owner['aid'])             # a downgrade takes them off the pool again
        self.assertNotIn(self.o1, self.pool(self.sharer['aid']))
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM listings WHERE agency_id=?', self.owner['aid'])[0], 4)

    def test_cap_is_twelve_newest_first(self):
        self.world()
        ids = [self.listing(self.owner['aid'], 'p%02d' % i, share=True, age=10 + i) for i in range(15)]
        self.sql("UPDATE agencies SET plan='ia' WHERE id=?", self.owner['aid'])
        got = self.pool(self.sharer['aid'])
        self.assertEqual(len(got), db.POOL_MAX)
        self.assertEqual(db.POOL_MAX, 12)
        self.assertEqual(got, [self.o1] + ids[:11])                                            # o1 is the newest, then p00..p10
        s, home, _ = self.site(self.sharer)
        self.assertEqual(cards(section(home)), 12)
        self.assertEqual(cards(home), 13)                                                      # + the agency's own one

    def test_what_is_already_shown_or_removed_is_not_repeated(self):
        self.world()
        o2 = self.listing(self.owner['aid'], 'o2', share=True, age=2)
        o3 = self.listing(self.owner['aid'], 'o3', share=True, age=3)
        self.panel(self.sharer, '/bolsa/%d/compartir' % o2, {})                                # shown on purpose: main grid, not the section
        self.panel(self.sharer, '/bolsa/%d/compartir' % o3, {})
        self.panel(self.sharer, '/bolsa/%d/retirar' % o3, {})                                  # removed on purpose: stays removed
        self.assertEqual(self.pool(self.sharer['aid']), [self.o1])
        home = self.site(self.sharer)[1]
        self.assertEqual(slugs_in(section(home)), ['depa-o1'])
        self.assertEqual(home.count('href="/propiedad/depa-o2"'), 1)
        self.assertNotIn('depa-o3', home)

    def test_slug_collisions_never_hide_the_agencys_own_page(self):
        self.world()
        self.listing(self.sharer['aid'], 'clash', slug='depa-o1', age=8)                       # same slug as the owner's listing
        self.assertEqual(self.pool(self.sharer['aid']), [])
        s, page, _ = self.site(self.sharer, '/propiedad/depa-o1')
        self.assertIn('Departamento clash', page)                                              # the agency's own listing answers
        other = self.agency('pro', OWNER_WA)                                                   # two other owners with one slug: the newer wins
        newer = self.listing(self.owner['aid'], 'tw1', share=True, slug='depa-twin', age=2)
        self.listing(other['aid'], 'tw2', share=True, slug='depa-twin', age=3)
        self.assertEqual(self.pool(self.sharer['aid']), [newer])
        s, page, _ = self.site(self.sharer, '/propiedad/depa-twin')
        self.assertIn('Departamento tw1', page)
        self.assertNotIn('Departamento tw2', page)

    def test_off_states_show_nothing_and_serve_nothing(self):
        self.world()
        slug = 'depa-o1'
        self.assertIn(slug, self.site(self.sharer)[1])
        self.assertEqual(self.site(self.sharer, '/propiedad/' + slug)[0], 200)
        self.section_on(self.sharer, False)                                                    # the agency's switch
        self.assertEqual((section(self.site(self.sharer)[1]), self.site(self.sharer, '/propiedad/' + slug)[0]), ('', 404))
        self.section_on(self.sharer)
        self.v2(False)                                                                          # the server switch
        home = self.site(self.sharer)[1]
        self.assertEqual((section(home), 'Más propiedades de la Bolsa' in home, self.site(self.sharer, '/propiedad/' + slug)[0]), ('', False, 404))
        self.assertEqual(self.pool(self.sharer['aid']), [])
        self.v2()
        self.assertEqual(self.site(self.sharer, '/propiedad/' + slug)[0], 200)
        with mock.patch.dict(db.PLAN_FEATURES_V2, {'bolsa': ('pro', 'ia')}):                   # a plan without the Bolsa
            self.assertEqual(self.pool(self.sharer['aid']), [])
            self.assertEqual(section(self.site(self.sharer)[1]), '')

    def test_each_card_opens_the_listing_on_the_sharers_site_with_the_sharers_contact(self):
        self.world()
        home = self.site(self.sharer)[1]
        self.assertIn('<a class="lc" href="/propiedad/depa-o1">', section(home))               # relative: this site
        s, page, _ = self.site(self.sharer, '/propiedad/depa-o1')
        self.assertEqual(s, 200)
        self.assertIn('Departamento o1 en Roma Norte', page)
        self.assertIn('wa.me/525599887766', page)                                              # the sharer's WhatsApp
        self.assertIn('Casa Rosa', page)
        self.assertIn('<form method="post" action="/contacto">', page)
        self.assertIn('name="listing" value="%d"' % self.o1, page)

    def test_canonical_is_the_owners_page_and_the_sharers_sitemap_leaves_it_out(self):
        self.world()
        con = db.connect()
        owner_url = db.canonical(con, self.o1)['url']
        con.close()
        self.assertIn(self.owner['slug'], owner_url)
        s, page, _ = self.site(self.sharer, '/propiedad/depa-o1')
        self.assertIn('<link rel="canonical" href="%s">' % owner_url, page)
        self.assertIn('<meta property="og:url" content="%s">' % owner_url, page)
        self.assertNotIn('%s/propiedad/depa-o1' % db.origin(self.sharer['slug']), page.split('<body')[0])  # the head never points at the sharer's copy
        # the sharer's own page keeps its own canonical
        s, mine, _ = self.site(self.sharer, '/propiedad/depa-mia')
        self.assertIn('<link rel="canonical" href="%s/propiedad/depa-mia">' % db.origin(self.sharer['slug']), mine)
        # sitemap, llms.txt and every feed: own listings only
        s, sitemap, _ = self.site(self.sharer, '/sitemap.xml')
        self.assertIn('/propiedad/depa-mia', sitemap)
        self.assertNotIn('depa-o1', sitemap)
        s, llms, _ = self.site(self.sharer, '/llms.txt')
        self.assertIn('depa-mia', llms)
        self.assertNotIn('depa-o1', llms)
        for key in ('llave_open.xml', 'llave_open.json', 'trovit.xml', 'mitula.xml'):
            s, feed, _ = self.site(self.sharer, '/feeds/' + key)
            self.assertNotIn('Departamento o1', feed, key)
        # the owner's sitemap has it
        s, osm, _ = self.site(self.owner, '/sitemap.xml')
        self.assertIn('/propiedad/depa-o1', osm)
        # the Instagram card and sheet are not served for a listing that is not yours
        self.assertEqual(self.site(self.sharer, '/propiedad/depa-o1/tarjeta-post.jpg')[0], 404)

    def test_the_commission_split_is_never_on_a_public_page(self):
        self.world()
        pages = [self.site(self.sharer)[1], self.site(self.sharer, '/propiedad/depa-o1')[1], self.site(self.sharer, '/sitemap.xml')[1],
                 self.site(self.sharer, '/llms.txt')[1], self.site(self.sharer, '/gracias')[1]]
        for page in pages:
            low = re.sub(r'<(style|script)\b.*?</\1>', '', page, flags=re.S).lower()
            for txt in ('comisi', 'reparto', 'split', 'commission', '37%', '63%', '37/63', '63/37', '6.35', '6,35', 'share_split'):
                self.assertNotIn(txt, low, txt)
        # ... but the panel shows it, to the sharer: they receive 63
        s, page, _ = self.panel(self.sharer, '/bolsa')
        self.assertIn('Comisión compartida: tú recibes 63%', page)
        self.assertIn('Sale en tu sitio', page)
        self.assertIn('Departamento o1', page)

    def test_no_owner_contact_data_leaks(self):
        self.world()
        pages = [self.site(self.sharer)[1], self.site(self.sharer, '/propiedad/depa-o1')[1]]
        for page in pages:
            for secret in ('5511223344', '5500001111', OWNER_EMAIL, self.owner['email'], 'owner-test.example', 'Zacarías', 'Dueño'):
                self.assertNotIn(secret, page, secret)
            self.assertIn('5599887766', page)
        # the same page of the owner's own site does carry the owner's contact (the test would pass for the wrong reason otherwise)
        own = self.site(self.owner, '/propiedad/depa-o1')[1]
        self.assertIn('5511223344', own)
        self.assertIn('Zacarías', own)

    def test_a_lead_follows_the_existing_bolsa_path(self):
        self.world()
        before_shares = self.web.one('SELECT COUNT(*) FROM shares')[0]
        s, _, h = self.site(self.sharer, '/contacto', {'listing': str(self.o1), 'name': 'Ana Cliente', 'phone': '55 4444 3333',
                                                        'message': 'Me interesa', 'consent': '1'})
        self.assertEqual(s, 303)
        lead = self.web.q('SELECT * FROM leads')[0]
        self.assertEqual((lead['agency_id'], lead['owner_agency_id'], lead['listing_id'], lead['source']),
                         (self.sharer['aid'], self.owner['aid'], self.o1, 'bolsa'))
        self.assertEqual(self.web.one('SELECT COUNT(*) FROM shares')[0], before_shares)         # no side effect: nothing was shared on the way
        # both agencies get the alert, each with the split from its own side: the owner keeps 37, the sharer gets 63
        alerts = [json.loads(r['payload']) for r in self.web.q("SELECT payload FROM outbox WHERE kind='ghl.agent_alert' AND ref=?", 'lead:%d' % lead['id'])]
        self.assertEqual(sorted(x['role'] for x in alerts), ['owner', 'receiving'])
        self.assertTrue(all('Bolsa 63/37.' in x['body']['text'] for x in alerts), alerts)
        con = db.connect()
        try:
            mails = {m['to']: m['text'] for m in agent_mail.new_lead_messages(con, lead['id'])}
        finally:
            con.close()
        self.assertEqual(len(mails), 2)
        sharer_mail = [t for to, t in mails.items() if to == self.sharer['email']][0]
        owner_mail = [t for to, t in mails.items() if to == self.owner['email']][0]
        self.assertIn('Reparto 63/37', sharer_mail)
        self.assertIn('Reparto 37/63', owner_mail)
        # the panel's client list carries it as a Bolsa lead
        s, page, _ = self.panel(self.sharer, '/clientes')
        self.assertIn('Ana Cliente', page)

    def test_a_listing_that_is_not_on_the_page_is_not_attached_to_a_lead(self):
        self.world()
        hidden = self.listing(self.owner['aid'], 'priv', share=False, age=3)
        self.site(self.sharer, '/contacto', {'listing': str(hidden), 'name': 'Beto', 'phone': '55 4444 3334', 'consent': '1'})
        self.section_on(self.sharer, False)
        self.site(self.sharer, '/contacto', {'listing': str(self.o1), 'name': 'Carla', 'phone': '55 4444 3335', 'consent': '1'})
        rows = self.web.q('SELECT name, listing_id, source, owner_agency_id FROM leads ORDER BY id')
        self.assertEqual([(r['name'], r['listing_id'], r['source']) for r in rows], [('Beto', None, 'sitio'), ('Carla', None, 'sitio')])

    def test_lia_knows_the_listing_on_screen(self):
        self.world()
        con = db.connect()
        try:
            agency = con.execute('SELECT * FROM agencies WHERE id=?', (self.sharer['aid'],)).fetchone()
            self.assertEqual(lia._canon_for(con, agency, self.o1)['id'], self.o1)
            self.section_on(self.sharer, False)
            agency = con.execute('SELECT * FROM agencies WHERE id=?', (self.sharer['aid'],)).fetchone()
            self.assertIsNone(lia._canon_for(con, agency, self.o1))
        finally:
            con.close()

    def test_looks_the_same_in_all_four_designs(self):
        self.world()
        for design in ('loteria', 'residencia', 'ciudad', 'costa', 'no-existe'):
            self.sql('UPDATE agencies SET design=? WHERE id=?', design, self.sharer['aid'])
            home = self.site(self.sharer)[1]
            sec = section(home)
            self.assertIn('<h2>Más propiedades de la Bolsa</h2>', sec, design)
            self.assertIn('<div class="cards">', sec, design)                                     # the same grid class as "Propiedades"
            self.assertEqual(cards(sec), 1, design)
            self.assertEqual(home.count('<h1>'), 1, design)
            # it sits between the agency's own grid and the alert form, so the page order is unchanged
            self.assertLess(home.index('<h2>Propiedades</h2>'), home.index('id="bolsa"'), design)
            self.assertLess(home.index('id="bolsa"'), home.index('id="alerta"'), design)
            self.assertNotIn('style="width', sec)                                                  # nothing that could push past 375 px

    def test_switch_off_site_pages_are_byte_identical(self):
        self.world(on=True)
        self.v2(False)
        a_on = self.site(self.sharer)[1], self.site(self.sharer, '/propiedad/depa-mia')[1], self.site(self.sharer, '/sitemap.xml')[1]
        self.section_on(self.sharer, False)
        a_off = self.site(self.sharer)[1], self.site(self.sharer, '/propiedad/depa-mia')[1], self.site(self.sharer, '/sitemap.xml')[1]
        self.assertEqual(a_on, a_off)
        self.assertNotIn('id="bolsa"', a_on[0])


if __name__ == '__main__':
    unittest.main()
