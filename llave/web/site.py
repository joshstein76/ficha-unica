"""The free agent website (one per agency, on <slug>.<base> or a verified custom domain).
Every listing page ships RealEstateListing JSON-LD, one canonical (Bolsa shares point to the owner's page),
a WhatsApp button and a lead form. Also sitemap.xml, robots.txt and llms.txt for AI search."""
import json

from .. import db, geo, whatsapp
from ..leads import rentapoliza_offer
from .common import e, money, nice_date, facts_line, label, TYPES
from .styles import FONTS, PRECONNECT, fonts_url, site_css

WA_ICON = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .1-3.3-.9-2.8-1.2-4.6-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.9s.7-2 1-2.3c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.4 0 .5l-.4.6-.4.4c-.1.2-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.3 2.4 1.5.3.1.5.1.6-.1l.9-1.1c.2-.3.4-.2.7-.1l1.9.9c.3.1.5.2.5.3.1.2.1.7-.1 1.3z"/></svg>')


CARD_SIZES = '(min-width:1120px) 360px, (min-width:600px) 33vw, 100vw'


def _scaled(p, s):
    """Dimensions of the s-px version, from the stored 1600 dimensions (longest side)."""
    w, h = p.get('width'), p.get('height')
    if not w or not h:
        return None
    k = min(1.0, s / float(max(w, h)))
    return max(1, round(w * k)), max(1, round(h * k))


def picture(p, alt, sizes, base=800, loading='lazy', priority=False):
    """<picture> with webp srcset (400/800/1600) and a jpg fallback; width/height set to avoid layout shift."""
    webp = ', '.join('%s %dw' % (e(p['webp_%d' % s]), (_scaled(p, s) or (s, 0))[0]) for s in (400, 800, 1600))
    jpg = ', '.join('%s %dw' % (e(p[k]), (_scaled(p, s) or (s, 0))[0])
                    for k, s in (('url_400', 400), ('url_800', 800), ('url', 1600)))
    d = _scaled(p, base)
    attrs = ' width="%d" height="%d"' % d if d else ''
    if priority:
        attrs += ' fetchpriority="high"'
    else:
        attrs += (' loading="lazy"' if loading == 'lazy' else '') + ' decoding="async"'
    return ('<picture><source type="image/webp" srcset="%s" sizes="%s">'
            '<img src="%s" srcset="%s" sizes="%s" alt="%s"%s></picture>') % (
        webp, sizes, e(p['url'] if base == 1600 else p['url_800']), jpg, sizes, e(alt), attrs)


def _page(agency, title, body, head_extra='', canonical=None, description=''):
    a = agency
    brand = ('<img src="%s/media/%s" alt="%s">' % (e(db.site_url(a)), e(a['logo_path']), e(a['name']))
             if a['logo_path'] else e(a['name']))
    wa = whatsapp.wa_link(a['whatsapp'], 'Hola, vi su sitio y me gustaría más información.') if a['whatsapp'] else ''
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s</title><meta name="description" content="%s">%s'
            '%s<link rel="stylesheet" href="%s">'
            '<style>%s</style>%s</head><body><a class="skip" href="#main">Saltar al contenido</a>'
            '<header class="sh"><div class="in"><a class="brand" href="/">%s</a>%s</div></header>'
            '%s'
            '<footer class="sf"><div class="in"><span>© %s · %s</span><span><a href="/aviso-de-privacidad">Aviso de privacidad</a></span>'
            '<span class="muted">Sitio creado con <a href="%s" rel="nofollow">Ficha Única</a></span></div></footer></body></html>') % (
        e(title), e(description[:160]),
        ('<link rel="canonical" href="%s">' % e(canonical)) if canonical else '',
        PRECONNECT, fonts_url(a['design']), site_css(a['design'], a['accent']), head_extra, brand,
        ('<a class="wa" href="%s" rel="nofollow" aria-label="WhatsApp de %s">%s WhatsApp</a>' % (e(wa), e(a['name']), WA_ICON)) if wa else '',
        body, e(a['name']), e(a['city'] or 'México'), e(brand_url('sitio-' + a['slug'])))


def brand_url(source):
    return '%s/?source=%s' % (db.origin(), source)


def _card(c):
    img = picture(c['photos'][0], '', CARD_SIZES) if c['photos'] else ''
    op = 'En venta' if c['operation'] == 'venta' else 'En renta'
    where = ', '.join(x for x in (c['address']['colonia'], c['address']['municipio']) if x)
    return ('<a class="lc" href="/propiedad/%s">%s<div class="t"><span class="tag">%s · %s</span>'
            '<h3>%s</h3><span class="p">%s</span><span class="f">%s</span><span class="f">%s</span></div></a>') % (
        e(c['slug']), img,
        op, e(label(TYPES, c['property_type'])), e(c['title']), e(money(c['price'], c['currency'])),
        e(facts_line(c)), e(where))


def home(con, agency):
    ids = db.public_listing_ids(con, agency['id'])
    cards = [db.canonical(con, i) for i in ids]
    hero_img = next((picture(c['photos'][0], '', '100vw', base=1600, priority=True) for c in cards if c['photos']), '')
    org = {'@context': 'https://schema.org', '@type': 'RealEstateAgent', 'name': agency['name'],
           'url': db.site_url(agency), 'telephone': agency['whatsapp'],
           'areaServed': agency['city'] or 'México', 'description': agency['about'] or ''}
    body = ('<main id="main"><section class="hero">%s<div class="cap"><div class="in"><h1>%s</h1><p>%s</p></div></div></section>'
            '<div class="in"><section class="sec"><h2>Propiedades</h2>%s</section>'
            '<section class="sec" id="alerta"><h2>¿Buscas algo en especial?</h2><form class="box alertf" method="post" action="/alerta" style="position:static">'
            '<input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">'
            '<label class="vh" for="al-n">Tu nombre</label><input id="al-n" name="name" placeholder="Tu nombre" autocomplete="name">'
            '<label class="vh" for="al-p">Tu WhatsApp</label><input id="al-p" name="phone" placeholder="Tu WhatsApp (10 dígitos)" inputmode="tel" required autocomplete="tel">'
            '<label class="vh" for="al-o">Operación</label><select id="al-o" name="operation"><option value="">Venta o renta</option><option value="venta">Venta</option><option value="renta">Renta</option></select>'
            '<label class="vh" for="al-c">Colonia</label><input id="al-c" name="colonia" placeholder="Colonia">'
            '<label class="vh" for="al-m">Presupuesto máximo</label><input id="al-m" name="max" inputmode="numeric" placeholder="Presupuesto máximo (MXN)">'
            '<label class="check"><input type="checkbox" name="consent" value="1" required> Acepto el <a href="/aviso-de-privacidad">aviso de privacidad</a>.</label>'
            '<button type="submit">Avísenme cuando salga algo así</button></form></section>'
            '<section class="sec"><h2>Sobre nosotros</h2><p class="desc">%s</p>%s</section></div></main>') % (
        hero_img,
        e(agency['name']), e(agency['tagline'] or ''),
        ('<div class="cards">%s</div>' % ''.join(_card(c) for c in cards)) if cards
        else '<p class="muted">Pronto publicaremos propiedades aquí.</p>',
        e(agency['about'] or ''), team_html(con, agency))
    ld = '<script type="application/ld+json">%s</script>' % json.dumps(org, ensure_ascii=False)
    return _page(agency, '%s · Bienes raíces' % agency['name'], body, ld, db.site_url(agency) + '/',
                 agency['about'] or agency['tagline'] or agency['name'])


def listing_jsonld(c, page_url):
    kind = {'casa': 'SingleFamilyResidence', 'departamento': 'Apartment'}.get(c['property_type'], 'Place')
    place = {'@type': kind, 'name': c['title'],
             'address': {'@type': 'PostalAddress', 'addressLocality': c['address']['colonia'] or '',
                         'addressRegion': c['address']['estado'] or '', 'addressCountry': 'MX'}}
    if c['m2_built']:
        place['floorSize'] = {'@type': 'QuantitativeValue', 'value': c['m2_built'], 'unitCode': 'MTK'}
    if c['bedrooms']:
        place['numberOfBedrooms'] = c['bedrooms']
    if c['bathrooms']:
        place['numberOfBathroomsTotal'] = c['bathrooms']
    ld = {'@context': 'https://schema.org', '@type': 'RealEstateListing', 'name': c['title'], 'url': page_url,
          'description': c['description'][:500], 'datePosted': (c['updated_at'] or '')[:10],
          'image': [p['url'] for p in c['photos'][:8]], 'about': place,
          'offeredBy': {'@type': 'RealEstateAgent', 'name': c['agency']['name'], 'url': c['agency']['site_url']}}
    if c['price'] is not None:
        ld['offers'] = {'@type': 'Offer', 'price': c['price'], 'priceCurrency': c['currency'],
                        'businessFunction': 'http://purl.org/goodrelations/v1#' +
                        ('Sell' if c['operation'] == 'venta' else 'LeaseOut'),
                        'availability': 'https://schema.org/InStock'}
    return ld


def listing(con, agency, c, shared_split=None, error=''):
    """c = canonical listing. When it belongs to another agency (Bolsa), contact = this agency,
    canonical = the owner's page."""
    own = c['agency']['id'] == agency['id']
    page_url = '%s/propiedad/%s' % (db.site_url(agency), c['slug'])
    canon = page_url if own else c['url']
    photos = c['photos']
    total = len(photos)

    def galt(i, p):
        return '%s – foto %d de %d' % (c['title'], i + 1, total)
    gal = ''.join(picture(p, galt(i, p), '(min-width:701px) 66vw, 100vw', base=1600 if i == 0 else 800,
                          priority=(i == 0)) for i, p in enumerate(photos[:3]))

    def strip_img(i, p):
        d = _scaled(p, 800)
        return '<img src="%s" alt="%s" loading="lazy" decoding="async"%s>' % (
            e(p['url_800']), e(galt(i, p)), (' width="%d" height="%d"' % d) if d else '')
    strip = ''.join(strip_img(i, p) for i, p in enumerate(photos) if i >= 3)
    facts = []
    for val, lab in ((money(c['price'], c['currency']), 'Precio'),
                     (('%g m²' % c['m2_built']) if c['m2_built'] else None, 'Construcción'),
                     (('%g m²' % c['m2_land']) if c['m2_land'] else None, 'Terreno'),
                     (c['bedrooms'], 'Recámaras'), (('%g' % c['bathrooms']) if c['bathrooms'] else None, 'Baños'),
                     (c['parking'], 'Estacionamientos'),
                     (money(c['maintenance'], 'MXN') if c['maintenance'] else None, 'Mantenimiento')):
        if val not in (None, '', 0):
            facts.append('<div><b>%s</b><small>%s</small></div>' % (e(val), lab))
    where = ', '.join(x for x in (c['address']['colonia'], c['address']['municipio'], c['address']['estado']) if x)
    wa = whatsapp.wa_link(agency['whatsapp'], whatsapp.listing_message(c)) if agency['whatsapp'] else ''
    rp = rentapoliza_offer(c)
    map_html = ''
    ad = c['address']
    if ad['lat'] is not None and ad['lng'] is not None:
        from .panel import map_block
        la, ln = geo.approx(ad['lat'], ad['lng'], exact=ad['show_exact'])
        map_html = '<div><h2>Ubicación%s</h2>%s</div>' % ('' if ad['show_exact'] else ' aproximada', map_block(
            [{'lat': la, 'lng': ln, 't': c['title'], 'p': money(c['price'], c['currency']), 'a': ad['colonia'] or ''}], 240))
    am = ''.join('<li>%s</li>' % e(x) for x in c['amenities'])
    ag = c.get('agent') if own else None
    contact_name = ag['name'] if ag and (ag['name'] or '').split(' ')[0].lower() not in ('equipo', 'team') else agency['name']
    avatar = ('<img class="av" src="%s/media/%s" alt="" width="56" height="56">' % (e(db.site_url(agency)), e(ag['photo']))
              if ag and ag.get('photo') else '<div class="av" aria-hidden="true">%s</div>' % e(contact_name[:1].upper()))
    profile_link = ('<br><a class="small" href="/asesor/%s">Ver perfil</a>' % e(ag['slug'])) if ag and ag.get('slug') else ''
    if ag and ag.get('whatsapp') and agency['whatsapp']:
        wa = whatsapp.wa_link(ag['whatsapp'], whatsapp.listing_message(c))
    inv = ' aria-invalid="true" aria-describedby="err"' if error else ''
    swipe = ''.join(picture(p, '', '88vw') for p in photos)
    body = ('<main id="main" class="in sec"><div><span class="tag">%s · %s · folio %s</span><h1>%s</h1>'
            '<p class="muted">%s</p><p class="lp-price">%s <span class="muted">%s</span></p></div>'
            '<div class="gal">%s</div>%s<div class="swipe" aria-hidden="true">%s</div><p class="swipe-hint muted small">%d fotos · desliza →</p>'
            '<div class="lp"><div class="sec" style="padding:0"><div class="facts">%s</div>'
            '%s<div><h2>Descripción</h2><p class="desc">%s</p></div>%s%s</div>'
            '<aside class="box" id="contacto"><h2 class="vh">Contacto</h2><div class="agent">%s<div><b>%s</b>%s<br>'
            '<span class="muted">Te responde por WhatsApp</span></div></div>'
            '%s'
            '<form method="post" action="/contacto"><input type="hidden" name="listing" value="%d">'
            '<input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">'
            '<label class="vh" for="f-name">Tu nombre</label><input id="f-name" name="name" placeholder="Tu nombre" autocomplete="name" required%s>'
            '<label class="vh" for="f-phone">Tu WhatsApp (10 dígitos)</label><input id="f-phone" name="phone" placeholder="Tu WhatsApp (10 dígitos)" inputmode="tel" autocomplete="tel" maxlength="20"%s>'
            '<label class="vh" for="f-email">Correo (opcional)</label><input id="f-email" name="email" type="email" placeholder="Correo (opcional)" autocomplete="email"%s>'
            '<label class="vh" for="f-msg">Mensaje</label><textarea id="f-msg" name="message" rows="3"%s>Hola, me interesa esta propiedad (folio %s).</textarea>'
            '<label class="check"><input type="checkbox" name="consent" value="1" required> Acepto el '
            '<a href="/aviso-de-privacidad">aviso de privacidad</a>.</label>%s'
            '<button type="submit">Quiero más información</button></form></aside></div></main>%s') % (
        'Venta' if c['operation'] == 'venta' else 'Renta', e(label(TYPES, c['property_type'])), e(c['ref']),
        e(c['title']), e(where), e(money(c['price'], c['currency'])), e(facts_line(c)), gal,
        ('<div class="strip">%s</div>' % strip) if strip else '', swipe, len(photos),
        ''.join(facts),
        ('<p class="muted small">Precio confirmado el %s. Sujeto a cambio y disponibilidad.</p>' % nice_date(c['price_date']))
        if c['price_date'] and c['price'] is not None else '',
        e(c['description']), ('<div><h2>Amenidades</h2><ul class="am">%s</ul></div>' % am) if am else '',
        (('<p class="notice">%s</p>' % e(rp)) if rp else '') + map_html + faq_html(c),
        avatar, e(contact_name), profile_link,
        ('<a class="wa" href="%s" rel="nofollow" aria-label="Escribir por WhatsApp a %s sobre esta propiedad">%s Escribir por WhatsApp</a>' % (e(wa), e(contact_name), WA_ICON)) if wa else '',
        c['id'], inv, inv, inv, inv, e(c['ref']), ('<p class="muted small" id="err" role="alert">%s</p>' % e(error)) if error else '',
        ('<a class="wa float" href="%s" rel="nofollow" aria-label="WhatsApp flotante: preguntar por esta propiedad">%s</a>'
         '<nav class="mbar" aria-label="Contacto rápido"><a class="wa" href="%s" rel="nofollow" aria-label="WhatsApp: contacto rápido">%s WhatsApp</a><a class="ask" href="#contacto">Me interesa</a></nav>'
         % (e(wa), WA_ICON, e(wa), WA_ICON)) if wa else '')
    og = ''.join('<meta property="%s" content="%s">' % (k, e(v)) for k, v in (
        ('og:title', c['title']), ('og:type', 'website'), ('og:url', canon),
        ('og:image', photos[0]['url'] if photos else ''), ('og:description', c['description'][:200])))
    from ..ai import geo_seo
    ld = '<script type="application/ld+json">%s</script>' % json.dumps(listing_jsonld(c, canon), ensure_ascii=False)
    faqs = geo_seo.listing_faq(c)
    if faqs:
        ld += '<script type="application/ld+json">%s</script>' % json.dumps(geo_seo.faq_jsonld(faqs), ensure_ascii=False)
    title = '%s · %s' % (c['title'], money(c['price'], c['currency']))
    return _page(agency, title, body, og + ld, canon, c['description'])


FICHA_CSS = r"""
@page{size:A4;margin:12mm}*{box-sizing:border-box}body{margin:0;font:11pt/1.45 "Figtree",system-ui,sans-serif;color:#1b1b1b;background:#fff}
.sheet{max-width:186mm;margin:0 auto;padding:16px;display:grid;gap:10px}
.hd{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--accent);padding-bottom:6px}
.hd b{font-size:14pt}.hd span{color:#666;font-size:9pt}
h1{font:400 22pt/1.1 "Instrument Serif",Georgia,serif;margin:0}
.main{width:100%;height:88mm;object-fit:cover}.row3{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.row3 img{width:100%;height:30mm;object-fit:cover}
.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.facts div{border:1px solid #ddd;padding:6px}
.facts b{display:block;font-size:13pt}.facts small{color:#666}
.desc{font-size:10pt;white-space:pre-line;max-height:60mm;overflow:hidden}
.ft{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #ddd;padding-top:8px;font-size:10pt}
.noprint{display:flex;gap:8px;justify-content:center;padding:12px}.noprint button{min-height:44px;padding:0 18px;font:600 15px system-ui;border:0;background:#1b1b1b;color:#fff;border-radius:8px;cursor:pointer}
@media print{.noprint{display:none}.sheet{padding:0}}
"""


def ficha(agency, c):
    """Printable A4 listing sheet (the PDF 'ficha técnica' agents hand out; print-to-PDF from the browser).
    Later: order printed copies from a nearby print shop through Cerquito."""
    p = c['photos']
    facts = [(money(c['price'], c['currency']), 'Precio'), (('%g m²' % c['m2_built']) if c['m2_built'] else None, 'Construcción'),
             (c['bedrooms'], 'Recámaras'), (('%g' % c['bathrooms']) if c['bathrooms'] else None, 'Baños'),
             (c['parking'], 'Estacionamientos'), (('%g m²' % c['m2_land']) if c['m2_land'] else None, 'Terreno')]
    facts_html = ''.join('<div><b>%s</b><small>%s</small></div>' % (e(v), l) for v, l in facts if v not in (None, '', 0))
    where = ', '.join(x for x in (c['address']['colonia'], c['address']['municipio'], c['address']['estado']) if x)
    url = '%s/propiedad/%s' % (db.site_url(agency), c['slug'])
    price_note = ('Precio al %s, sujeto a cambio y disponibilidad.' % nice_date(c['price_date'])) if c['price_date'] and c['price'] is not None else ''
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Ficha %s · %s</title><meta name="robots" content="noindex"><link rel="stylesheet" href="%s">'
            '<style>:root{--accent:%s}%s</style></head><body>'
            '<div class="noprint"><button onclick="window.print()">Imprimir o guardar PDF</button></div>'
            '<div class="sheet"><div class="hd"><b>%s</b><span>Folio %s · %s</span></div><h1>%s</h1><span>%s</span>'
            '%s<div class="row3">%s</div><div class="facts">%s</div><p class="desc">%s</p>'
            '<div class="ft"><span><b>%s</b><br>WhatsApp %s</span><span style="text-align:right">%s<br>%s</span></div></div>'
            '</body></html>') % (
        e(c['ref']), e(agency['name']), fonts_url('residencia'), e(agency['accent'] if (agency['accent'] or '').startswith('#') else '#1b1b1b'),
        FICHA_CSS, e(agency['name']), e(c['ref']), 'Venta' if c['operation'] == 'venta' else 'Renta', e(c['title']), e(where),
        ('<img class="main" src="%s" alt="">' % e(p[0]['url'])) if p else '',
        ''.join('<img src="%s" alt="">' % e(x['url_800']) for x in p[1:4]), facts_html, e(c['description'][:1200]),
        e(agency['name']), e(agency['whatsapp'] or ''), e(url), e(price_note))


def thanks(agency, wa_link='', message=''):
    body = ('<main id="main" class="in sec" style="min-height:50vh"><h1>%s</h1>'
            '<p>%s</p>%s<p><a href="/">Ver más propiedades</a></p></main>') % (
        e(message) if message else '¡Gracias! Ya recibimos tu mensaje.', '' if message else 'Te escribimos por WhatsApp en breve.',
        ('<p><a class="wa" href="%s">%s Escribir ahora por WhatsApp</a></p>' % (e(wa_link), WA_ICON)) if wa_link else '')
    return _page(agency, 'Gracias · ' + agency['name'], body)


def privacy(agency):
    body = ('<main id="main" class="in sec"><h1>Aviso de privacidad simplificado</h1><div class="desc">'
            '%s es responsable de los datos personales que nos compartes en este sitio (nombre, teléfono, correo y tu mensaje). '
            'Los usamos para responder tu solicitud sobre propiedades y darte seguimiento por WhatsApp, teléfono o correo. '
            'No vendemos tus datos. Puedes pedir acceso, corrección, cancelación u oposición (derechos ARCO) escribiendo a %s.\n\n'
            'Este sitio funciona con Ficha Única, un servicio de %s, que trata tus datos solo por cuenta de %s.\n\n'
            '<b>BORRADOR LOCAL</b>: texto de ejemplo, debe revisarlo un abogado conforme a la Ley Federal de Protección de Datos '
            'Personales en Posesión de los Particulares (2025) antes de publicarse.</div></main>') % (
        e(agency['name']), e(agency['email'] or agency['whatsapp'] or ''), e(db.OWNER), e(agency['name']))
    return _page(agency, 'Aviso de privacidad · ' + agency['name'], body)


def not_found(agency):
    return _page(agency, 'No encontrada · ' + agency['name'], '<main id="main" class="in sec"><h1>Esta propiedad ya no está disponible.</h1>'
                 '<p><a href="/">Ver propiedades disponibles</a></p></main>')


def sitemap(con, agency):
    base = db.site_url(agency)
    own = [db.canonical(con, i) for i in db.public_listing_ids(con, agency['id'], include_shared=False)]
    urls = [base + '/'] + ['%s/propiedad/%s' % (base, c['slug']) for c in own]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>'
            % ''.join('<url><loc>%s</loc></url>' % e(u) for u in urls))


def robots(agency):
    return 'User-agent: *\nAllow: /\nDisallow: /contacto\n\nSitemap: %s/sitemap.xml\n' % db.site_url(agency)


def llms(con, agency):
    """Plain-text summary for AI assistants (the AI-search edge)."""
    lines = ['# %s' % agency['name'], '', '> %s' % (agency['tagline'] or 'Bienes raíces'), '',
             agency['about'] or '', '', 'Contacto: WhatsApp %s' % (agency['whatsapp'] or ''), '', '## Propiedades', '']
    for i in db.public_listing_ids(con, agency['id'], include_shared=False):
        c = db.canonical(con, i)
        price = money(c['price'], c['currency'])
        if c['price_date'] and c['price'] is not None:
            price += ' (precio al %s)' % nice_date(c['price_date'])
        lines.append('- [%s](%s/propiedad/%s): %s; %s; %s; %s, %s' % (
            c['title'], db.site_url(agency), c['slug'], 'venta' if c['operation'] == 'venta' else 'renta',
            price, facts_line(c) or 's/d', c['address']['colonia'] or '', c['address']['municipio'] or ''))
    return '\n'.join(lines) + '\n'


def _agents(con, agency_id):
    return con.execute("SELECT * FROM users WHERE agency_id=? AND slug IS NOT NULL AND slug != '' ORDER BY id", (agency_id,)).fetchall()


def team_html(con, agency):
    rows = _agents(con, agency['id'])
    if not rows:
        return ''
    cards = ''.join('<a class="agent" href="/asesor/%s">%s<div><b>%s</b><br><span class="muted small">%s</span></div></a>' % (
        e(u['slug']), ('<img class="av" src="%s/media/%s" alt="" width="56" height="56" loading="lazy">' % (e(db.site_url(agency)), e(u['photo_path'])))
        if u['photo_path'] else '<div class="av" aria-hidden="true">%s</div>' % e(u['name'][:1].upper()),
        e(u['name']), e(u['zones'] or '')) for u in rows)
    return '<h2>Equipo</h2><div class="team">%s</div>' % cards


def agent_profile(con, agency, u):
    ids = [r['id'] for r in con.execute("SELECT id FROM listings WHERE agency_id=? AND agent_id=? AND status IN ('activa','apartada') "
                                        "ORDER BY updated_at DESC", (agency['id'], u['id']))]
    cards = [db.canonical(con, i) for i in ids]
    wa = whatsapp.wa_link(u['whatsapp'] or agency['whatsapp'], 'Hola %s, vi tu perfil y me gustaría más información.' % u['name'].split(' ')[0]) \
        if (u['whatsapp'] or agency['whatsapp']) else ''
    url = '%s/asesor/%s' % (db.site_url(agency), u['slug'])
    ld = {'@context': 'https://schema.org', '@type': 'RealEstateAgent', 'name': u['name'], 'url': url,
          'worksFor': {'@type': 'RealEstateAgent', 'name': agency['name'], 'url': db.site_url(agency)},
          'areaServed': [z.strip() for z in (u['zones'] or '').split(',') if z.strip()] or (agency['city'] or 'México'),
          'description': u['bio'] or ''}
    if u['photo_path']:
        ld['image'] = '%s/media/%s' % (db.site_url(agency), u['photo_path'])
    body = ('<main id="main" class="in sec"><div class="agent big">%s<div><h1>%s</h1><p class="muted">%s · %s</p></div></div>'
            '%s%s<section class="sec" style="padding:0"><h2>Propiedades de %s</h2>%s</section></main>') % (
        ('<img class="av" src="%s/media/%s" alt="Foto de %s" width="120" height="120">' % (e(db.site_url(agency)), e(u['photo_path']), e(u['name'])))
        if u['photo_path'] else '<div class="av" aria-hidden="true">%s</div>' % e(u['name'][:1].upper()),
        e(u['name']), e(agency['name']), e(u['zones'] or agency['city'] or ''),
        ('<p class="desc">%s</p>' % e(u['bio'])) if u['bio'] else '',
        ('<p><a class="wa" href="%s" rel="nofollow">%s Escribir por WhatsApp</a></p>' % (e(wa), WA_ICON)) if wa else '',
        e(u['name'].split(' ')[0]),
        ('<div class="cards">%s</div>' % ''.join(_card(c) for c in cards)) if cards else '<p class="muted">Pronto publicará propiedades aquí.</p>')
    head = '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False)
    return _page(agency, '%s · %s' % (u['name'], agency['name']), body, head, url, u['bio'] or '%s, asesor inmobiliario en %s' % (u['name'], agency['name']))


def faq_html(c):
    from ..ai import geo_seo
    faqs = geo_seo.listing_faq(c)
    if not faqs:
        return ''
    return '<div><h2>Preguntas frecuentes</h2>%s</div>' % ''.join(
        '<details class="faq"><summary>%s</summary><p>%s</p></details>' % (e(f['q']), e(f['a'])) for f in faqs)


def valuation(con, agency, result=None, error=''):
    """'¿Cuánto vale tu propiedad?' owner page: seller lead magnet. The estimate uses only public comparables in
    Ficha Única; with fewer than 3 it promises nothing and an agent follows up."""
    res = ''
    if result is not None:
        if result.get('ok'):
            res = ('<div class="box" style="position:static"><h2>Rango orientativo: %s – %s</h2><p class="muted small">%s</p>'
                   '<p>Un asesor de %s le escribe por WhatsApp para afinarlo con una visita.</p></div>') % (
                e(money(result['range_low'], result['currency'])), e(money(result['range_high'], result['currency'])),
                e(result['note']), e(agency['name']))
        else:
            res = ('<div class="box" style="position:static"><h2>Gracias, ya recibimos sus datos.</h2>'
                   '<p>Aún no hay suficientes propiedades comparables públicas en su zona para dar un rango automático. '
                   'Un asesor de %s le escribe por WhatsApp con una valuación.</p></div>') % e(agency['name'])
    types = ''.join('<option value="%s">%s</option>' % (k, e(v)) for k, v in TYPES)
    body = ('<main id="main" class="in sec"><div><h1>¿Cuánto vale su propiedad?</h1><p class="muted">Déjenos los datos básicos y le damos un '
            'rango orientativo con propiedades comparables de su zona. Sin costo.</p></div>%s%s'
            '<form class="box alertf" method="post" action="/vende" style="position:static">'
            '<input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">'
            '<label for="v-op">Operación<select id="v-op" name="operation"><option value="venta">Vender</option><option value="renta">Rentar</option></select></label>'
            '<label for="v-ty">Tipo<select id="v-ty" name="property_type">%s</select></label>'
            '<label for="v-col">Colonia<input id="v-col" name="colonia" required></label>'
            '<label for="v-mun">Alcaldía o municipio<input id="v-mun" name="municipio" required></label>'
            '<label for="v-m2">m² de construcción<input id="v-m2" name="m2" inputmode="decimal" required></label>'
            '<label for="v-rec">Recámaras<input id="v-rec" name="bedrooms" inputmode="numeric"></label>'
            '<label for="v-name">Su nombre<input id="v-name" name="name" required autocomplete="name"></label>'
            '<label for="v-phone">Su WhatsApp<input id="v-phone" name="phone" inputmode="tel" required autocomplete="tel"></label>'
            '<label class="check"><input type="checkbox" name="consent" value="1" required> Acepto el <a href="/aviso-de-privacidad">aviso de privacidad</a>.</label>'
            '<button type="submit">Ver el rango</button></form></main>') % (
        ('<p class="notice" role="alert">%s</p>' % e(error)) if error else '', res, types)
    return _page(agency, '¿Cuánto vale su propiedad? · ' + agency['name'], body, '', db.site_url(agency) + '/vende',
                 'Valuación orientativa sin costo con propiedades comparables de su zona.')
