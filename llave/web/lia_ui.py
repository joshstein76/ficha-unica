"""Lía's widget markup for agent sites (the chat itself is llave/lia.py; the look is static/lia.css; the behaviour is static/lia.js).
`attach` is the only entry point: when any gate is off it returns the page UNCHANGED (the same string, so the page is byte-identical
to a site without Lía); when all four are on it adds the widget just before </body>."""
import functools
import hashlib
import os

from .. import lia
from .common import e
from .styles import resolve_design

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# Lía's face: the 'lia' symbol of config/design-system/loteria-sprite.svg in the Command Center, inlined with its own ids so it
# never depends on the sprite being on the page (a ficha coin in cempasúchil with big eyes, rosa cheeks and a smile).
_CONCHA = ('<circle cx="50" cy="50" r="40"/><circle cx="88" cy="50" r="11"/><circle cx="82.9" cy="69" r="11"/><circle cx="69" cy="82.9" r="11"/>'
           '<circle cx="50" cy="88" r="11"/><circle cx="31" cy="82.9" r="11"/><circle cx="17.1" cy="69" r="11"/><circle cx="12" cy="50" r="11"/>'
           '<circle cx="17.1" cy="31" r="11"/><circle cx="31" cy="17.1" r="11"/><circle cx="50" cy="12" r="11"/><circle cx="69" cy="17.1" r="11"/>'
           '<circle cx="82.9" cy="31" r="11"/>')
FACE_DEFS = ('<svg class="lia-sp" width="0" height="0" aria-hidden="true" focusable="false"><defs><g id="lia-c">%s</g></defs>'
             '<symbol id="lia-face" viewBox="0 0 100 100"><use href="#lia-c" fill="#1B1236"/>'
             '<g transform="translate(50 50) scale(.87) translate(-50 -50)"><use href="#lia-c" fill="#FFB800"/></g>'
             '<ellipse cx="37" cy="45" rx="6" ry="8.5" fill="#1B1236"/><ellipse cx="63" cy="45" rx="6" ry="8.5" fill="#1B1236"/>'
             '<circle cx="39" cy="42" r="2.2" fill="#FFFFFF"/><circle cx="65" cy="42" r="2.2" fill="#FFFFFF"/>'
             '<circle cx="26" cy="58" r="6" fill="#FF4FA3"/><circle cx="74" cy="58" r="6" fill="#FF4FA3"/>'
             '<path fill="none" stroke="#1B1236" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" d="M37 60Q50 74 63 60"/>'
             '</symbol></svg>') % _CONCHA
FACE = '<svg class="lia-ic" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><use href="#lia-face"/></svg>'
CLOSE = ('<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" fill="none" '
         'stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>')
SEND = ('<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M4 12h15M13 5l7 7-7 7" fill="none" '
        'stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>')


@functools.lru_cache(maxsize=1)
def asset_version():
    """Short hash of lia.css + lia.js, so a changed file is never served from a day-old cache."""
    h = hashlib.sha1()
    for n in ('lia.css', 'lia.js'):
        with open(os.path.join(STATIC, n), 'rb') as f:
            h.update(f.read())
    return h.hexdigest()[:8]


def widget(agency, canon=None):
    """The widget block. All dynamic text goes through e(); the JS only ever sets textContent."""
    name = agency['name']
    design = resolve_design(agency['design'])
    quien = lia.who(agency, canon)
    v = asset_version()
    return (
        '<div class="lia d-%s" id="lia" data-l="%s" hidden>%s'
        '<button type="button" class="lia-fab" aria-haspopup="dialog" aria-expanded="false" aria-controls="lia-panel">%s<span>Pregúntale a Lía</span></button>'
        '<div class="lia-panel" id="lia-panel" role="dialog" aria-modal="true" aria-labelledby="lia-t" hidden>'
        '<header class="lia-h">%s<div><b id="lia-t">Lía</b><small>Asistente de IA de %s</small></div>'
        '<button type="button" class="lia-x" aria-label="Cerrar el chat">%s</button></header>'
        '<div class="lia-log" role="log" aria-live="polite" aria-label="Conversación con Lía" tabindex="0"><p class="lia-m a">%s</p></div>'
        '<form class="lia-cf" hidden><p class="lia-cft">Deja tus datos y %s te escribe por WhatsApp.</p>'
        '<label class="lia-vh" for="lia-n">Tu nombre</label><input id="lia-n" name="name" placeholder="Tu nombre" autocomplete="name" maxlength="80" required>'
        '<label class="lia-vh" for="lia-p">Tu WhatsApp (10 dígitos)</label><input id="lia-p" name="phone" placeholder="Tu WhatsApp (10 dígitos)" inputmode="tel" autocomplete="tel" maxlength="20" required>'
        '<label class="lia-ck"><input type="checkbox" name="consent" value="1" required><span>Acepto el '
        '<a href="/aviso-de-privacidad" target="_blank" rel="noopener">aviso de privacidad</a>.</span></label>'
        '<p class="lia-er" role="alert" hidden></p><button type="submit" class="lia-go">Enviar mis datos</button></form>'
        '<form class="lia-f"><input class="lia-hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<label class="lia-vh" for="lia-i">Tu mensaje</label>'
        '<textarea id="lia-i" rows="1" maxlength="%d" placeholder="Escribe tu pregunta" enterkeyhint="send"></textarea>'
        '<button type="submit" class="lia-s" aria-label="Enviar mensaje">%s</button></form>'
        '<p class="lia-n">Lía es una asistente de inteligencia artificial. Guardamos esta conversación para que %s te atienda. '
        '<a href="/aviso-de-privacidad" target="_blank" rel="noopener">Aviso de privacidad</a></p>'
        '</div></div><link rel="stylesheet" href="/_s/lia.css?v=%s"><script defer src="/_s/lia.js?v=%s"></script>') % (
        design, e(canon['id'] if canon else ''), FACE_DEFS, FACE, FACE, e(name), CLOSE,
        e(lia.greeting(name, canon['title'] if canon else None)), e(quien), lia.MAX_CHARS, SEND, e(name), v, v)


def attach(con, agency, page, canon=None):
    """-> the page with Lía added, or `page` itself (not a copy) when any of the four gates is off."""
    if not lia.enabled_for(con, agency):
        return page
    i = page.rfind('</body>')
    if i < 0:
        return page
    return page[:i] + widget(agency, canon) + page[i:]
