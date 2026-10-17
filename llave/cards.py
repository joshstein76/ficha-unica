"""Share cards: a branded 1080x1350 (Instagram 4:5) or 1080x1920 (story) JPEG per listing.

Fonts: production should bundle Figtree (OFL) and point LLAVE_CARD_FONT at it for brand consistency;
the macOS system fonts below are only a local-dev fallback.
"""
import hashlib
import io
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

from llave import db
from llave.web.common import facts_line, money, nice_date
from llave.web.styles import on_accent

W = 1080
KINDS = {'post': (1080, 1350, 0.62), 'story': (1080, 1920, 0.58)}
DEFAULT_ACCENT = '#1f4e79'
_BOLD = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf']
_REG = ['/System/Library/Fonts/Supplemental/Arial.ttf']
_COMMON = ['/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf']
FONT_USED = {}  # last font path chosen per weight (for diagnostics/tests)


def _font(size, bold=False):
    env = os.environ.get('LLAVE_CARD_FONT')
    for path in ([env] if env else []) + (_BOLD if bold else _REG) + _COMMON:
        if path and os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size)
                FONT_USED['bold' if bold else 'regular'] = path
                return f
            except Exception:
                continue
    FONT_USED['bold' if bold else 'regular'] = 'PIL default'
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _tw(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def _fit_one_line(draw, text, bold, size, max_w, min_size=18):
    """Shrink the font until text fits max_w; if still too wide, truncate with an ellipsis."""
    while True:
        f = _font(size, bold)
        if _tw(draw, text, f) <= max_w or size <= min_size:
            break
        size -= 2
    if _tw(draw, text, f) > max_w:
        t = text
        while len(t) > 1 and _tw(draw, t + '…', f) > max_w:
            t = t[:-1]
        text = t.rstrip() + '…'
    return text, f


def _wrap(draw, text, font, max_w, max_lines=2):
    words = (text or '').split()
    lines, cur = [], ''
    i = 0
    while i < len(words):
        trial = (cur + ' ' + words[i]).strip()
        if _tw(draw, trial, font) <= max_w or not cur:
            cur = trial
            i += 1
        else:
            lines.append(cur)
            cur = ''
            if len(lines) == max_lines:
                break
    else:
        if cur:
            lines.append(cur)
        cur = None
    truncated = cur is not None or len(lines) > max_lines
    lines = lines[:max_lines]
    if truncated and lines:
        last = lines[-1]
        while len(last) > 1 and _tw(draw, last + '…', font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + '…'
    # a single unbroken word can still be wider than the line
    out = []
    for ln in lines:
        while len(ln) > 1 and _tw(draw, ln, font) > max_w:
            ln = ln[:-2] + '…' if not ln.endswith('…') else ln[:-2] + '…'
        out.append(ln)
    return out


def _hex(c):
    return c if re.match(r'^#[0-9a-fA-F]{6}$', c or '') else DEFAULT_ACCENT


def format_whatsapp(raw):
    """+525578358858 -> '55 7835 8858' (Mexican 10-digit national number); other numbers keep a '+' prefix."""
    d = re.sub(r'\D', '', raw or '')
    if d.startswith('52') and len(d) == 12:
        d = d[2:]
    elif d.startswith('521') and len(d) == 13:
        d = d[3:]
    if len(d) == 10:
        return '%s %s %s' % (d[:2], d[2:6], d[6:])
    return ('+' + d) if d else ''


def _first_photo_path(con, listing_id):
    row = con.execute('SELECT sizes, sha256 FROM photos WHERE listing_id=? ORDER BY position, id LIMIT 1',
                      (listing_id,)).fetchone()
    if not row:
        return None, ''
    try:
        sizes = json.loads(row['sizes'])
    except ValueError:
        return None, ''
    rel = sizes.get('1600')
    path = os.path.join(db.MEDIA_DIR, rel) if rel else None
    return (path if path and os.path.exists(path) else None), row['sha256']


def _agency_accent(con, listing_id, accent):
    if accent:
        return _hex(accent)
    r = con.execute('SELECT a.accent FROM agencies a JOIN listings l ON l.agency_id=a.id WHERE l.id=?',
                    (listing_id,)).fetchone()
    return _hex(r['accent'] if r else None)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def render(con, listing_id, kind='post', accent=None, return_texts=False):
    if kind not in KINDS:
        raise ValueError('kind must be post or story')
    c = db.canonical(con, listing_id)
    if not c:
        raise ValueError('listing not found')
    cw, ch, photo_frac = KINDS[kind]
    accent = _agency_accent(con, listing_id, accent)
    fg = on_accent(accent)
    muted = '#5b6470'
    ink = '#14181f'
    pad = 64
    maxw = cw - 2 * pad
    texts = []

    img = Image.new('RGB', (cw, ch), '#ffffff')
    photo_h = int(ch * photo_frac)
    path, _ = _first_photo_path(con, listing_id)
    if path:
        try:
            with Image.open(path) as ph:
                ph = ImageOps.exif_transpose(ph).convert('RGB')
                img.paste(ImageOps.fit(ph, (cw, photo_h), Image.LANCZOS, centering=(0.5, 0.5)), (0, 0))
        except Exception:
            path = None
    if not path:
        img.paste(Image.new('RGB', (cw, photo_h), _rgb(accent)), (0, 0))
    d = ImageDraw.Draw(img)

    # pill
    pill = 'EN RENTA' if c['operation'] == 'renta' else 'EN VENTA'
    pf = _font(34, True)
    pw, ph_ = _tw(d, pill, pf), 34
    px, py = 48, 48
    d.rounded_rectangle((px, py, px + pw + 56, py + 74), radius=37, fill='#ffffff')
    pb = d.textbbox((0, 0), pill, font=pf)
    d.text((px + 28 - pb[0], py + 37 - (pb[1] + pb[3]) / 2), pill, font=pf, fill=ink)
    texts.append(pill)

    # footer geometry
    foot_h = 130 if kind == 'post' else 180
    foot_y = ch - foot_h
    top = photo_h + (40 if kind == 'post' else 52)
    base = 1.0 if kind == 'story' else 0.86
    panel_texts = []
    for scale in (base, base * .92, base * .84, base * .76, base * .68):
        panel_texts = []
        panel = Image.new('RGB', (cw, foot_y - photo_h), '#ffffff')
        pd = ImageDraw.Draw(panel)
        y = top - photo_h

        price_txt, f = _fit_one_line(pd, money(c['price'], c['currency']), True, int(104 * scale), maxw)
        pd.text((pad, y), price_txt, font=f, fill=ink)
        panel_texts.append(price_txt)
        y += pd.textbbox((0, 0), 'Ag', font=f)[3] + int(22 * scale)

        tf = _font(int(48 * scale), True)
        for ln in _wrap(pd, c['title'] or '', tf, maxw, 2):
            pd.text((pad, y), ln, font=tf, fill=ink)
            panel_texts.append(ln)
            y += int(48 * scale * 1.25)
        y += int(10 * scale)

        addr = c['address']
        rows = [(facts_line(c), 34), (', '.join(x for x in (addr.get('colonia'), addr.get('municipio')) if x), 34)]
        if c.get('price_date'):
            rows.append(('Precio al ' + nice_date(c['price_date']), 26))
        for text, size in rows:
            if not text:
                continue
            size = int(size * scale)
            t, sf = _fit_one_line(pd, text, False, size, maxw)
            pd.text((pad, y), t, font=sf, fill=muted)
            panel_texts.append(t)
            y += int(size * 1.4)
        if y <= foot_y - photo_h - 16:
            break
    img.paste(panel, (0, photo_h))
    texts += panel_texts
    d = ImageDraw.Draw(img)

    # footer bar
    d.rectangle((0, foot_y, cw, ch), fill=accent)
    name = c['agency']['name'] or ''
    wa = format_whatsapp(c['agency']['whatsapp'])
    right_w = int(maxw * 0.46)
    nm, nf = _fit_one_line(d, name, True, 40, maxw - right_w - 24 if wa else maxw)
    cy = foot_y + foot_h // 2
    nb = d.textbbox((0, 0), nm, font=nf)
    d.text((pad - nb[0], cy - (nb[1] + nb[3]) / 2), nm, font=nf, fill=fg)
    texts.append(nm)
    if wa:
        lab, lf = _fit_one_line(d, 'Escríbenos por WhatsApp', False, 26, right_w)
        num, numf = _fit_one_line(d, wa, True, 44, right_w)
        lh = d.textbbox((0, 0), lab, font=lf)
        nh = d.textbbox((0, 0), num, font=numf)
        d.text((cw - pad - _tw(d, lab, lf) - lh[0], cy - 44), lab, font=lf, fill=fg)
        d.text((cw - pad - _tw(d, num, numf) - nh[0], cy - 6), num, font=numf, fill=fg)
        texts += [lab, num]

    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=88)  # no exif/icc passed -> no metadata
    data = buf.getvalue()
    return (data, texts) if return_texts else data


def _hash(con, listing_id, kind, accent):
    c = db.canonical(con, listing_id)
    _, sha = _first_photo_path(con, listing_id)
    key = '|'.join(str(x) for x in (c['updated_at'], c['price_cents'], c['title'], sha,
                                    _agency_accent(con, listing_id, accent), c['agency']['name'],
                                    c['agency']['whatsapp'], c['operation'], kind))
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


def render_cached(con, listing_id, kind='post', accent=None):
    """Returns the relative path (under MEDIA_DIR) of the card, regenerating when inputs change."""
    h = _hash(con, listing_id, kind, accent)
    rel = 'cards/%s-%s-%s.jpg' % (listing_id, kind, h)
    full = os.path.join(db.MEDIA_DIR, rel)
    if not os.path.exists(full):
        data = render(con, listing_id, kind, accent)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        for old in _stale(os.path.dirname(full), listing_id, kind):
            try:
                os.remove(old)
            except OSError:
                pass
        with open(full, 'wb') as fh:
            fh.write(data)
    return rel


def _stale(folder, listing_id, kind):
    pre = '%s-%s-' % (listing_id, kind)
    return [os.path.join(folder, n) for n in os.listdir(folder) if n.startswith(pre) and n.endswith('.jpg')]
