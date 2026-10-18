import datetime
import json
import os
import random
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from PIL import Image, ImageFilter

from llave import db
from llave.ai import client, writer, photo_qa, comps, geo_seo, social_kit


def fake(responses, calls=None):
    """transport returning queued (status, dict|bytes) items."""
    q = list(responses)

    def t(url, headers, body):
        if calls is not None:
            calls.append((url, headers, json.loads(body.decode())))
        s, b = q.pop(0)
        if isinstance(b, Exception):
            raise b
        return s, (b if isinstance(b, bytes) else json.dumps(b).encode())
    return t


def ok_resp(obj):
    return (200, {'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'x'},
                                                         {'type': 'text', 'text': json.dumps(obj)}]})


SCH = {'type': 'object', 'properties': {'a': {'type': 'string'}}, 'required': ['a'], 'additionalProperties': False}


class EnvCase(unittest.TestCase):
    ENV = {'ANTHROPIC_API_KEY': 'sk-test-123', 'LLAVE_AI_LIVE': '1'}

    def setUp(self):
        p = mock.patch.dict(os.environ, self.ENV)
        p.start()
        os.environ.pop('ANTHROPIC_AUTH_TOKEN', None)
        mock.patch('llave.ai.client.time.sleep').start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(p.stop)


class ClientTest(EnvCase):
    def test_request_shape(self):
        calls = []
        r = client.complete_json('sys', 'usr', SCH, effort='high', transport=fake([ok_resp({'a': 'b'})], calls))
        self.assertEqual(r, {'a': 'b'})
        url, h, body = calls[0]
        self.assertEqual(url, 'https://api.anthropic.com/v1/messages')
        self.assertEqual(h['x-api-key'], 'sk-test-123')
        self.assertEqual(h['anthropic-version'], '2023-06-01')
        self.assertEqual(h['content-type'], 'application/json')
        self.assertEqual(h['anthropic-beta'], 'server-side-fallback-2026-07-01')
        self.assertEqual(body['model'], 'claude-opus-5-5')
        self.assertEqual(body['max_tokens'], 16000)
        self.assertEqual(body['fallbacks'], 'default')
        self.assertEqual(body['system'], 'sys')
        self.assertEqual(body['messages'], [{'role': 'user', 'content': 'usr'}])
        self.assertEqual(body['output_config']['effort'], 'high')
        self.assertEqual(body['output_config']['format'], {'type': 'json_schema', 'schema': SCH})
        for bad in ('thinking', 'temperature', 'tool_choice', 'tools'):
            self.assertNotIn(bad, body)

    def test_oauth_token(self):
        os.environ.pop('ANTHROPIC_API_KEY')
        os.environ['ANTHROPIC_AUTH_TOKEN'] = 'tok-1'
        calls = []
        client.complete_json('s', 'u', SCH, transport=fake([ok_resp({'a': 'x'})], calls))
        h = calls[0][1]
        self.assertEqual(h['Authorization'], 'Bearer tok-1')
        self.assertNotIn('x-api-key', h)
        self.assertEqual(h['anthropic-beta'], 'oauth-2025-04-20,server-side-fallback-2026-07-01')

    def test_enabled(self):
        self.assertTrue(client.enabled())
        os.environ['LLAVE_AI_LIVE'] = '0'
        self.assertFalse(client.enabled())
        os.environ['LLAVE_AI_LIVE'] = '1'
        os.environ.pop('ANTHROPIC_API_KEY')
        self.assertFalse(client.enabled())

    def test_refusal_and_max_tokens(self):
        with self.assertRaises(client.AIRefused):
            client.complete_json('s', 'u', SCH, transport=fake([(200, {'stop_reason': 'refusal', 'content': []})]))
        with self.assertRaises(client.AIIncomplete):
            client.complete_json('s', 'u', SCH, transport=fake([(200, {'stop_reason': 'max_tokens',
                                                                        'content': [{'type': 'text', 'text': '{"a"'}]})]))

    def test_retry_429_then_ok(self):
        calls = []
        r = client.complete_json('s', 'u', SCH, transport=fake([(429, {}), (503, {}), ok_resp({'a': 'ok'})], calls))
        self.assertEqual(r, {'a': 'ok'})
        self.assertEqual(len(calls), 3)

    def test_retry_exhausted_and_no_retry_on_400(self):
        with self.assertRaises(client.AIError):
            client.complete_json('s', 'u', SCH, transport=fake([(500, {})] * 3))
        calls = []
        with self.assertRaises(client.AIError) as cm:
            client.complete_json('s', 'u', SCH, transport=fake([(401, {}), ok_resp({'a': 'x'})], calls))
        self.assertEqual(len(calls), 1)
        self.assertNotIn('sk-test-123', str(cm.exception))

    def test_retry_on_network_error(self):
        r = client.complete_json('s', 'u', SCH, transport=fake([(0, urllib.error.URLError('down')), ok_resp({'a': 'y'})]))
        self.assertEqual(r, {'a': 'y'})

    def test_schemas_follow_limits(self):
        def walk(s):
            if isinstance(s, dict):
                for bad in ('minLength', 'maxLength', 'minimum', 'maximum'):
                    self.assertNotIn(bad, s)
                if s.get('type') == 'object':
                    self.assertIs(s.get('additionalProperties'), False)
                    self.assertEqual(sorted(s['required']), sorted(s['properties']))
                for v in s.values():
                    walk(v)
            elif isinstance(s, list):
                for v in s:
                    walk(v)
        walk(writer.SCHEMA)
        walk(social_kit.POLISH_SCHEMA)


def canon(**kw):
    c = {'id': 1, 'ref': 'V-1', 'slug': 's', 'url': 'http://x/p', 'status': 'activa', 'operation': 'venta',
         'property_type': 'departamento', 'title': 'Depto', 'description': '', 'price': 4500000, 'currency': 'MXN',
         'price_date': '2026-10-10', 'maintenance': 3500, 'm2_built': 85.0, 'm2_land': None, 'bedrooms': 2,
         'bathrooms': 2.0, 'parking': 1, 'floor': '4', 'year_built': None, 'furnished': False, 'pets': True,
         'amenities': ['Gimnasio'], 'address': {'colonia': 'Polanco', 'municipio': 'Miguel Hidalgo', 'estado': 'CDMX'},
         'agency': {'name': 'VIVE', 'whatsapp': '+52 55 1111 2222'}}
    c.update(kw)
    return c


GOOD = {'title': 'Departamento en venta en Polanco, 2 recámaras',
        'description': 'Departamento de 85 m² en Polanco. Tiene 2 recámaras y 2 baños. Precio: $4,500,000 MXN.',
        'highlights': ['85 m²', '2 recámaras', '2 baños']}


class WriterTest(EnvCase):
    def test_template_es_en(self):
        with mock.patch.dict(os.environ, {'LLAVE_AI_LIVE': '0'}):
            es = writer.describe(canon())
            en = writer.describe(canon(), lang='en')
        self.assertEqual(es['source'], 'plantilla')
        self.assertLessEqual(len(es['title']), 90)
        self.assertIn('Polanco', es['title'])
        self.assertIn('$4,500,000 MXN', es['description'])
        self.assertIn('Acepta mascotas', es['description'])
        self.assertTrue(3 <= len(es['highlights']) <= 5)
        self.assertIn('for sale', en['title'])
        self.assertIn('Pets are welcome', en['description'])
        self.assertIsNone(writer.validate(canon(), {k: es[k] for k in ('title', 'description', 'highlights')}))

    def test_ai_mode_ok(self):
        calls = []
        r = writer.describe(canon(), transport=fake([ok_resp(GOOD)], calls))
        self.assertEqual(r['source'], 'ia')
        self.assertEqual(r['title'], GOOD['title'])
        body = calls[0][2]
        self.assertIn('4500000', body['messages'][0]['content'])
        self.assertNotIn('1111', body['messages'][0]['content'])  # no contact data to the model

    def test_invented_number_rejected(self):
        bad = dict(GOOD, description=GOOD['description'] + ' A 300 metros del metro.')
        r = writer.describe(canon(), transport=fake([ok_resp(bad)]))
        self.assertEqual(r['source'], 'plantilla')
        self.assertIn('300', r['reason'])
        bad2 = dict(GOOD, description='El mejor departamento de 85 m².')
        r = writer.describe(canon(), transport=fake([ok_resp(bad2)]))
        self.assertEqual(r['source'], 'plantilla')

    def test_ai_failure_falls_back(self):
        r = writer.describe(canon(), transport=fake([(200, {'stop_reason': 'refusal', 'content': []})]))
        self.assertEqual(r['source'], 'plantilla')
        self.assertTrue(r['reason'])


def noisy(seed, size=(400, 300), base=130, amp=100):
    rnd = random.Random(seed)
    im = Image.new('RGB', size)
    im.putdata([(lambda v: (v, v, min(255, v + 20)))(max(0, min(255, int(base + rnd.uniform(-amp, amp)))))
                for _ in range(size[0] * size[1])])
    return im


class DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._media = db.MEDIA_DIR
        db.MEDIA_DIR = os.path.join(self.tmp, 'media')
        self.con = db.connect(os.path.join(self.tmp, 't.db'))
        db.init(self.con)
        self.con.execute("INSERT INTO agencies(id,slug,name,whatsapp) VALUES (1,'a','Agencia A','+525511112222')")
        self.con.execute("INSERT INTO agencies(id,slug,name) VALUES (2,'b','Agencia B')")
        self.con.commit()
        self.n = 0
        p = mock.patch.dict(os.environ, {'LLAVE_AI_LIVE': '0'})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        db.MEDIA_DIR = self._media

    def listing(self, agency=1, colonia='Polanco', price=4500000, m2=85, op='venta', cur='MXN', status='activa',
                ptype='departamento', municipio='Miguel Hidalgo', created='2026-10-01 10:00:00', price_date='2026-10-10'):
        self.n += 1
        c = self.con.execute(
            'INSERT INTO listings(agency_id,ref,slug,status,operation,property_type,title,price_cents,currency,price_date,'
            'm2_built,bedrooms,colonia,municipio,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (agency, 'R-%d' % self.n, 's%d' % self.n, status, op, ptype, 'Depto %d' % self.n,
             price * 100, cur, price_date, m2, 2, colonia, municipio, created))
        self.con.commit()
        return c.lastrowid

    def photo(self, lid, img, pos):
        self.n += 1
        rel = 'zz/p%d/800.jpg' % self.n
        path = os.path.join(db.MEDIA_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path, 'JPEG', quality=92)
        c = self.con.execute('INSERT INTO photos(listing_id,position,sha256,width,height,sizes) VALUES (?,?,?,?,?,?)',
                             (lid, pos, 'sha%d' % self.n, img.size[0], img.size[1], json.dumps({'800': rel})))
        self.con.commit()
        return c.lastrowid


class PhotoQATest(DbCase):
    def test_analyze(self):
        lid = self.listing()
        dark = self.photo(lid, noisy(1, base=20, amp=15), 0)
        blur = self.photo(lid, noisy(2).filter(ImageFilter.GaussianBlur(8)), 1)
        good = self.photo(lid, noisy(3), 2)
        dup1 = self.photo(lid, noisy(4), 3)
        dup2 = self.photo(lid, noisy(4), 4)
        plan = self.photo(lid, Image.new('RGB', (400, 300), (255, 255, 255)), 5)
        r = photo_qa.analyze(self.con, lid)
        by = {p['photo_id']: p for p in r['photos']}
        self.assertIn('Foto oscura', by[dark]['issues'])
        self.assertIn('Foto borrosa', by[blur]['issues'])
        self.assertEqual(by[good]['issues'], [])
        self.assertTrue(by[plan]['is_floorplan'])
        self.assertFalse(by[good]['is_floorplan'])
        self.assertIn('Foto repetida', by[dup2]['issues'])
        self.assertNotIn('Foto repetida', by[dup1]['issues'])
        order = r['suggested_order']
        self.assertEqual(sorted(order), sorted(by))
        self.assertIn(order[0], (good, dup1))
        self.assertEqual(order[-1], plan)
        self.assertLess(order.index(good), order.index(blur))
        self.assertLess(order.index(dup1), order.index(dup2))
        tips = ' | '.join(r['tips'])
        self.assertIn('Agrega al menos 8 fotos', tips)
        self.assertIn('La portada está oscura', tips)
        self.assertIn('Hay 1 foto borrosa', tips)
        self.assertIn('repetida', tips)

    def test_empty(self):
        lid = self.listing()
        r = photo_qa.analyze(self.con, lid)
        self.assertEqual(r['photos'], [])
        self.assertIn('Agrega al menos 8 fotos', r['tips'][0])


class CompsTest(DbCase):
    def test_ok_and_exclusions(self):
        me = self.listing(price=5000000, m2=80)
        for p, m in ((4000000, 80), (4400000, 70), (5200000, 90)):
            self.listing(price=p, m2=m, agency=2)
        self.listing(price=9999999, m2=80, cur='USD')
        self.listing(price=100, m2=80, op='renta')
        self.listing(price=100, m2=80, ptype='casa')
        self.listing(price=100, m2=200)
        self.listing(price=100, m2=80, status='borrador')
        self.listing(price=100, m2=80, colonia='Roma', municipio='Cuauhtémoc')
        r = comps.suggest_price(self.con, me)
        self.assertTrue(r['ok'])
        self.assertEqual(r['n'], 3)
        self.assertEqual(r['currency'], 'MXN')
        self.assertNotIn('R-1', [c['ref'] for c in r['comps']])
        self.assertLessEqual(r['range_low'], r['range_high'])
        self.assertEqual(r['price_per_m2_median'], 57778)
        self.assertIn('orientativo', r['note'])
        self.assertIn('Ficha Única', r['note'])
        self.assertIn('/propiedad/', r['comps'][0]['url'])

    def test_not_enough(self):
        me = self.listing()
        self.listing(price=4000000)
        self.listing(price=4100000, cur='USD')
        r = comps.suggest_price(self.con, me)
        self.assertFalse(r['ok'])
        self.assertEqual(r['note'], 'No hay suficientes comparables públicos en Ficha Única para sugerir precio')
        self.assertEqual(r['comps'], [])

    def test_municipio_fallback(self):
        me = self.listing(colonia='Polanco')
        for i in range(3):
            self.listing(colonia='Anzures', price=4000000 + i)
        r = comps.suggest_price(self.con, me)
        self.assertTrue(r['ok'])
        self.assertIn('municipio', r['note'])


class GeoTest(DbCase):
    def test_listing_faq_only_facts(self):
        faqs = geo_seo.listing_faq(canon(pets=False, parking=None, maintenance=None, m2_land=None))
        text = json.dumps(faqs, ensure_ascii=False)
        self.assertIn('$4,500,000 MXN', text)
        self.assertIn('10 oct 2026', text)
        self.assertIn('85 m²', text)
        self.assertIn('WhatsApp', text)
        for absent in ('mascotas', 'estacionamiento', 'antenimiento', 'amueblado'):
            self.assertNotIn(absent, text)
        ld = geo_seo.faq_jsonld(faqs)
        self.assertEqual(ld['@type'], 'FAQPage')
        self.assertEqual(len(ld['mainEntity']), len(faqs))
        self.assertEqual(ld['mainEntity'][0]['acceptedAnswer']['@type'], 'Answer')
        full = json.dumps(geo_seo.listing_faq(canon()), ensure_ascii=False)
        self.assertIn('mascotas', full)
        self.assertIn('$3,500 MXN', full)

    def test_agency_faq(self):
        self.listing(colonia='Polanco')
        self.listing(colonia='Condesa', ptype='casa')
        self.listing(colonia='Roma', status='borrador')
        a = self.con.execute('SELECT * FROM agencies WHERE id=1').fetchone()
        text = json.dumps(geo_seo.agency_faq(self.con, a), ensure_ascii=False)
        self.assertIn('Condesa y Polanco', text)
        self.assertNotIn('Roma', text)
        self.assertIn('casas', text)
        self.assertIn('WhatsApp', text)


class SocialTest(DbCase):
    TODAY = datetime.date(2026, 10, 17)

    def test_kit_structure(self):
        for i in range(4):
            self.listing(colonia='Polanco', price=4000000 + i * 100000, created='2026-10-0%d 10:00:00' % (i + 1))
        k = social_kit.weekly_kit(self.con, 1, today=self.TODAY)
        self.assertEqual(k['week'], '2026-W42')
        self.assertEqual([i['kind'] for i in k['items']], ['listing', 'listing', 'listing', 'market', 'tip'])
        lst = [i for i in k['items'] if i['kind'] == 'listing']
        self.assertEqual(len({i['listing_ref'] for i in lst}), 3)
        self.assertEqual(lst[0]['listing_ref'], 'R-4')
        for i in lst:
            self.assertTrue(i['image_url'].endswith('/tarjeta-post.jpg'))
            self.assertIn('/propiedad/', i['image_url'])
        for i in k['items']:
            self.assertLessEqual(len(i['hashtags']), 3)
            self.assertIn('WhatsApp', i['caption'])
            self.assertNotIn('#', i['caption'])
        m = k['items'][3]
        self.assertIn('Precio medio por m² en Polanco', m['caption'])
        self.assertIn('4 propiedades públicas en Ficha Única', m['caption'])
        tip = k['items'][-1]
        self.assertIn(tip['title'], [t for t, _ in social_kit.LESSONS])
        self.assertIsNone(tip['image_url'])

    def test_market_skipped_under_three(self):
        self.listing(colonia='Polanco')
        self.listing(colonia='Polanco')
        k = social_kit.weekly_kit(self.con, 1, today=self.TODAY)
        self.assertEqual([i['kind'] for i in k['items']], ['listing', 'listing', 'tip'])

    def test_ai_polish_validated(self):
        self.listing()
        self.listing(colonia='Roma')
        self.listing(colonia='Condesa')
        base = social_kit.weekly_kit(self.con, 1, today=self.TODAY)
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k', 'LLAVE_AI_LIVE': '1'}):
            caps = [{'index': i, 'caption': 'Texto pulido para WhatsApp.'} for i in range(len(base['items']))]
            caps[0] = {'index': 0, 'caption': 'Cuesta $9,999,999 por WhatsApp'}
            k = social_kit.weekly_kit(self.con, 1, today=self.TODAY, transport=fake([ok_resp({'captions': caps})]))
        self.assertEqual(k['items'][0]['caption'], base['items'][0]['caption'])
        self.assertEqual(k['items'][1]['caption'], 'Texto pulido para WhatsApp.')


if __name__ == '__main__':
    unittest.main()
