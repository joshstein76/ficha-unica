"""Photo pipeline: validate, strip all metadata, resize (1600/800/400), JPEG + WebP, dedupe by sha256."""
import hashlib
import io
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont, ImageOps

from llave import db

SIZES = (1600, 800, 400)
MIN_SIDE = 600
MAX_RATIO = 2.6
MIN_RATIO = 0.38


def _watermark(img, text):
    w, h = img.size
    fs = max(12, int(min(w, h) * 0.035))
    try:
        font = ImageFont.load_default(size=fs)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    base = img.convert('RGBA')
    layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = w - tw - int(w * 0.02) - box[0], h - th - int(h * 0.02) - box[1]
    off = max(1, fs // 14)
    d.text((x + off, y + off), text, font=font, fill=(0, 0, 0, 90))
    d.text((x, y), text, font=font, fill=(255, 255, 255, 89))  # ~35% opacity
    return Image.alpha_composite(base, layer).convert('RGB')


def _resized(img, long_edge):
    w, h = img.size
    if max(w, h) <= long_edge:
        return img.copy()
    k = long_edge / float(max(w, h))
    return img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)


def ingest(con, listing_id, data, alt=None, watermark_text=None):
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError('No se pudo leer la imagen: sube un archivo JPG, PNG o WebP')
    img = ImageOps.exif_transpose(img).convert('RGB')
    w, h = img.size
    if min(w, h) < MIN_SIDE:
        raise ValueError('La foto es muy pequeña: mínimo 600 px')
    ratio = w / float(h)
    if ratio > MAX_RATIO or ratio < MIN_RATIO:
        raise ValueError('Parece un banner o logo, no una foto de la propiedad')
    sha = hashlib.sha256(data).hexdigest()
    dup = con.execute('SELECT id FROM photos WHERE listing_id=? AND sha256=?', (listing_id, sha)).fetchone()
    if dup:
        return dup['id']
    rel = '%s/%s' % (sha[:2], sha)
    folder = os.path.join(db.MEDIA_DIR, sha[:2], sha)
    os.makedirs(folder, exist_ok=True)
    sizes = {}
    dims = (w, h)
    for s in SIZES:
        im = _resized(img, s)
        if s == 1600:
            dims = im.size
        if watermark_text and s in (1600, 800):
            im = _watermark(im, watermark_text)
        clean = Image.new('RGB', im.size)  # fresh image: no info/EXIF/ICC carried over
        clean.paste(im)
        clean.save(os.path.join(folder, '%d.jpg' % s), 'JPEG', quality=82, progressive=True, optimize=True)
        clean.save(os.path.join(folder, '%d.webp' % s), 'WEBP', quality=80)
        sizes[str(s)] = '%s/%d.jpg' % (rel, s)
        sizes['%dw' % s] = '%s/%d.webp' % (rel, s)
    pos = con.execute('SELECT COALESCE(MAX(position), -1) + 1 FROM photos WHERE listing_id=?', (listing_id,)).fetchone()[0]
    cur = con.execute('INSERT INTO photos(listing_id, position, sha256, width, height, sizes, alt) VALUES (?,?,?,?,?,?,?)',
                      (listing_id, pos, sha, dims[0], dims[1], json.dumps(sizes), alt))
    con.commit()
    return cur.lastrowid


def reorder(con, listing_id, photo_ids_in_order):
    for pos, pid in enumerate(photo_ids_in_order):
        con.execute('UPDATE photos SET position=? WHERE id=? AND listing_id=?', (pos, pid, listing_id))
    con.commit()


def delete(con, photo_id):
    row = con.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
    if not row:
        return False
    con.execute('DELETE FROM photos WHERE id=?', (photo_id,))
    con.commit()
    sha = row['sha256']
    if not con.execute('SELECT 1 FROM photos WHERE sha256=? LIMIT 1', (sha,)).fetchone():
        shutil.rmtree(os.path.join(db.MEDIA_DIR, sha[:2], sha), ignore_errors=True)
        try:
            os.rmdir(os.path.join(db.MEDIA_DIR, sha[:2]))
        except OSError:
            pass
    return True
