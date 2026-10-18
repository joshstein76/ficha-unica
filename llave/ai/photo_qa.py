"""Photo quality check with Pillow only (local, no network): light, contrast, sharpness, floor plans, repeats."""
import json
import os
import statistics

from PIL import Image, ImageFilter, ImageStat

from .. import db

DARK = 70          # mean luminance below this = dark
BRIGHT = 225       # above this = washed out
LOW_CONTRAST = 25  # luminance stddev below this = flat
BLURRY = 300       # variance of edge map below this = blurry
DUP_DIST = 5
MIN_PHOTOS = 8


def _dhash(gray):
    small = gray.resize((9, 8), Image.LANCZOS)
    px = list(small.getdata())
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (1 if px[r * 9 + c] > px[r * 9 + c + 1] else 0)
    return bits


def _metrics(path):
    with Image.open(path) as im:
        im = im.convert('RGB')
        im.thumbnail((800, 800))
        gray = im.convert('L')
        st = ImageStat.Stat(gray)
        brightness, contrast = st.mean[0], st.stddev[0]
        sharp = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]
        sat = ImageStat.Stat(im.convert('HSV').split()[1]).mean[0] / 255.0
        hist = gray.histogram()
        white = sum(hist[200:]) / float(sum(hist) or 1)
        w, h = im.size
        return {'brightness': round(brightness, 1), 'contrast': round(contrast, 1), 'sharpness': round(sharp, 1),
                'is_floorplan': bool(sat < 0.08 and white > 0.6), 'landscape': w >= h, 'hash': _dhash(gray)}


def _path(sizes):
    rel = sizes.get('800') or sizes.get('1600') or sizes.get('400')
    return os.path.join(db.MEDIA_DIR, rel) if rel else None


def analyze(con, listing_id):
    rows = con.execute('SELECT id, sizes FROM photos WHERE listing_id=? ORDER BY position, id', (listing_id,)).fetchall()
    infos = []
    for r in rows:
        p = _path(json.loads(r['sizes']))
        m = None
        if p and os.path.exists(p):
            try:
                m = _metrics(p)
            except (OSError, ValueError):
                m = None
        infos.append((r['id'], m))
    seen = []
    photos = []
    meta = {}
    for pid, m in infos:
        if m is None:
            photos.append({'photo_id': pid, 'score': 0, 'brightness': None, 'contrast': None, 'sharpness': None,
                           'is_floorplan': False, 'issues': ['No se pudo leer la foto']})
            meta[pid] = {'landscape': False, 'bad': True}
            continue
        issues, score = [], 100
        if m['is_floorplan']:
            issues_fp = True
        else:
            issues_fp = False
            if m['brightness'] < DARK:
                issues.append('Foto oscura'); score -= 30
            elif m['brightness'] > BRIGHT:
                issues.append('Foto sobreexpuesta'); score -= 25
            if m['contrast'] < LOW_CONTRAST:
                issues.append('Poco contraste'); score -= 15
            if m['sharpness'] < BLURRY:
                issues.append('Foto borrosa'); score -= 30
            if not m['landscape']:
                issues.append('Foto vertical: mejor en horizontal'); score -= 10
        for h, other in seen:
            if bin(m['hash'] ^ h).count('1') <= DUP_DIST:
                issues.append('Foto repetida'); score -= 40
                break
        seen.append((m['hash'], pid))
        if issues_fp:
            issues.append('Es un plano: va al final')
        photos.append({'photo_id': pid, 'score': max(score, 0), 'brightness': m['brightness'],
                       'contrast': m['contrast'], 'sharpness': m['sharpness'], 'is_floorplan': issues_fp,
                       'issues': issues})
        meta[pid] = {'landscape': m['landscape'], 'bad': False}
    # order: best non-floorplan landscape first (cover), then the rest by score, floor plans last, repeats near the end
    def key(p):
        dup = 'Foto repetida' in p['issues']
        land = meta[p['photo_id']]['landscape']
        return (p['is_floorplan'], dup, not land, -p['score'], p['photo_id'])
    order = [p['photo_id'] for p in sorted(photos, key=key)]
    tips = []
    n = len(photos)
    if n < MIN_PHOTOS:
        tips.append('Agrega al menos %d fotos (hoy tienes %d)' % (MIN_PHOTOS, n))
    by_id = {p['photo_id']: p for p in photos}
    first = photos[0] if photos else None
    if first and order and order[0] != first['photo_id'] and not by_id[order[0]]['is_floorplan']:
        pos = [p['photo_id'] for p in photos].index(order[0]) + 1
        if first['brightness'] is not None and first['brightness'] < DARK:
            tips.append('La portada está oscura: cambia a la foto %d, que es la mejor de la galería' % pos)
        elif 'Foto borrosa' in first['issues']:
            tips.append('La portada está borrosa: cambia a la foto %d, que es la mejor de la galería' % pos)
        else:
            tips.append('Usa como portada la foto %d: es la mejor de la galería' % pos)
    blur = sum(1 for p in photos if 'Foto borrosa' in p['issues'])
    if blur:
        tips.append('Hay %d %s borrosa%s: vuelve a tomarla%s' % (blur, 'foto' if blur == 1 else 'fotos', '' if blur == 1 else 's', '' if blur == 1 else 's'))
    dark = sum(1 for p in photos if 'Foto oscura' in p['issues'])
    if dark:
        tips.append('Hay %d %s oscura%s: abre cortinas y enciende las luces' % (dark, 'foto' if dark == 1 else 'fotos', '' if dark == 1 else 's'))
    dups = sum(1 for p in photos if 'Foto repetida' in p['issues'])
    if dups:
        tips.append('Hay %d %s repetida%s: elimínala%s' % (dups, 'foto' if dups == 1 else 'fotos', '' if dups == 1 else 's', '' if dups == 1 else 's'))
    if n and not any(p['is_floorplan'] for p in photos):
        tips.append('Si tienes el plano, súbelo: ayuda a decidir la visita')
    return {'photos': photos, 'suggested_order': order, 'tips': tips}
