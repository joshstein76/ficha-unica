#!/usr/bin/env python3
"""Seed the local demo: VIVE Polanco (8 listings) + Agencia Ejemplo (Bolsa test). Idempotent; --reset wipes data/."""
import csv
import glob
import json
import os
import re
import secrets
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import auth, db, photos  # noqa: E402

PACK = '/Users/joshstein/Desktop/Claude Ledger/josh-command-center/clients/vive-polanco/work/2026-10-17-FREE-TRAFFIC-PACK'
CACHE = os.path.join(ROOT, 'data', 'seed-cache')
CREDS = os.path.join(ROOT, 'seed', 'DEMO-CREDENTIALS.local.md')
UA = 'Mozilla/5.0 (LLAVE local seed)'
MAX_PHOTOS = 10
PORTALS = ('trovit', 'mitula', 'llave_open', 'mercadolibre')

RITZ_AMEN_5203 = ['Spa', 'Alberca interior', 'Gimnasio', 'Concierge 24 h', 'Valet parking', 'Admite mascotas']


def parse_price(s):
    """-> (cents or None, currency, note or None)"""
    s = s.strip()
    cur = 'USD' if s.startswith('US$') else 'MXN'
    if 'verify' in s.lower() or re.search(r'\d-\d', s):
        return None, cur, 'Precio por verificar (CSV: "%s")' % s
    m = re.search(r'([\d,]+)', s)
    return int(m.group(1).replace(',', '')) * 100, cur, None


def first_num(s, pat=r'([\d.]+)'):
    m = re.search(pat, s or '')
    return float(m.group(1)) if m else None


def parse_beds_baths(s):
    b = re.search(r'(\d+)\s*rec', s or '')
    ba = re.search(r'([\d.]+)\s*bañ', s or '')
    return (int(b.group(1)) if b else None), (float(ba.group(1)) if ba else None)


# Josh cleared ALL Ritz units for portals on 2026-10-17. Facts copied from LISTING-TEXTS-ES-EN.md (VIVE pack, 10-17).
# resale=True -> the required line "Residencia de propietario privado (reventa), publicada por VIVE Polanco". 4804 is NOT a resale.
RITZ = {
    '4804': dict(cents=130000000, cur='USD', date='2026-10-17', m2=75, beds=1, baths=1, park=1, maint=None, resale=False,
                 datos='75 m² interiores · 1 recámara con escritorio · 1 baño · 1 estacionamiento · mantenimiento US$1,200 al mes · '
                       'entrega inmediata · nunca habitada, se vende amueblada'),
    '4908': dict(cents=280000000, cur='USD', date='2026-10-01', m2=134, beds=2, baths=2.5, park=2, resale=True,
                 datos='134 m² interiores + 33 m² de terraza · 2 recámaras · 2.5 baños · 2 estacionamientos · vista al Bosque de Chapultepec'),
    '5102': dict(cents=85000000, cur='USD', date='2026-10-01', m2=83, beds=1, baths=1, park=1, resale=True,
                 datos='aprox. 83 m² interiores · 1 recámara · 1 baño · 1 estacionamiento · nivel 51 · vista a la ciudad'),
    '5002': dict(cents=82500000, cur='USD', date='2026-10-01', m2=78, beds=1, baths=1, park=1, resale=True,
                 datos='78 m² interiores · 1 recámara · 1 baño · 1 estacionamiento · nivel 50 · vista a la ciudad'),
    '5105': dict(cents=2750000000, cur='MXN', date='2026-10-01', m2=96, beds=2, baths=2, park=2, resale=True,
                 datos='96 m² interiores + 14.27 m² de terraza · 2 recámaras · 2 baños · 2 estacionamientos · nivel 51 · vista al Bosque de Chapultepec'),
    '5407': dict(cents=149000000, cur='USD', date='2026-10-01', m2=80, beds=1, baths=2, park=1, resale=True,
                 datos='80 m² interiores + 18 m² de terraza · 1 recámara · 2 baños · 1 estacionamiento · vista al Bosque de Chapultepec'),
}
RESALE_LINE = 'Residencia de propietario privado (reventa), publicada por VIVE Polanco.'


def parse_texts():
    txt = open(os.path.join(PACK, 'LISTING-TEXTS-ES-EN.md'), encoding='utf-8').read()
    out = {}
    for block in re.split(r'\n## ', txt)[1:]:
        key = '5203' if '5203' in block.split('\n')[0] else ('heraclito' if 'Heráclito' in block.split('\n')[0] else None)
        if not key:
            continue
        get = lambda label: (re.search(r'\*\*%s[^*]*\*\*:?\s*(.+)' % label, block) or [None, None])[1]
        desc = get('Descripción ES')
        # drop the trailing site link / WhatsApp tail; the public site adds its own contact
        desc = re.split(r'\s*Más información y visita:|\s*https://', desc)[0].strip()
        out[key] = {'title': get('Título ES').strip(), 'desc': desc}
    return out


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, re.sub(r'[^A-Za-z0-9._-]+', '_', url.split('/wp-content/uploads/')[-1]))
    if os.path.exists(fn):
        return open(fn, 'rb').read(), False
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    with open(fn, 'wb') as f:
        f.write(data)
    time.sleep(2)
    return data, True


def pick_urls(unit, urls):
    """Keep only property photos for this unit (or generic building shots); floor plans last."""
    keep, plans = [], []
    for u in urls:
        fn = u.split('/')[-1]
        low = fn.lower()
        if any(x in low for x in ('logo', 'agent-circle', 'vive-ad', 'planta-tipo')):
            continue
        if any(x in low for x in ('thompson', 'sudermann', 'ocean-terrace', 'st-residences')):
            continue
        nums = re.findall(r'(?<!\d)([45]\d{3})(?!\d)', low)
        if any(n != unit for n in nums):
            continue
        if 'plano' in low:
            plans.append(u)
        else:
            keep.append((0 if unit in low else 1, len(keep), u))
    keep = [u for _, _, u in sorted(keep)]
    return (keep + plans)[:MAX_PHOTOS] if not plans else (keep[:MAX_PHOTOS - len(plans)] + plans)


def local_files(unit_dir):
    d = os.path.join(PACK, 'photos', unit_dir)
    fs = sorted(glob.glob(os.path.join(d, 'web-1600', '*.jpg')))
    return fs or sorted(glob.glob(os.path.join(d, 'original', '*.jpg')))


def main():
    reset = '--reset' in sys.argv
    if reset:
        for p in (db.DB_PATH, db.DB_PATH + '-wal', db.DB_PATH + '-shm'):
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(db.MEDIA_DIR, ignore_errors=True)
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    con = db.connect()
    db.init(con)
    if con.execute("SELECT 1 FROM agencies WHERE slug='vive-polanco'").fetchone():
        print("Ya existe 'vive-polanco'; nada que hacer (usa --reset para recrear).")
        return

    pw1, pw2 = secrets.token_urlsafe(12), secrets.token_urlsafe(12)
    cur = con.execute(
        "INSERT INTO agencies(slug,name,tagline,whatsapp,email,city,design,accent,about,is_demo,plan) "
        "VALUES(?,?,?,?,?,?,?,?,?,1,'agencia')",
        ('vive-polanco', 'VIVE Polanco', 'Bienes raíces en Polanco', '+525578358858', 'contacto@vivepolanco.test',
         'Ciudad de México', 'residencia', '#1a1a1a',
         'VIVE Polanco acompaña a compradores y propietarios en Polanco y la Ciudad de México. '
         'Atendemos cada propiedad con información clara y trato directo.'))
    vive = cur.lastrowid
    uid1 = con.execute("INSERT INTO users(agency_id,name,email,whatsapp,password_hash,role) VALUES(?,?,?,?,?, 'owner')",
                       (vive, 'Equipo VIVE', 'demo@vivepolanco.test', '+525578358858', auth.hash_password(pw1))).lastrowid
    cur = con.execute(
        "INSERT INTO agencies(slug,name,tagline,whatsapp,email,city,design,accent,about,is_demo,plan) "
        "VALUES('agencia-ejemplo','Agencia Ejemplo (demo)','Agencia de demostración','+525500000000',"
        "'contacto@ejemplo.test','Ciudad de México','ciudad','#1f4e79',"
        "'Agencia de demostración para probar la red entre agentes (Bolsa).',1,'gratis')")
    ej = cur.lastrowid
    con.execute("INSERT INTO users(agency_id,name,email,whatsapp,password_hash,role) VALUES(?,?,?,?,?, 'owner')",
                (ej, 'Equipo Ejemplo', 'demo2@ejemplo.test', '+525500000000', auth.hash_password(pw2)))
    con.commit()
    with open(CREDS, 'w', encoding='utf-8') as f:
        f.write('# Credenciales demo (local, no se sube a git)\n\n'
                '- vive-polanco: demo@vivepolanco.test / %s\n- agencia-ejemplo: demo2@ejemplo.test / %s\n' % (pw1, pw2))
    print('credenciales en seed/DEMO-CREDENTIALS.local.md')

    texts = parse_texts()
    rows = list(csv.DictReader(open(os.path.join(PACK, 'listings-upload-pack.csv'), encoding='utf-8-sig')))
    summary = []
    for i, r in enumerate(rows, 1):
        name = r['listing']
        her = name.startswith('Heráclito')
        unit = None if her else name.split('·')[-1].strip()
        cents, curr, note = parse_price(r['price_as_shown_on_site_2026-10-17'])
        beds, baths = parse_beds_baths(r['beds_baths'])
        m2 = first_num(r['size'])
        parking = int(first_num(r['parking'])) if first_num(r['parking']) is not None else None
        cleared = True  # Josh 2026-10-17: all Ritz units + Heráclito cleared for portals
        rz = RITZ.get(unit)
        t = texts.get('heraclito' if her else ('5203' if unit == '5203' else None))
        if t:
            title, desc = t['title'], t['desc']
        else:
            title = 'Residencia %s en The Ritz-Carlton Residences, Mexico City' % unit
            facts = []
            if m2:
                facts.append('%g m² interiores' % m2)
            if beds:
                facts.append('%d recámara%s' % (beds, '' if beds == 1 else 's'))
            if baths:
                facts.append('%g baño%s' % (baths, '' if baths == 1 else 's'))
            if parking:
                facts.append('%d estacionamiento%s' % (parking, '' if parking == 1 else 's'))
            if rz:
                cents, curr, note = rz['cents'], rz['cur'], None
                m2, beds, baths, parking = rz['m2'], rz['beds'], rz['baths'], rz['park']
                facts = []
            desc = (((RESALE_LINE + ' ') if rz and rz['resale'] else '') +
                    'Residencia %s en The Ritz-Carlton Residences, Mexico City, Paseo de la Reforma 509.' % unit +
                    ((' ' + rz['datos'][0].upper() + rz['datos'][1:] + '.') if rz else '') +
                    (' ' + ' · '.join(facts).capitalize() + '.' if facts else '') +
                    ' Consulta disponibilidad y precio con VIVE Polanco.')
        if her:
            addr = ('Heráclito', '331', 'Polanco V Sección', 'Miguel Hidalgo')
        else:
            addr = ('Paseo de la Reforma', '509', 'Cuauhtémoc', 'Cuauhtémoc')
        notes = []
        if note:
            notes.append(note)
        if not cleared:
            notes.append(r['status_for_portals'])
        furnished = 1 if 'amueblado' in r['price_as_shown_on_site_2026-10-17'] else 0
        ref = 'VIVE-%04d' % i
        lid = con.execute(
            "INSERT INTO listings(agency_id,agent_id,ref,slug,status,operation,property_type,title,description,"
            "price_cents,currency,price_date,m2_built,bedrooms,bathrooms,parking,floor,furnished,pets,amenities,"
            "street,ext_number,colonia,municipio,estado,show_exact_location,source_url,share_in_bolsa,internal_note) "
            "VALUES(?,?,?,?,?, 'venta','departamento',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Ciudad de México',0,?,?,?)",
            (vive, uid1, ref, db.slugify(title), 'activa' if cleared else 'pausada', title, desc, cents, curr,
             '2026-10-05' if unit == '5203' else (rz['date'] if rz else '2026-10-17'), m2, beds, baths, parking,
             '52' if unit == '5203' else None, furnished, 1 if unit == '5203' else 0,
             json.dumps(RITZ_AMEN_5203 if unit == '5203' else [], ensure_ascii=False),
             addr[0], addr[1], addr[2], addr[3], r['live_url'], 1 if her else 0,
             ' | '.join(notes) or None)).lastrowid
        # map pins (OpenStreetMap Nominatim, 10-17; Heráclito = street-level). Public maps snap to a ~250 m grid.
        con.execute('UPDATE listings SET lat=?, lng=? WHERE id=?', ((19.4328220, -99.1903221) if her else (19.4241618, -99.1757815)) + (lid,))
        if cleared:
            for p in PORTALS:
                con.execute('INSERT INTO portal_publications(listing_id,portal,enabled) VALUES(?,?,1)', (lid, p))
            if her:
                con.execute("INSERT INTO shares(listing_id,sharing_agency_id,split_pct,status) VALUES(?,?,50,'activa')", (lid, ej))
        con.commit()

        # photos
        ing, skipped = 0, []
        sources = []
        if her:
            sources = [('file', f) for f in local_files('heraclito-331')[:MAX_PHOTOS]]
        else:
            urls = pick_urls(unit, r['photo_urls_(full-size, watermarked)'].split(' | '))
            if unit == '5203':
                loc = local_files('5203')
                plans = [u for u in urls if 'plano' in u.lower()]
                sources = [('file', f) for f in loc[:MAX_PHOTOS - len(plans)]] + [('url', u) for u in plans]
            else:
                sources = [('url', u) for u in urls]
        for kind, s in sources:
            label = os.path.basename(s)
            try:
                data = open(s, 'rb').read() if kind == 'file' else fetch(s)[0]
                alt = '%s - %s' % (title, 'plano' if 'plano' in label.lower() else 'foto')
                photos.ingest(con, lid, data, alt=alt)
                ing += 1
            except Exception as e:
                skipped.append('%s (%s)' % (label, e))
                print('  omitida %s: %s' % (label, e))
        summary.append((ref, name, 'activa' if cleared else 'pausada', ing, len(skipped)))

    print('\n%-10s %-34s %-8s %6s %8s' % ('ref', 'listing', 'status', 'fotos', 'omitidas'))
    for s in summary:
        print('%-10s %-34s %-8s %6d %8d' % s)


if __name__ == '__main__':
    main()
