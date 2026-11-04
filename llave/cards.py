"""Share cards in the Lotería look: every listing becomes a card an agent forwards to WhatsApp groups and posts on Instagram.

Kinds (JPEG, no metadata):
  post         1080x1350  (Instagram 4:5, WhatsApp)        story        1080x1920  (Instagram / WhatsApp status)
  enlace       1200x630   (link preview of the public page when the listing has no photo)
  cierre_post  1080x1350  ¡Vendida! / ¡Rentada!            cierre_story 1080x1920  (only for sold / rented listings)
Each card is a lotería card on a wall in the agent's accent colour: thick ink outline, hard offset shadow, a number in the
corner, the photo in the frame, a price sticker, the title, facts, colonia, and the agent's name + WhatsApp. A small
"Hecho con Ficha Única · fichaunica.mx" line sits under the card (the growth loop; there is no way to remove it).

Fonts: Figtree (SIL OFL) is bundled in llave/card_assets/fonts, so the server never needs system fonts and never falls back to
PIL's default font. Shrikhand (titles) and Bricolage Grotesque ExtraBold (prices) are used when their files are in that folder
(or in LLAVE_CARD_FONTS_DIR); otherwise bold Figtree with a thicker outline. LLAVE_CARD_FONT=/path/font.ttf forces one font.
Everything is drawn at 2x and scaled down, so edges and text are smooth. Our own art only: no classic lotería deck names or drawings.
"""
import hashlib
import io
import json
import math
import os
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps

from llave import db
from llave.web.common import TYPES, facts_line, label, money, nice_date

CARD_VERSION = 'loteria-1'  # bump when the drawing changes: cached cards from older code are regenerated

# ---------- brand tokens (docs: the Lotería design system) ----------
TINTA, PAPEL, BLANCO = '#1B1236', '#FFF9EE', '#FFFFFF'
CEMPA, CHILE, JACARANDA, ROSA, NOPAL, CIELO, SUAVE = '#FFB800', '#FF4F1F', '#5B2EE6', '#FF4FA3', '#0FB56D', '#37C5F2', '#5E5478'
DEFAULT_ACCENT = CEMPA
BRAND_LINE = 'Hecho con Ficha Única · fichaunica.mx'

SS = 2  # supersampling: layout is in 1080-wide "logical" pixels, drawing happens at SS x
KINDS = {
    'post': {'w': 1080, 'h': 1350, 'closed': False},
    'story': {'w': 1080, 'h': 1920, 'closed': False},
    'enlace': {'w': 1200, 'h': 630, 'closed': False},
    'cierre_post': {'w': 1080, 'h': 1350, 'closed': True},
    'cierre_story': {'w': 1080, 'h': 1920, 'closed': True},
}
W = 1080

# ---------- fonts ----------
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'card_assets')
BUNDLED_FONTS = os.path.join(ASSETS, 'fonts')
BODY_FILE, BOLD_FILE = 'Figtree-500.ttf', 'Figtree-600.ttf'
DISPLAY_FILES = ('Shrikhand-Regular.ttf', 'Shrikhand.ttf')
PRICE_FILES = ('BricolageGrotesque-ExtraBold.ttf', 'BricolageGrotesque-Bold.ttf',
               'BricolageGrotesque[opsz,wdth,wght].ttf', 'BricolageGrotesque-Variable.ttf')
FAUX_BOLD = 0.017  # bold Figtree standing in for the display fonts: outline each letter by this share of its size
# Dev machines only, last resort after the bundled fonts (the server has none of these).
SYSTEM_FONTS = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Helvetica.ttc',
                '/Library/Fonts/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
FONT_USED = {}  # last font path chosen per role (diagnostics + tests): 'PIL default' means nothing could be loaded
_FONT_CACHE = {}


def _font_dirs():
    env = os.environ.get('LLAVE_CARD_FONTS_DIR')
    return ([env] if env else []) + [BUNDLED_FONTS]


def _find(names):
    for d in _font_dirs():
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


def _candidates(role):
    """[(path, faux_bold_ratio)] in the order to try for a role: text | bold | display (titles) | price."""
    heavy = role in ('display', 'price')
    out = []
    env = os.environ.get('LLAVE_CARD_FONT')
    if env and os.path.isfile(env):
        out.append((env, FAUX_BOLD if heavy else 0))
    brand = _find(DISPLAY_FILES) if role == 'display' else _find(PRICE_FILES) if role == 'price' else None
    if brand:
        out.append((brand, 0))
    bundled = _find((BODY_FILE,) if role == 'text' else (BOLD_FILE,))
    if bundled:
        out.append((bundled, FAUX_BOLD if heavy else 0))
    out += [(p, FAUX_BOLD if heavy else 0) for p in SYSTEM_FONTS if os.path.isfile(p)]
    return out


def _variable(font, px):
    """Bricolage ships as one variable file: ask for weight 800 and the condensed width the brand uses."""
    try:
        axes = font.get_variation_axes()
    except Exception:
        return  # a static font
    vals = []
    for ax in axes:
        name = ax['name'].decode('latin-1') if isinstance(ax['name'], bytes) else str(ax['name'])
        name = name.lower()
        want = ax['default']
        if 'weight' in name:
            want = 800
        elif 'width' in name:
            want = 80
        elif 'optical' in name or name == 'opsz':
            want = px / SS
        vals.append(max(ax['minimum'], min(ax['maximum'], want)))
    try:
        font.set_variation_by_axes(vals)
    except Exception:
        pass


def _load(role, px):
    for path, faux in _candidates(role):
        key = (path, px)
        try:
            if key not in _FONT_CACHE:
                f = ImageFont.truetype(path, px)
                if role == 'price' and ('wght' in path or 'Variable' in path):
                    _variable(f, px)
                _FONT_CACHE[key] = f
            FONT_USED[role] = path
            return _FONT_CACHE[key], faux, path
        except Exception:
            continue
    FONT_USED[role] = 'PIL default'
    try:
        return ImageFont.load_default(size=px), 0, 'PIL default'
    except TypeError:
        return ImageFont.load_default(), 0, 'PIL default'


def fonts_signature():
    """Which font file each role uses right now: part of the cache key, so adding the brand fonts regenerates the cards."""
    parts = []
    for role in ('text', 'bold', 'display', 'price'):
        c = _candidates(role)
        parts.append('%s=%s' % (role, os.path.basename(c[0][0]) if c else 'default'))
    return ','.join(parts)


class Face:
    """A font at one size (logical px) with its measuring and the 'bold' stroke. Widths come back in logical px."""
    def __init__(self, role, size):
        self.size = size
        self.px = max(6, int(round(size * SS)))
        self.font, faux, self.path = _load(role, self.px)
        self.stroke = int(round(self.px * faux))
        self._cap = None

    def bbox(self, text):
        """Ink box in SS px, origin at the left end of the baseline."""
        try:
            return self.font.getbbox(text, anchor='ls', stroke_width=self.stroke)
        except TypeError:  # very old Pillow
            b = self.font.getbbox(text, stroke_width=self.stroke)
            return (b[0], b[1] - self.px, b[2], b[3] - self.px)

    def w(self, text):
        b = self.bbox(text)
        return (b[2] - b[0]) / float(SS)

    @property
    def cap(self):
        if self._cap is None:
            self._cap = -self.bbox('H')[1] / float(SS)
        return self._cap


def get_face(role, size):
    return Face(role, size)


# ---------- text helpers ----------
def clean(text):
    """Text for a card: no emoji, symbols or scripts the fonts lack (they would print as empty boxes), one line, single spaces."""
    t = unicodedata.normalize('NFC', str(text or ''))
    out = []
    for ch in t:
        cat = unicodedata.category(ch)
        o = ord(ch)
        if cat in ('Cc', 'Zl', 'Zp', 'Zs'):
            out.append(' ')
        elif cat in ('So', 'Cs', 'Cf', 'Cn', 'Co', 'Sk') and ch not in '°':
            continue
        elif o < 0x250 or 0x2000 <= o <= 0x206F or 0x20A0 <= o <= 0x20CF:
            out.append(ch)
    return re.sub(r' +', ' ', ''.join(out)).strip()


def _ellipsize(text, face, max_w):
    """Cut text so that text + '…' fits max_w, at a word boundary when there is one to cut at."""
    t = text
    while t and face.w(t.rstrip() + '…') > max_w:
        t = t[:-1]
    if t and not text[len(t):len(t) + 1].isspace() and ' ' in t.strip():
        t = t[:t.rstrip().rfind(' ')]  # drop the half word
    return (t.rstrip(' ,;:.-') + '…') if t.strip() else '…'


def fit_line(text, role, size, max_w, min_size=18, step=2):
    """One line: shrink the font until it fits max_w; at the minimum size cut it with an ellipsis."""
    s = size
    while True:
        f = get_face(role, s)
        if f.w(text) <= max_w or s <= min_size:
            break
        s -= step
    if f.w(text) > max_w:
        text = _ellipsize(text, f, max_w)
    return text, f


def _wrap(text, face, max_w, max_lines):
    words = text.split()
    lines, cur, truncated = [], '', False
    while words:
        w = words[0]
        trial = (cur + ' ' + w) if cur else w
        if face.w(trial) <= max_w:
            cur = trial
            words.pop(0)
            continue
        if cur:
            lines.append(cur)
            cur = ''
        else:  # one word wider than the line: break it by letters
            cut = w
            while len(cut) > 1 and face.w(cut) > max_w:
                cut = cut[:-1]
            lines.append(cut)
            rest = w[len(cut):]
            if rest:
                words[0] = rest
            else:
                words.pop(0)
        if len(lines) == max_lines:
            truncated = bool(words)
            break
    else:
        if cur:
            lines.append(cur)
    if truncated and lines:
        lines[-1] = _ellipsize(lines[-1], face, max_w)
    return lines, truncated


def fit_wrap(text, role, sizes, max_w, max_lines):
    """Largest size (from `sizes`, big to small) whose text fits in max_lines; at the smallest, the last line gets an ellipsis."""
    lines, f = [], None
    for s in sizes:
        f = get_face(role, s)
        lines, truncated = _wrap(text, f, max_w, max_lines)
        if not truncated:
            break
    return lines, f


# ---------- colour helpers ----------
def _hex(c):
    return c if re.match(r'^#[0-9a-fA-F]{6}$', c or '') else DEFAULT_ACCENT


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % tuple(int(round(x + (y - x) * t)) for x, y in zip(ra, rb))


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))))


def _sticker_color(accent, prefer=(CHILE, CEMPA, ROSA, NOPAL)):
    """The price sticker is chile unless the agent's colour is too close to it to stand out."""
    for c in prefer:
        if _dist(c, accent) > 80:
            return c
    return BLANCO


# ---------- the canvas ----------
class Canvas:
    """Draws in logical px (1080 wide) at SS x. Records every text drawn (and its ink box) for the tests."""
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.img = Image.new('RGB', (w * SS, h * SS), bg)
        self.d = ImageDraw.Draw(self.img)
        self.texts = []
        self.boxes = []  # (text, ink box in logical px, the container it must stay inside)

    def s(self, v):
        return int(round(v * SS))

    def box(self, b):
        return tuple(self.s(v) for v in b)

    def rrect(self, b, r, fill=None, outline=None, width=0):
        self.d.rounded_rectangle(self.box(b), radius=self.s(r), fill=fill, outline=outline, width=self.s(width) if outline else 0)

    def rect(self, b, fill):
        self.d.rectangle(self.box(b), fill=fill)

    def paste(self, im, xy, mask=None):
        self.img.paste(im, (self.s(xy[0]), self.s(xy[1])), mask)

    def text(self, x, base, text, face, fill, align='l', limit=None):
        """x is the left, centre or right edge of the ink; base is the baseline (logical px)."""
        _text_on(self.d, self.s(x), self.s(base), text, face, fill, align)
        l, t, r, b = face.bbox(text)
        X, Y = self.s(x), self.s(base)
        ox = X - l if align == 'l' else X - (l + r) / 2.0 if align == 'c' else X - r
        self.texts.append(text)
        self.boxes.append((text, ((ox + l) / SS, (Y + t) / SS, (ox + r) / SS, (Y + b) / SS), limit))

    def text_mid(self, x, cy, text, face, fill, align='l', limit=None):
        """Same, vertically centred on cy by cap height (so digits and caps sit in the middle of their chip)."""
        self.text(x, cy + face.cap / 2.0, text, face, fill, align, limit)


def _text_on(d, X, Y, text, face, fill, align='l'):
    """Text on any ImageDraw at SS px: ink box edge at X, baseline at Y."""
    l, t, r, b = face.bbox(text)
    ox = X - l if align == 'l' else X - (l + r) / 2.0 if align == 'c' else X - r
    d.text((ox, Y), text, font=face.font, fill=fill, anchor='ls', stroke_width=face.stroke, stroke_fill=fill)


# ---------- art ----------
def _sunburst(size, center, c1, c2, step=15):
    """Alternating rays from a centre (the lotería sunburst): size and centre in SS px."""
    w, h = size
    im = Image.new('RGB', (w, h), c2)
    d = ImageDraw.Draw(im)
    cx, cy = center
    big = math.hypot(max(cx, w - cx), max(cy, h - cy)) * 1.3
    for i in range(0, 360 // step, 2):
        a0, a1 = math.radians(i * step - 90), math.radians((i + 1) * step - 90)
        d.polygon([(cx, cy), (cx + big * math.cos(a0), cy + big * math.sin(a0)), (cx + big * math.cos(a1), cy + big * math.sin(a1))], fill=c1)
    return im


def _mark(px):
    key = ('mark', px)
    if key not in _FONT_CACHE:
        with Image.open(os.path.join(ASSETS, 'ficha-unica-mark-512.png')) as m:
            _FONT_CACHE[key] = m.convert('RGBA').resize((px, px), Image.LANCZOS)
    return _FONT_CACHE[key]


def _mark_sticker(cv, cx, cy, size, shadow=6):
    """The Ficha Única mark with its hard shadow, centred on (cx, cy)."""
    m = _mark(cv.s(size))
    sh = Image.new('RGBA', m.size, _rgb(TINTA) + (255,))
    sh.putalpha(m.getchannel('A'))
    x, y = cv.s(cx - size / 2.0), cv.s(cy - size / 2.0)
    cv.img.paste(sh, (x + cv.s(shadow), y + cv.s(shadow)), sh)
    cv.img.paste(m, (x, y), m)


def _casa(d, X, Y, size, sun, ink=TINTA):
    """'La Casa', our own little house drawing (shown when a listing has no photo yet). X, Y, size are SS px."""
    k = size / 100.0
    lw = max(2, int(round(3 * k)))

    def P(px, py):
        return (X + px * k, Y + py * k)

    def outlined(points, fill):
        pts = [P(*p) for p in points]
        d.polygon(pts, fill=fill)
        d.line(pts + [pts[0], pts[1]], fill=ink, width=lw, joint='curve')

    cx, cy = P(76, 24)
    r = 12 * k
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sun, outline=ink, width=lw)
    outlined([(24, 46), (76, 46), (76, 86), (24, 86)], BLANCO)
    outlined([(14, 50), (50, 18), (86, 50)], CHILE)
    outlined([(45, 60), (61, 60), (61, 86), (45, 86)], JACARANDA)
    outlined([(30, 56), (40, 56), (40, 67), (30, 67)], CIELO)


def _pin(cv, cx, cy, size, fill=CHILE):
    r = size * 0.36
    top = cy - size * 0.18
    cv.d.polygon([(cv.s(cx - r * 0.86), cv.s(top + r * 0.5)), (cv.s(cx + r * 0.86), cv.s(top + r * 0.5)), (cv.s(cx), cv.s(cy + size * 0.5))], fill=TINTA)
    cv.d.ellipse((cv.s(cx - r - 2), cv.s(top - r - 2), cv.s(cx + r + 2), cv.s(top + r + 2)), fill=TINTA)
    ri = r * 0.82
    cv.d.ellipse((cv.s(cx - ri), cv.s(top - ri), cv.s(cx + ri), cv.s(top + ri)), fill=fill)
    cv.d.ellipse((cv.s(cx - r * 0.34), cv.s(top - r * 0.34), cv.s(cx + r * 0.34), cv.s(top + r * 0.34)), fill=TINTA)


def _sticker(cv, cx, cy, w, h, angle, fill, lines, radius=22, outline=7, shadow=9, limit=None):
    """A rounded sticker with ink outline and hard shadow, tilted a little. lines = [(text, face, baseline offset from centre, colour)]."""
    pad = 24
    lw, lh = cv.s(w + 2 * pad), cv.s(h + 2 * pad)
    layer = Image.new('RGBA', (lw, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0 = cv.s(pad), cv.s(pad)
    x1, y1 = x0 + cv.s(w), y0 + cv.s(h)
    d.rounded_rectangle((x0 + cv.s(shadow), y0 + cv.s(shadow), x1 + cv.s(shadow), y1 + cv.s(shadow)), radius=cv.s(radius), fill=TINTA)
    d.rounded_rectangle((x0, y0, x1, y1), radius=cv.s(radius), fill=fill, outline=TINTA, width=cv.s(outline))
    for text, face, dy, color in lines:
        _text_on(d, (x0 + x1) // 2, (y0 + y1) // 2 + cv.s(dy), text, face, color, 'c')
        l, t, r, b = face.bbox(text)
        cv.texts.append(text)
        cv.boxes.append((text, (cx - (r - l) / 2.0 / SS, cy + dy + t / float(SS), cx + (r - l) / 2.0 / SS, cy + dy + b / float(SS)),
                         limit))
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    cv.img.paste(layer, (cv.s(cx) - layer.width // 2, cv.s(cy) - layer.height // 2), layer)


def _photo_frame(cv, box, path, accent, sun, r=26):
    """The picture in its frame. Landscape photos fill it; tall ones are shown whole on the sunburst; no photo = La Casa."""
    fx0, fy0, fx1, fy1 = box
    fw, fh = fx1 - fx0, fy1 - fy0
    size = (cv.s(fw), cv.s(fh))
    base = _sunburst(size, (size[0] // 2, size[1] // 2), _mix(accent, '#ffffff', .26), accent)
    ph = None
    if path:
        try:
            with Image.open(path) as im:
                ph = ImageOps.exif_transpose(im).convert('RGB')
        except Exception:
            ph = None
    if ph is None:
        inner = base
        side = min(size) * 0.62
        _casa(ImageDraw.Draw(inner), (size[0] - side) / 2.0, (size[1] - side) / 2.0 + size[1] * 0.03, side, sun)
    else:
        ratio = ph.width / float(ph.height)
        if ratio >= 0.8 * (fw / float(fh)):
            inner = ImageOps.fit(ph, size, Image.LANCZOS, centering=(0.5, 0.42))
        else:
            inner = base
            mh = fh - 44
            mw = min(mh * ratio, fw - 44)
            mh = mw / ratio
            pw, phh = cv.s(mw), cv.s(mh)
            px, py = (size[0] - pw) // 2, (size[1] - phh) // 2
            d = ImageDraw.Draw(inner)
            d.rounded_rectangle((px + cv.s(10), py + cv.s(10), px + pw + cv.s(10), py + phh + cv.s(10)), radius=cv.s(14), fill=TINTA)
            fitted = ph.resize((pw, phh), Image.LANCZOS)
            m = Image.new('L', (pw, phh), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, pw - 1, phh - 1), radius=cv.s(14), fill=255)
            inner.paste(fitted, (px, py), m)
            d.rounded_rectangle((px, py, px + pw, py + phh), radius=cv.s(14), outline=TINTA, width=cv.s(5))
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=cv.s(r), fill=255)
    cv.img.paste(inner, (cv.s(fx0), cv.s(fy0)), mask)
    cv.rrect(box, r, outline=TINTA, width=6)
    return ph is not None


# ---------- the spec: everything a card shows (also the cache key) ----------
def _card_number(ref, lid):
    m = re.search(r'(\d+)\D*$', ref or '')
    n = int(m.group(1)) if m else lid
    return str(n % 1000000)


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
    r = con.execute('SELECT a.accent FROM agencies a JOIN listings l ON l.agency_id=a.id WHERE l.id=?', (listing_id,)).fetchone()
    return _hex(r['accent'] if r else None)


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


MONEY_WORDS = re.compile(r'(\$|\bUS\b|\bMXN\b|\bUSD\b|\bMDP\b|\bMDD\b|\bMN\b|\bpesos\b|\bd[oó]lares\b|\bmillones?\b|\bmil\b)', re.I)


def addr_place(c):
    a = c['address']
    return a.get('colonia') or a.get('municipio') or 'México'


def _title_has_price(title, c):
    """True when a title says what it cost (a currency sign or word, or the price's own digits)."""
    if MONEY_WORDS.search(title):
        return True
    digits = re.sub(r'(?<=\d)[,.\s](?=\d{3}\b)', '', title)
    if re.search(r'\d{5,}', digits):
        return True
    return bool(c.get('price')) and str(c['price']) in re.sub(r'\D', '', title)


def build_spec(con, listing_id, kind='post', accent=None, show_price=False):
    if kind not in KINDS:
        raise ValueError('kind must be one of %s' % ', '.join(sorted(KINDS)))
    c = db.canonical(con, listing_id)
    if not c:
        raise ValueError('listing not found')
    closed = KINDS[kind]['closed']
    if closed and c['status'] not in db.CLOSED_STATUSES:
        raise ValueError('only sold or rented listings have a closing card')
    accent = _agency_accent(con, listing_id, accent)
    path, sha = _first_photo_path(con, listing_id)
    ag, u = c['agency'], c['agent']
    person = clean((u or {}).get('name') or ag['name'])
    agency_line = clean(ag['name']) if u and clean(u.get('name')) and clean(ag['name']) and clean(ag['name']).lower() != person.lower() else ''
    addr = c['address']
    price_txt = money(c['price'], c['currency'])
    title = clean(c['title'])
    if closed and not show_price and _title_has_price(title, c):
        # the agent chose to hide the price: a title like "Depa en venta $4.5 mdp" must not give it away
        title = clean('%s en %s' % (label(TYPES, c['property_type']), addr_place(c)))
    spec = {
        'kind': kind, 'closed': closed, 'status': c['status'], 'accent': accent,
        'number': _card_number(c['ref'], c['id']),
        'title': title or clean(label(TYPES, c['property_type'])) or 'Propiedad',
        'facts': [clean(x) for x in facts_line(c).split(' · ') if x],
        'place': clean(', '.join(x for x in (addr.get('colonia'), addr.get('municipio')) if x)),
        'name': person, 'agency_line': agency_line, 'wa': format_whatsapp((u or ag)['whatsapp']),
        'photo_sha': sha if path else '',
        'photo_path': path,
        'updated_at': c['updated_at'] or '',  # not drawn: any edit to the listing regenerates its cards
    }
    if not closed:
        spec.update({'tag': 'EN RENTA' if c['operation'] == 'renta' else 'EN VENTA', 'tag_color': CIELO if c['operation'] == 'renta' else NOPAL,
                     'tag_ink': TINTA, 'price': price_txt, 'price_label': '',
                     'price_date': ('Precio al ' + nice_date(c['price_date'])) if c['price_date'] and c['price'] is not None else ''})
    else:
        rented = c['status'] == 'rentada'
        spec.update({'tag': clean(label(TYPES, c['property_type'])).upper(), 'tag_color': JACARANDA, 'tag_ink': BLANCO,
                     'stamp': '¡RENTADA!' if rented else '¡VENDIDA!',
                     'cta': '¿Quieres rentar la tuya?' if rented else '¿Quieres vender la tuya?',
                     # the price on a closing card is only ever the list price, and only when the agent chose to show it
                     'price': price_txt if (show_price and c['price'] is not None) else '',
                     'price_label': 'Precio de lista' if (show_price and c['price'] is not None) else '', 'price_date': ''})
    return spec


def _hash(spec):
    body = {k: v for k, v in spec.items() if k != 'photo_path'}
    key = '|'.join((CARD_VERSION, fonts_signature(), json.dumps(body, sort_keys=True, ensure_ascii=False)))
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


# ---------- drawing ----------
def _wall(cv, accent):
    sb = _sunburst((cv.w * SS, cv.h * SS), (cv.w * SS // 2, int(cv.h * SS * 0.54)), _mix(accent, '#ffffff', .24), accent)
    cv.img.paste(sb, (0, 0))
    cv.d = ImageDraw.Draw(cv.img)


def _attribution(cv, cx, cy):
    """'Hecho con Ficha Única · fichaunica.mx' on an ink pill with the mark: small, honest, always there."""
    f = get_face('bold', 27)
    tw = f.w(BRAND_LINE)
    mk = 46
    pw = mk + 12 + tw + 44
    ph = 58
    cv.rrect((cx - pw / 2.0, cy - ph / 2.0, cx + pw / 2.0, cy + ph / 2.0), ph / 2.0, fill=TINTA)
    m = _mark(cv.s(mk))
    cv.img.paste(m, (cv.s(cx - pw / 2.0 + 8), cv.s(cy - mk / 2.0)), m)
    cv.text_mid(cx - pw / 2.0 + 8 + mk + 12, cy, BRAND_LINE, f, PAPEL, 'l',
                (cx - pw / 2.0, cy - ph / 2.0, cx + pw / 2.0, cy + ph / 2.0))


def _chips(cv, texts, cx, cy, max_w, size=32):
    """A centred row of outlined chips; shrinks until the row fits."""
    if not texts:
        return 0
    while True:
        f = get_face('bold', size)
        padx, gap = size * 0.7, 12
        widths = [f.w(t) + 2 * padx for t in texts]
        total = sum(widths) + gap * (len(texts) - 1)
        if total <= max_w or size <= 22:
            break
        size -= 2
    if total > max_w:  # still too wide at the smallest size: keep the first chips that fit
        while len(texts) > 1 and total > max_w:
            texts, widths = texts[:-1], widths[:-1]
            total = sum(widths) + gap * (len(texts) - 1)
    h = size * 1.85
    x = cx - total / 2.0
    for t, w in zip(texts, widths):
        cv.rrect((x, cy - h / 2.0, x + w, cy + h / 2.0), h / 2.0, fill=PAPEL, outline=TINTA, width=4)
        cv.text_mid(x + w / 2.0, cy, t, f, TINTA, 'c', (x, cy - h / 2.0, x + w, cy + h / 2.0))
        x += w + gap
    return h


def _draw(spec):
    """Returns the finished card as an SS-size RGB image plus the Canvas (texts and boxes for the tests)."""
    kind = spec['kind']
    if kind == 'enlace':
        return _draw_enlace(spec)
    K = KINDS[kind]
    CW, CH = K['w'], K['h']
    closed = spec['closed']
    accent = spec['accent']
    sun = CEMPA if _dist(CEMPA, accent) > 90 else BLANCO
    cv = Canvas(CW, CH, accent)
    _wall(cv, accent)

    R, OUT, SH, PAD = 36, 8, 16, 26
    story = kind.endswith('story')
    x0, x1 = 48, CW - 48 - SH
    y0, y1 = (230, 1600) if story else (48, 1240)
    band_h = (170 if story else 150) if closed else (140 if story else 124)
    band_top = y1 - OUT - band_h
    cv.rrect((x0 + SH, y0 + SH, x1 + SH, y1 + SH), R, fill=TINTA)          # hard shadow
    cv.rrect((x0, y0, x1, y1), R, fill=TINTA)                              # the card's ink outline (and, at the bottom, its band)
    cv.rrect((x0 + OUT, y0 + OUT, x1 - OUT, band_top + R), R - OUT, fill=BLANCO)
    cv.rect((x0 + OUT, band_top, x1 - OUT, band_top + R), TINTA)           # square the face's bottom corners: the band meets it flat
    ix0, ix1 = x0 + OUT + PAD, x1 - OUT - PAD
    iw = ix1 - ix0
    cx = (x0 + x1) / 2.0
    face_box = (x0 + OUT, y0 + OUT, x1 - OUT, band_top)

    # header: number chip + tag
    ry = y0 + OUT + PAD
    chip = 78
    nt, nf = fit_line(spec['number'], 'price', 46, 150, 30)
    chip_w = max(chip, nf.w(nt) + 36)
    cv.rrect((ix0, ry, ix0 + chip_w, ry + chip), 24, fill=ROSA, outline=TINTA, width=5)
    cv.text_mid(ix0 + chip_w / 2.0, ry + chip / 2.0, nt, nf, TINTA, 'c', (ix0, ry, ix0 + chip_w, ry + chip))
    tag_max = iw - chip_w - 16 - 120
    tt, tf = fit_line(spec['tag'], 'bold', 30, tag_max - 44, 20)
    tw = tf.w(tt) + 44
    th = 62
    tx = ix0 + chip_w + 16
    cv.rrect((tx, ry + (chip - th) / 2.0, tx + tw, ry + (chip - th) / 2.0 + th), th / 2.0, fill=spec['tag_color'], outline=TINTA, width=5)
    cv.text_mid(tx + tw / 2.0, ry + chip / 2.0, tt, tf, spec['tag_ink'], 'c', (tx, ry, tx + tw, ry + chip))

    # what goes under the photo (measured first, so the photo takes whatever height is left)
    price_txt = spec['price']
    has_sticker = bool(price_txt)
    sticker = None
    if has_sticker:
        two = bool(spec['price_label'])
        pt, pf = fit_line(price_txt, 'price', 88 if not two else 76, iw - 90, 34)
        sw = min(iw - 30, pf.w(pt) + 76)
        sh_ = pf.cap + (44 if not two else 92)
        sticker = (pt, pf, sw, sh_)
    date_txt = spec['price_date']
    title_sizes = list(range(66 if story else 62, 35, -4))
    tlines, tface = fit_wrap(spec['title'], 'display', title_sizes, iw - 10, 2)
    pitch = tface.size * 1.16
    title_h = pitch * len(tlines)
    chips_h = 58 if spec['facts'] else 0
    place_txt = spec['place']
    below = 22                                                  # padding above the band
    below += 40 + 14 if place_txt else 0
    below += chips_h + 14 if chips_h else 0
    below += title_h + 12
    below += (40 if date_txt else 0)
    below += (sticker[3] / 2.0 + 12) if sticker else 8
    p_top = ry + chip + 18
    p_bot = band_top - below
    p_bot = max(p_bot, p_top + 240)
    fbox = (ix0, p_top, ix1, p_bot)
    _photo_frame(cv, fbox, spec['photo_path'], accent, sun)
    cv.d = ImageDraw.Draw(cv.img)

    y = p_bot
    if sticker:
        pt, pf, sw, sh_ = sticker
        lines = [(pt, pf, pf.cap / 2.0 + (0 if not spec['price_label'] else 20), TINTA)]
        if spec['price_label']:
            lf = get_face('bold', 26)
            lines.append((spec['price_label'], lf, -sh_ / 2.0 + 24 + lf.cap, TINTA))
        _sticker(cv, cx - 4, p_bot, sw, sh_, 2.2, _sticker_color(accent, (NOPAL, CEMPA, CIELO, ROSA) if closed else (CHILE, CEMPA, ROSA, NOPAL)), lines, limit=(cx - sw / 2.0, p_bot - sh_ / 2.0, cx + sw / 2.0, p_bot + sh_ / 2.0))
        y = p_bot + sh_ / 2.0 + 12
    if closed:  # the stamp across the picture
        sz = 120 if not story else 128
        stt, stf = fit_line(spec['stamp'], 'display', sz, (ix1 - ix0) * 0.8 - 80, 40)
        stw, sth = stf.w(stt) + 80, stf.cap + 78
        scy = p_top + (p_bot - p_top) * (0.42 if sticker else 0.5)
        _sticker(cv, cx, scy, stw, sth, -7, CHILE, [(stt, stf, stf.cap / 2.0, TINTA)], radius=24, outline=8, shadow=11,
                 limit=(cx - stw / 2.0, scy - sth / 2.0, cx + stw / 2.0, scy + sth / 2.0))
    if date_txt:
        df = get_face('bold', 26)
        cv.text_mid(cx, y + 22, date_txt, df, SUAVE, 'c', (ix0, y, ix1, y + 34))
        y += 40
    y += 6
    for ln in tlines:                                           # title
        cv.text(cx, y + tface.size * 0.95, ln, tface, TINTA, 'c', (ix0, p_top, ix1, band_top))
        y += pitch
    y += 12
    if chips_h:
        _chips(cv, spec['facts'], cx, y + chips_h / 2.0, iw)
        y += chips_h + 14
    if place_txt:
        pf2, pad_pin = get_face('bold', 34), 40
        pt2, pf2 = fit_line(place_txt, 'bold', 34, iw - pad_pin - 10, 22)
        total = pad_pin + pf2.w(pt2)
        sx = cx - total / 2.0
        _pin(cv, sx + 14, y + 20, 34)
        cv.text_mid(sx + pad_pin, y + 20, pt2, pf2, TINTA, 'l', (ix0, y, ix1, y + 42))

    # the band: the agent
    bx0, bx1 = x0 + OUT + 32, x1 - OUT - 32
    cy = band_top + band_h / 2.0
    wa = spec['wa']
    pill_w = 0
    if wa:
        lf = get_face('bold', 22)
        num, nf2 = fit_line(wa, 'price', 44, (bx1 - bx0) * 0.56 - 56, 24)
        pill_w = max(lf.w('WhatsApp'), nf2.w(num)) + 56
        ph_ = 90
        px0 = bx1 - pill_w
        cv.rrect((px0, cy - ph_ / 2.0, bx1, cy + ph_ / 2.0), 26, fill=NOPAL)
        cv.text(px0 + pill_w / 2.0, cy - ph_ / 2.0 + 28, 'WhatsApp', lf, TINTA, 'c', (px0, cy - ph_ / 2.0, bx1, cy + ph_ / 2.0))
        cv.text(px0 + pill_w / 2.0, cy + ph_ / 2.0 - 14, num, nf2, TINTA, 'c', (px0, cy - ph_ / 2.0, bx1, cy + ph_ / 2.0))
    left_w = bx1 - bx0 - (pill_w + 22 if wa else 0)
    left = (bx0, band_top + 8, bx0 + left_w, band_top + band_h)
    blines = []
    if closed:
        clines, cf = fit_wrap(spec['cta'], 'display', [40, 36, 32, 28, 26], left_w, 2)
        blines += [(t, cf, PAPEL, cf.size * 1.14) for t in clines]
    if spec['name']:
        nm, nfont = fit_line(spec['name'], 'bold', 34 if closed else 40, left_w, 22)
        blines.append((nm, nfont, PAPEL if not closed else CEMPA, nfont.size * 1.2))
    if spec['agency_line'] and not closed:
        an, af = fit_line(spec['agency_line'], 'text', 24, left_w, 18)
        blines.append((an, af, '#CFC7E4', af.size * 1.3))
    total_h = sum(h for _, _, _, h in blines)
    yy = cy - total_h / 2.0
    for t, f, col, h in blines:
        cv.text(bx0, yy + h * 0.78, t, f, col, 'l', left)
        yy += h

    _mark_sticker(cv, x1 - 38, y0 + 40, 124)
    _attribution(cv, W / 2.0, (y1 + SH + CH) / 2.0 if not story else y1 + SH + 62)
    return cv.img, cv


def _draw_enlace(spec):
    """1200x630 link preview: photo on the left, price + title on the right."""
    CW, CH = 1200, 630
    accent = spec['accent']
    sun = CEMPA if _dist(CEMPA, accent) > 90 else BLANCO
    cv = Canvas(CW, CH, accent)
    _wall(cv, accent)
    R, OUT, SH = 30, 7, 14
    x0, y0, x1, y1 = 34, 30, CW - 34 - SH, CH - 30 - SH
    cv.rrect((x0 + SH, y0 + SH, x1 + SH, y1 + SH), R, fill=TINTA)
    cv.rrect((x0, y0, x1, y1), R, fill=TINTA)
    cv.rrect((x0 + OUT, y0 + OUT, x1 - OUT, y1 - OUT), R - OUT, fill=BLANCO)
    pad = 24
    fx0, fy0, fx1, fy1 = x0 + OUT + pad, y0 + OUT + pad, x0 + OUT + pad + 470, y1 - OUT - pad
    _photo_frame(cv, (fx0, fy0, fx1, fy1), spec['photo_path'], accent, sun, r=22)
    cv.d = ImageDraw.Draw(cv.img)
    rx0, rx1 = fx1 + 30, x1 - OUT - pad
    rw = rx1 - rx0
    chip = 64
    nt, nf = fit_line(spec['number'], 'price', 38, 110, 24)
    chip_w = max(chip, nf.w(nt) + 30)
    cv.rrect((rx0, fy0, rx0 + chip_w, fy0 + chip), 20, fill=ROSA, outline=TINTA, width=4)
    cv.text_mid(rx0 + chip_w / 2.0, fy0 + chip / 2.0, nt, nf, TINTA, 'c', (rx0, fy0, rx0 + chip_w, fy0 + chip))
    tt, tf = fit_line(spec['tag'], 'bold', 26, rw - chip_w - 16 - 130, 18)
    tw = tf.w(tt) + 38
    tx = rx0 + chip_w + 14
    cv.rrect((tx, fy0 + 4, tx + tw, fy0 + chip - 4), (chip - 8) / 2.0, fill=spec['tag_color'], outline=TINTA, width=4)
    cv.text_mid(tx + tw / 2.0, fy0 + chip / 2.0, tt, tf, spec['tag_ink'], 'c', (tx, fy0, tx + tw, fy0 + chip))
    _mark_sticker(cv, x1 - 30, y0 + 32, 104, 5)
    y = fy0 + chip + 26
    lines, f = fit_wrap(spec['title'], 'display', list(range(54, 31, -4)), rw, 3)
    pitch = f.size * 1.16
    for ln in lines:
        cv.text(rx0, y + f.size * 0.86, ln, f, TINTA, 'l', (rx0, y, rx1, y + pitch))
        y += pitch
    pt, pf = fit_line(spec['price'], 'price', 66, rw - 60, 30)
    sw, sh_ = min(rw - 10, pf.w(pt) + 60), pf.cap + 40
    py = y + 22 + sh_ / 2.0
    _sticker(cv, rx0 + sw / 2.0 + 4, py, sw, sh_, -2, _sticker_color(accent), [(pt, pf, pf.cap / 2.0, TINTA)], radius=20, outline=6, shadow=8,
             limit=(rx0, py - sh_ / 2.0, rx0 + sw + 8, py + sh_ / 2.0))
    y = py + sh_ / 2.0 + 28
    if spec['place']:
        pl, plf = fit_line(spec['place'], 'bold', 30, rw - 40, 20)
        _pin(cv, rx0 + 12, y + 16, 30)
        cv.text_mid(rx0 + 36, y + 16, pl, plf, TINTA, 'l', (rx0, y, rx1, y + 36))
    bf = get_face('bold', 22)
    cv.text(rx1, fy1 - 4, 'Hecho con Ficha Única · fichaunica.mx', bf, SUAVE, 'r', (rx0, fy1 - 30, rx1, fy1 + 4))
    return cv.img, cv


# ---------- output ----------
def _encode(img_ss, size):
    img = img_ss.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=90, subsampling=0, optimize=True)  # no exif / icc passed: no metadata
    return buf.getvalue()


def render(con, listing_id, kind='post', accent=None, return_texts=False, show_price=False):
    """JPEG bytes of one card. show_price only matters for the closing cards (¡Vendida! / ¡Rentada!): default is no price."""
    spec = build_spec(con, listing_id, kind, accent, show_price)
    img, cv = _draw(spec)
    data = _encode(img, (KINDS[kind]['w'], KINDS[kind]['h']))
    return (data, cv.texts) if return_texts else data


def render_cached(con, listing_id, kind='post', accent=None, show_price=False):
    """Relative path (under MEDIA_DIR) of the card. The file name carries a hash of everything the card shows, so the card is
    regenerated as soon as the listing, the agent, the photo, the colour, the fonts or this code change, and old files are removed."""
    spec = build_spec(con, listing_id, kind, accent, show_price)
    key = kind + ('-precio' if spec['closed'] and spec['price'] else '')
    rel = 'cards/%s-%s-%s.jpg' % (listing_id, key, _hash(spec))
    full = os.path.join(db.MEDIA_DIR, rel)
    if not os.path.exists(full):
        img, _ = _draw(spec)
        data = _encode(img, (KINDS[kind]['w'], KINDS[kind]['h']))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = '%s.%d.tmp' % (full, os.getpid())
        with open(tmp, 'wb') as fh:
            fh.write(data)
        os.replace(tmp, full)
        for old in _stale(os.path.dirname(full), listing_id, key):
            if old != full:
                try:
                    os.remove(old)
                except OSError:
                    pass
    return rel


def _stale(folder, listing_id, key):
    pre = '%s-%s-' % (listing_id, key)
    return [os.path.join(folder, n) for n in os.listdir(folder) if n.startswith(pre) and n.endswith('.jpg')]


# ---------- who gets which card, and the WhatsApp text ----------
def plans_v2():
    return db.plans_v2()


def can_make(agency, kind):
    """Pro and up: every card (they are in the 'tools' feature). With LLAVE_PLANS_V2=1 Gratis also gets the plain post card,
    the one an agent forwards to WhatsApp groups: never the story and never the ¡Vendida! cards. The link preview is for everyone."""
    if kind == 'enlace' or db.plan_has(agency, 'tools'):
        return True
    return kind == 'post' and plans_v2()


def share_text(listing, url):
    """The short Spanish message behind 'Mándalo a tus grupos' (title, price and colonia, then the listing's address)."""
    l = dict(listing)
    price = money((l['price_cents'] // 100) if l.get('price_cents') is not None else None, l.get('currency') or 'MXN')
    where = ', '.join(x for x in (l.get('colonia'), l.get('municipio')) if x)
    return '%s\n%s\nFotos y datos aquí: %s' % ((l.get('title') or '').strip(), ' · '.join(x for x in (price, where) if x), url)
