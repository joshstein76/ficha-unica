"""'Ve tu página': an instant preview of an agent's own site before sign-up (2026-11-23, cross-applied from IDX Bloom's live
"See your website"). The agent types a name, an optional agency name and a colonia; the app renders their page with the real
agent-site template and one sample property. NOTHING is stored: no DB row, no cookie, no log line with the values, no URL with
them (POST only). Behind LLAVE_PREVIEW=1 (off by default). The button sends the same values to the real sign-up form, pre-filled."""
import os

from . import site
from .common import e

MAX = 60
SAMPLE_PHOTO = '/_s/u-casa-2-pisos.webp'
HERO_PHOTO = '/_s/hero-sala.webp'


def enabled():
    return os.environ.get('LLAVE_PREVIEW') == '1'


def _clean(s):
    return ' '.join(str(s or '').split())[:MAX]


def form(error='', values=None):
    v = values or {}
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex"><title>Ve tu página · Ficha Única</title>'
            '<style>body{margin:0;font:17px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:#F6F7FB;color:#111827}'
            'main{max-width:440px;margin:0 auto;padding:40px 16px}h1{font-size:30px;line-height:1.15;margin:0 0 8px;letter-spacing:-.02em}'
            'h1 span{color:#2F5BEA}p{margin:0 0 20px;color:#4B5563}form{display:grid;gap:12px;background:#fff;border-radius:16px;padding:20px;'
            'box-shadow:0 10px 30px -18px rgba(17,24,39,.35)}label{display:grid;gap:4px;font-weight:600;font-size:15px}'
            'input{font:16px system-ui,sans-serif;padding:12px;border:1px solid #D1D5DB;border-radius:10px}'
            'button{min-height:50px;border:0;border-radius:12px;background:#2F5BEA;color:#fff;font:600 17px system-ui,sans-serif;cursor:pointer}'
            '.err{color:#B42318;font-weight:600}.small{font-size:14px;color:#6B7280;margin:12px 0 0}</style></head><body><main>'
            '<a href="/" style="display:inline-flex;align-items:center;gap:8px;margin:0 0 28px;color:#111827;text-decoration:none;font-weight:700;font-size:18px">'
            '<img src="/_s/fu-mark-pulso.svg" alt="" width="28" height="28">Ficha Única</a>'
            '<h1>Ve tu página <span>en 10 segundos.</span></h1><p>Escribe tu nombre y tu zona. Te mostramos cómo se vería, antes de crear nada.</p>'
            '%s<form method="post" action="/vista-previa">'
            '<label>Tu nombre<input name="name" maxlength="60" required autocomplete="name" value="%s"></label>'
            '<label>Tu inmobiliaria o marca (opcional)<input name="agency" maxlength="60" value="%s"></label>'
            '<label>Tu colonia o ciudad<input name="zona" maxlength="60" required placeholder="Ej. Del Valle" value="%s"></label>'
            '<button>Ver mi página</button></form>'
            '<p class="small">No guardamos nada de esto. Si te gusta, la creas gratis en un paso.</p></main></body></html>') % (
        ('<p class="err" role="alert">%s</p>' % e(error)) if error else '', e(v.get('name', '')), e(v.get('agency', '')), e(v.get('zona', '')))


def page(values):
    """The preview itself: the agent-site template with their name and zona, one sample property, and the sign-up button."""
    name, agency, zona = _clean(values.get('name')), _clean(values.get('agency')), _clean(values.get('zona'))
    if not name or not zona:
        return None
    a = {'name': agency or name, 'logo_path': None, 'whatsapp': '', 'design': 'ciudad', 'accent': '#2F5BEA', 'slug': '',
         'city': zona, 'is_demo': 0, 'tagline': 'Bienes raíces en %s' % zona}
    bar = ('<div role="note" style="background:#EEF2FF;color:#1E2A5A;font:600 14px/1.4 system-ui,sans-serif;padding:10px 16px;text-align:center">'
           'Vista previa: así se vería tu página. Todavía no existe y no guardamos nada.</div>')
    card = ('<div class="lc" aria-label="Propiedad de ejemplo"><img src="%s" alt="Casa de ejemplo" width="900" height="599" style="aspect-ratio:4/3;object-fit:cover">'
            '<div class="t"><span class="tag">Ejemplo · Así se ve tu propiedad</span><h3>Casa de 2 pisos en %s</h3><span class="p">$6,950,000 MXN</span>'
            '<span class="f">210 m² · 3 rec. · 2.5 baños</span><span class="f">%s</span></div></div>') % (SAMPLE_PHOTO, e(zona), e(zona))
    cta = ('<section class="sec" style="text-align:center"><h2>¿Te gusta? Es tuya, gratis.</h2>'
           '<p class="muted">1 propiedad, sin tarjeta y sin fecha de vencimiento. Tus clientes te escriben directo a tu WhatsApp.</p>'
           '<form method="post" action="/vista-previa"><input type="hidden" name="paso" value="registro">'
           '<input type="hidden" name="name" value="%s"><input type="hidden" name="agency" value="%s"><input type="hidden" name="zona" value="%s">'
           '<button style="min-height:52px;padding:0 28px;border:0;border-radius:12px;background:#2F5BEA;color:#fff;font:600 17px var(--body);cursor:pointer">'
           'Crear mi página gratis</button></form></section>') % (e(name), e(agency), e(zona))
    body = ('<main id="main">%s<section class="hero"><img src="%s" alt="" width="640" height="479" fetchpriority="high">'
            '<div class="cap"><div class="in"><h1>%s</h1><p>%s</p></div></div></section>'
            '<div class="in"><section class="sec"><h2>Propiedades</h2><div class="cards">%s</div></section>%s</div></main>') % (
        bar, HERO_PHOTO, e(a['name']), e(('%s · ' % name if agency else '') + a['tagline']), card, cta)
    return site._page(a, 'Vista previa · %s' % a['name'], body, '<meta name="robots" content="noindex, nofollow">')
