"""The share cards: sizes, fonts (never PIL's default), no text overflow, the ¡Vendida! / ¡Rentada! cards, plan gate, cache."""
import io
import os
import re
import shutil
import tempfile
import unittest

from PIL import Image, ImageFont

from llave import cards, db, operaciones, photos
from tests.test_photos import make_jpeg

BUNDLED = cards.BUNDLED_FONTS
ENV_KEYS = ('LLAVE_CARD_FONT', 'LLAVE_CARD_FONTS_DIR', 'LLAVE_PLANS_V2')


class CardsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = (db.MEDIA_DIR, cards.SYSTEM_FONTS)
        self._env = {k: os.environ.pop(k, None) for k in ENV_KEYS}
        db.MEDIA_DIR = os.path.join(self.tmp, 'media')
        cards.SYSTEM_FONTS = []  # as on the server: no system fonts at all
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(slug,name,whatsapp,accent) VALUES('a','VIVE Polanco','+525578358858','#0b2a4a')")
        self.con.execute("INSERT INTO users(agency_id,name,email,whatsapp,password_hash,role) VALUES(1,'Rosa Pérez','r@ejemplo.test','+525511223344','x','owner')")
        self.con.execute("INSERT INTO listings(agency_id,agent_id,ref,slug,title,operation,price_cents,currency,price_date,"
                         "m2_built,bedrooms,bathrooms,parking,colonia,municipio,updated_at) VALUES "
                         "(1,1,'R1','l1','Departamento con vista al parque','venta',450000000,'MXN','2026-10-17',"
                         "120,2,2,1,'Polanco','Miguel Hidalgo','2026-10-17 10:00:00')")
        self.con.execute("INSERT INTO listings(agency_id,ref,slug,title,operation,price_cents,currency,updated_at) "
                         "VALUES (1,'R2','l2','Penthouse','renta',69900000,'USD','2026-10-17 10:00:00')")
        self.con.commit()

    def tearDown(self):
        db.MEDIA_DIR, cards.SYSTEM_FONTS = self._old
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def close_listing(self, lid, status='vendida', **extra):
        sets = ', '.join('%s=?' % k for k in extra)
        self.con.execute("UPDATE listings SET status=?%s WHERE id=?" % ((', ' + sets) if sets else ''), [status] + list(extra.values()) + [lid])
        self.con.commit()


class SizesAndTexts(CardsBase):
    def test_every_size_renders_jpeg_without_metadata(self):
        for kind, size in (('post', (1080, 1350)), ('story', (1080, 1920)), ('enlace', (1200, 630))):
            im = Image.open(io.BytesIO(cards.render(self.con, 1, kind)))
            self.assertEqual((im.format, im.size), ('JPEG', size), kind)
            self.assertEqual(len(im.getexif()), 0)
            self.assertNotIn('icc_profile', im.info)
        self.close_listing(2, 'rentada')
        for kind, size in (('cierre_post', (1080, 1350)), ('cierre_story', (1080, 1920))):
            self.assertEqual(Image.open(io.BytesIO(cards.render(self.con, 2, kind))).size, size)

    def test_with_photo_and_every_photo_shape(self):
        for size in ((1800, 1200), (900, 1600), (1600, 700), (1000, 1000)):
            self.con.execute('DELETE FROM photos WHERE listing_id=1')
            photos.ingest(self.con, 1, make_jpeg(size, seed=size[0]))
            for kind in ('post', 'story', 'enlace'):
                self.assertEqual(Image.open(io.BytesIO(cards.render(self.con, 1, kind))).size, (cards.KINDS[kind]['w'], cards.KINDS[kind]['h']))

    def test_texts_usd_and_mxn_and_the_agents_own_phone(self):
        _, t1 = cards.render(self.con, 1, return_texts=True)
        self.assertIn('$4,500,000 MXN', t1)
        self.assertIn('EN VENTA', t1)
        self.assertIn('Precio al 17 oct 2026', t1)
        self.assertIn('55 1122 3344', t1)       # the listing agent's own WhatsApp, not the agency's
        self.assertNotIn('55 7835 8858', t1)
        self.assertIn('Rosa Pérez', t1)
        self.assertIn('VIVE Polanco', t1)
        _, t2 = cards.render(self.con, 2, 'story', return_texts=True)
        self.assertIn('US$699,000', t2)
        self.assertIn('EN RENTA', t2)
        self.assertIn('55 7835 8858', t2)       # no agent on this listing: the agency's number
        for t in (t1, t2):
            self.assertEqual([x for x in t if re.search(r'\d{2} \d{4} \d{4}', x)].__len__(), 1)  # exactly one phone on a card

    def test_attribution_line_on_every_kind(self):
        self.close_listing(2, 'vendida')
        for lid, kind in ((1, 'post'), (1, 'story'), (1, 'enlace'), (2, 'cierre_post'), (2, 'cierre_story')):
            self.assertIn('Hecho con Ficha Única · fichaunica.mx', cards.render(self.con, lid, kind, return_texts=True)[1], kind)

    def test_text_is_cleaned(self):
        self.con.execute('UPDATE listings SET title=? WHERE id=1', ('🏠✨ Depa increíble 🔥 en Narvarte!!!',))
        self.con.commit()
        _, texts = cards.render(self.con, 1, return_texts=True)
        self.assertIn('Depa increíble en Narvarte!!!', texts)
        self.con.execute('UPDATE listings SET title=? WHERE id=1', ('🏠🔥',))
        self.con.commit()
        _, texts = cards.render(self.con, 1, return_texts=True)
        self.assertIn('Departamento', texts)  # nothing printable left: the property type, never an empty line

    def test_whatsapp_formats(self):
        self.assertEqual(cards.format_whatsapp('+525578358858'), '55 7835 8858')
        self.assertEqual(cards.format_whatsapp('+15551234567'), '+15551234567')
        self.assertEqual(cards.format_whatsapp('+5215578358858'), '55 7835 8858')
        self.assertEqual(cards.format_whatsapp(''), '')


class NoOverflow(CardsBase):
    """Every text lands inside the card and inside its container, for the nastiest inputs."""
    NASTY = [
        {'title': 'Espectacular departamento remodelado con terraza privada vista panorámica ' * 5},
        {'title': 'X' * 300},
        {'title': 'Supercalifragilisticoespialidosamente' * 4, 'colonia': 'Y' * 80, 'municipio': 'Z' * 50},
        {'price_cents': 9223372036854775800, 'currency': 'USD'},
        {'price_cents': None, 'price_date': None},
        {'m2_built': 123456789.5, 'bedrooms': 99, 'bathrooms': 88.5, 'parking': 77},
        {'ref': 'FOLIO-123456789012345'},
        {'title': 'Áéíóú Ñandú ¿Cuánto cuesta? ¡Increíble! ' * 6, 'colonia': 'Lomas de Chapultepec Sección Palmas', 'municipio': 'Miguel Hidalgo'},
    ]

    def check(self, kind):
        spec = cards.build_spec(self.con, 1, kind)
        img, cv = cards._draw(spec)
        W, H = cards.KINDS[kind]['w'], cards.KINDS[kind]['h']
        self.assertTrue(cv.boxes)
        for text, (x0, y0, x1, y1), limit in cv.boxes:
            self.assertGreaterEqual(x0, 0, text)
            self.assertGreaterEqual(y0, 0, text)
            self.assertLessEqual(x1, W, text)
            self.assertLessEqual(y1, H, text)
            if limit:
                lx0, ly0, lx1, ly1 = limit
                self.assertGreaterEqual(x0, lx0 - 1.5, '%s left of its box' % text)
                self.assertLessEqual(x1, lx1 + 1.5, '%s right of its box' % text)
                self.assertGreaterEqual(y0, ly0 - 4, '%s above its box' % text)
                self.assertLessEqual(y1, ly1 + 4, '%s below its box' % text)

    def test_nasty_inputs_post_story_enlace(self):
        base = {'title': 'Departamento con vista al parque', 'price_cents': 450000000, 'currency': 'MXN', 'price_date': '2026-10-17',
                'm2_built': 120, 'bedrooms': 2, 'bathrooms': 2, 'parking': 1, 'colonia': 'Polanco', 'municipio': 'Miguel Hidalgo', 'ref': 'R1'}
        for extra in self.NASTY:
            vals = dict(base, **extra)
            self.con.execute('UPDATE listings SET %s WHERE id=1' % ', '.join('%s=?' % k for k in vals), list(vals.values()))
            self.con.execute("UPDATE users SET name=? WHERE id=1", ('Ana María de los Ángeles Fernández-Gutiérrez y Villalobos Sánchez',))
            self.con.execute("UPDATE agencies SET name=? WHERE id=1", ('Bienes Raíces Internacionales del Pacífico Mexicano S.A. de C.V.',))
            self.con.commit()
            for kind in ('post', 'story', 'enlace'):
                self.check(kind)

    def test_long_title_is_two_lines_with_an_ellipsis(self):
        title = 'Espectacular departamento remodelado con terraza privada vista panorámica ' * 5
        self.con.execute('UPDATE listings SET title=? WHERE id=1', (title,))
        self.con.commit()
        _, texts = cards.render(self.con, 1, return_texts=True)
        lines = [t for t in texts if t.startswith('Espectacular') or t.startswith('privada') or 'terraza' in t]
        self.assertLessEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith('…'))
        self.con.execute('UPDATE listings SET title=? WHERE id=1', ('X' * 300,))
        self.con.commit()
        cards.render(self.con, 1)

    def test_very_long_price_shrinks_to_fit(self):
        self.con.execute('UPDATE listings SET price_cents=? WHERE id=1', (9223372036854775800,))  # about the largest the database holds
        self.con.commit()
        _, texts = cards.render(self.con, 1, return_texts=True)
        self.assertTrue(any(t.startswith('$92,233,720,368,547,758') for t in texts))
        self.check('post')
        self.check('enlace')

    def test_closing_cards_do_not_overflow(self):
        self.close_listing(1, 'vendida', title='Una casa con un título larguísimo ' * 8)
        for kind in ('cierre_post', 'cierre_story'):
            for show in (False, True):
                spec = cards.build_spec(self.con, 1, kind, show_price=show)
                img, cv = cards._draw(spec)
                W, H = cards.KINDS[kind]['w'], cards.KINDS[kind]['h']
                for text, (x0, y0, x1, y1), limit in cv.boxes:
                    self.assertTrue(0 <= x0 and x1 <= W and 0 <= y0 and y1 <= H, text)
                    if limit:
                        self.assertTrue(x0 >= limit[0] - 1.5 and x1 <= limit[2] + 1.5, text)


class Fonts(CardsBase):
    def test_bundled_figtree_is_in_the_repo_and_loads(self):
        for name in (cards.BODY_FILE, cards.BOLD_FILE):
            path = os.path.join(BUNDLED, name)
            self.assertTrue(os.path.isfile(path), name)
            ImageFont.truetype(path, 40)
        self.assertTrue(os.path.isfile(os.path.join(BUNDLED, 'README.txt')))   # licence note + how to add the brand fonts
        self.assertTrue(os.path.isfile(os.path.join(cards.ASSETS, 'ficha-unica-mark-512.png')))

    def test_never_pil_default_when_the_bundled_font_exists(self):
        cards.FONT_USED.clear()
        for kind in ('post', 'story', 'enlace'):
            cards.render(self.con, 1, kind)
        self.close_listing(2)
        cards.render(self.con, 2, 'cierre_post')
        self.assertEqual(set(cards.FONT_USED), {'text', 'bold', 'display', 'price'})
        for role, path in cards.FONT_USED.items():
            self.assertNotEqual(path, 'PIL default', role)
            self.assertTrue(path.startswith(BUNDLED), '%s: %s' % (role, path))

    def test_pil_default_is_the_very_last_resort_and_still_renders(self):
        old = cards.BUNDLED_FONTS
        cards.BUNDLED_FONTS = os.path.join(self.tmp, 'no-fonts-here')
        try:
            cards.FONT_USED.clear()
            data = cards.render(self.con, 1)
            self.assertEqual(Image.open(io.BytesIO(data)).size, (1080, 1350))
            self.assertEqual(set(cards.FONT_USED.values()), {'PIL default'})
        finally:
            cards.BUNDLED_FONTS = old

    def test_env_font_still_forces_one_font(self):
        mine = os.path.join(self.tmp, 'mine.ttf')
        shutil.copy(os.path.join(BUNDLED, cards.BOLD_FILE), mine)
        os.environ['LLAVE_CARD_FONT'] = mine
        cards.FONT_USED.clear()
        cards.render(self.con, 1)
        self.assertEqual(set(cards.FONT_USED.values()), {mine})

    def test_brand_fonts_are_used_when_present_and_figtree_when_not(self):
        self.assertTrue(cards.fonts_signature().startswith('text=Figtree-500.ttf,bold=Figtree-600.ttf,display=Figtree-600.ttf,price=Figtree-600.ttf'))
        fd = os.path.join(self.tmp, 'brand')
        os.makedirs(fd)
        shutil.copy(os.path.join(BUNDLED, cards.BOLD_FILE), os.path.join(fd, 'Shrikhand-Regular.ttf'))          # stand-ins: only the lookup is tested
        shutil.copy(os.path.join(BUNDLED, cards.BOLD_FILE), os.path.join(fd, 'BricolageGrotesque-ExtraBold.ttf'))
        before = cards.render_cached(self.con, 1, 'post')
        os.environ['LLAVE_CARD_FONTS_DIR'] = fd
        cards.FONT_USED.clear()
        cards.render(self.con, 1)
        self.assertTrue(cards.FONT_USED['display'].endswith('Shrikhand-Regular.ttf'))
        self.assertTrue(cards.FONT_USED['price'].endswith('BricolageGrotesque-ExtraBold.ttf'))
        self.assertTrue(cards.FONT_USED['bold'].startswith(BUNDLED))   # everything else stays Figtree
        self.assertNotEqual(before, cards.render_cached(self.con, 1, 'post'))   # adding the brand fonts regenerates the cards
        del os.environ['LLAVE_CARD_FONTS_DIR']
        cards.FONT_USED.clear()
        cards.render(self.con, 1)
        self.assertTrue(cards.FONT_USED['display'].startswith(BUNDLED))

    def test_a_broken_brand_font_falls_back_to_figtree(self):
        fd = os.path.join(self.tmp, 'brand')
        os.makedirs(fd)
        with open(os.path.join(fd, 'Shrikhand-Regular.ttf'), 'wb') as fh:
            fh.write(b'not a font')
        os.environ['LLAVE_CARD_FONTS_DIR'] = fd
        cards.FONT_USED.clear()
        cards.render(self.con, 1)
        self.assertTrue(cards.FONT_USED['display'].startswith(BUNDLED))


class ClosingCards(CardsBase):
    def test_only_sold_or_rented_listings_have_a_closing_card(self):
        for status in ('borrador', 'activa', 'apartada', 'pausada'):
            self.con.execute('UPDATE listings SET status=? WHERE id=1', (status,))
            self.con.commit()
            for kind in ('cierre_post', 'cierre_story'):
                with self.assertRaises(ValueError, msg=status):
                    cards.render(self.con, 1, kind)
        for status, word in (('vendida', '¡VENDIDA!'), ('rentada', '¡RENTADA!')):
            self.close_listing(1, status)
            _, texts = cards.render(self.con, 1, 'cierre_post', return_texts=True)
            self.assertIn(word, texts)
        self.assertIn('¿Quieres rentar la tuya?', texts)
        self.close_listing(1, 'vendida')
        self.assertIn('¿Quieres vender la tuya?', cards.render(self.con, 1, 'cierre_story', return_texts=True)[1])

    def test_no_price_unless_the_agent_chose_to_show_it(self):
        self.close_listing(1)
        _, hidden = cards.render(self.con, 1, 'cierre_post', return_texts=True)
        joined = ' '.join(hidden)
        for bad in ('$', 'MXN', '4,500,000', '4500000', 'Precio'):
            self.assertNotIn(bad, joined)
        _, shown = cards.render(self.con, 1, 'cierre_post', show_price=True, return_texts=True)
        self.assertIn('$4,500,000 MXN', shown)
        self.assertIn('Precio de lista', shown)          # it is the list price: we do not know what it sold for
        self.assertNotIn('Precio al 17 oct 2026', shown)

    def test_a_title_that_says_the_price_is_not_printed_when_the_price_is_hidden(self):
        for title in ('Departamento en venta $4.5 mdp', 'Casa 4,500,000 pesos', 'Depa 4500000 oportunidad', 'Penthouse US$ 3 millones'):
            self.close_listing(1, 'vendida', title=title)
            _, hidden = cards.render(self.con, 1, 'cierre_post', return_texts=True)
            self.assertNotIn(title, hidden)
            self.assertIn('Departamento en Polanco', hidden)
            _, shown = cards.render(self.con, 1, 'cierre_post', show_price=True, return_texts=True)
            self.assertTrue(any(title.split()[-1][:3] in t for t in shown), title)     # the agent chose to show it: their own words stay

    def test_nothing_about_the_buyer_is_ever_on_the_card(self):
        self.close_listing(1)
        operaciones.create(self.con, 1, 'Carlos Comprador Ruiz', 'venta', '5599887766', 1, 410000000, 'Pagó de contado, quiere escriturar pronto')
        self.con.commit()
        for kind in ('cierre_post', 'cierre_story'):
            for show in (False, True):
                _, texts = cards.render(self.con, 1, kind, show_price=show, return_texts=True)
                joined = ' '.join(texts)
                for bad in ('Carlos', 'Comprador', 'Ruiz', '5599887766', '55 9988 7766', '4,100,000', 'contado', 'escriturar'):
                    self.assertNotIn(bad, joined)
                self.assertEqual([t for t in texts if re.search(r'\d{2} \d{4} \d{4}', t)], ['55 1122 3344'])   # only the agent's own number

    def test_closing_cache_keeps_the_two_price_choices_apart(self):
        self.close_listing(1)
        a = cards.render_cached(self.con, 1, 'cierre_post')
        b = cards.render_cached(self.con, 1, 'cierre_post', show_price=True)
        self.assertNotEqual(a, b)
        self.assertEqual(a, cards.render_cached(self.con, 1, 'cierre_post'))
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, a)) and os.path.exists(os.path.join(db.MEDIA_DIR, b)))
        self.assertNotEqual(open(os.path.join(db.MEDIA_DIR, a), 'rb').read(), open(os.path.join(db.MEDIA_DIR, b), 'rb').read())

    def test_closing_card_with_no_price_set_shows_none_even_when_asked(self):
        self.close_listing(1, price_cents=None)
        _, texts = cards.render(self.con, 1, 'cierre_post', show_price=True, return_texts=True)
        self.assertNotIn('Precio de lista', texts)
        self.assertNotIn('Precio a consultar', texts)


class PlanGate(CardsBase):
    def agency(self, plan):
        self.con.execute('UPDATE agencies SET plan=? WHERE id=1', (plan,))
        return self.con.execute('SELECT * FROM agencies WHERE id=1').fetchone()

    def test_instagram_images_stay_pro_and_up_today(self):
        self.assertIn('tools', db.PLAN_FEATURES)
        self.assertEqual(db.PLAN_FEATURES['tools'], ('pro', 'ia'))
        g, p, i = self.agency('gratis'), self.agency('pro'), self.agency('ia')
        for kind in ('post', 'story', 'cierre_post', 'cierre_story'):
            self.assertFalse(cards.can_make(g, kind), kind)
            self.assertTrue(cards.can_make(p, kind), kind)
            self.assertTrue(cards.can_make(i, kind), kind)

    def test_link_preview_card_is_for_every_plan(self):
        self.assertTrue(cards.can_make(self.agency('gratis'), 'enlace'))

    def test_v2_gives_gratis_only_the_plain_post_card(self):
        os.environ['LLAVE_PLANS_V2'] = '1'
        g = self.agency('gratis')
        self.assertTrue(cards.can_make(g, 'post'))
        for kind in ('story', 'cierre_post', 'cierre_story'):
            self.assertFalse(cards.can_make(g, kind), kind)
        os.environ['LLAVE_PLANS_V2'] = '0'
        self.assertFalse(cards.can_make(g, 'post'))
        os.environ.pop('LLAVE_PLANS_V2')
        self.assertFalse(cards.can_make(g, 'post'))


class Cache(CardsBase):
    def path(self, kind='post', lid=1):
        return cards.render_cached(self.con, lid, kind)

    def test_same_inputs_same_file(self):
        p1 = self.path()
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, p1)))
        self.assertEqual(p1, self.path())
        data = open(os.path.join(db.MEDIA_DIR, p1), 'rb').read()
        self.assertEqual(Image.open(io.BytesIO(data)).size, (1080, 1350))

    def test_every_visible_change_makes_a_new_card_and_removes_the_old_one(self):
        changes = [
            ('UPDATE listings SET price_cents=480000000 WHERE id=1',),
            ("UPDATE listings SET title='Otro título' WHERE id=1",),
            ("UPDATE listings SET colonia='Roma Norte' WHERE id=1",),
            ("UPDATE listings SET bedrooms=3 WHERE id=1",),
            ("UPDATE listings SET operation='renta' WHERE id=1",),
            ("UPDATE listings SET currency='USD' WHERE id=1",),
            ("UPDATE listings SET price_date='2026-11-01' WHERE id=1",),
            ("UPDATE listings SET updated_at='2026-10-18 09:00:00' WHERE id=1",),   # any edit at all
            ("UPDATE agencies SET accent='#FF4F1F' WHERE id=1",),
            ("UPDATE agencies SET name='VIVE Polanco Premium' WHERE id=1",),
            ("UPDATE users SET name='Rosa María Pérez' WHERE id=1",),
            ("UPDATE users SET whatsapp='+525500001111' WHERE id=1",),
        ]
        prev = self.path()
        for (sql,) in changes:
            self.con.execute(sql)
            self.con.commit()
            cur = self.path()
            self.assertNotEqual(prev, cur, sql)
            self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, cur)), sql)
            self.assertFalse(os.path.exists(os.path.join(db.MEDIA_DIR, prev)), 'old card left behind after: ' + sql)
            prev = cur
        self.assertEqual(len(os.listdir(os.path.join(db.MEDIA_DIR, 'cards'))), 1)

    def test_a_new_or_changed_photo_makes_a_new_card(self):
        p0 = self.path()
        photos.ingest(self.con, 1, make_jpeg((1800, 1200), seed=1))
        p1 = self.path()
        self.assertNotEqual(p0, p1)
        photos.ingest(self.con, 1, make_jpeg((1800, 1200), seed=2))
        self.assertEqual(p1, self.path())                      # a second photo is not on the card
        self.con.execute('DELETE FROM photos WHERE listing_id=1 AND position=0')                 # the first one went away
        self.con.execute('UPDATE photos SET position=0 WHERE listing_id=1')
        self.con.commit()
        self.assertNotEqual(p1, self.path())

    def test_other_listings_and_kinds_do_not_remove_each_others_cards(self):
        a, b, c = self.path('post', 1), self.path('story', 1), self.path('post', 2)
        self.con.execute("UPDATE listings SET title='Nuevo' WHERE id=1")
        self.con.commit()
        self.path('post', 1)
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, b)))
        self.assertTrue(os.path.exists(os.path.join(db.MEDIA_DIR, c)))
        self.assertFalse(os.path.exists(os.path.join(db.MEDIA_DIR, a)))

    def test_code_version_is_part_of_the_key(self):
        p1 = self.path()
        old = cards.CARD_VERSION
        cards.CARD_VERSION = old + '-next'
        try:
            self.assertNotEqual(p1, self.path())
        finally:
            cards.CARD_VERSION = old


class ShareText(CardsBase):
    def test_short_spanish_message_with_the_listing_url(self):
        l = self.con.execute('SELECT * FROM listings WHERE id=1').fetchone()
        t = cards.share_text(l, 'https://a.fichaunica.mx/propiedad/l1')
        self.assertEqual(t, 'Departamento con vista al parque\n$4,500,000 MXN · Polanco, Miguel Hidalgo\nFotos y datos aquí: https://a.fichaunica.mx/propiedad/l1')
        self.assertLess(len(t), 200)
        l2 = dict(l, price_cents=None, colonia=None, municipio=None)
        self.assertIn('Precio a consultar', cards.share_text(l2, 'https://x'))


if __name__ == '__main__':
    unittest.main()
