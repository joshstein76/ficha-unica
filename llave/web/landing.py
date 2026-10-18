"""Public landing (app.<base>/) and public pricing (/planes, /precios when logged out).
Server-rendered, inline CSS, no JS, no third-party images. Mexican Spanish, tú, mobile-first.
Never names competitors. Prices come from panel.PLANS so the landing, the pricing page and the panel never disagree."""
import json

from .. import db
from .common import e
from .styles import PRECONNECT

FONTS = 'https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;700&family=Fraunces:opsz,wght@9..144,600&display=swap'

CSS = r"""
:root{--bg:#fbf7f0;--card:#fff;--fg:#1d2b25;--muted:#56625b;--line:#e8dfd0;--brand:#0f5c4c;--brand-2:#e3f1ec;--on-brand:#fff;
--accent:#b4452b;--sand:#f3ead9;--ok:#1d6b45;--r:18px;--f:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif;--h:"Fraunces",Georgia,serif}
@media (prefers-color-scheme:dark){:root{--bg:#10171a;--card:#182126;--fg:#eef2ee;--muted:#a9b6ae;--line:#2a3a40;--brand:#4cc3a3;--brand-2:#173a33;
--on-brand:#0b1f1a;--accent:#f09a82;--sand:#1b2a2a;--ok:#6fd39f}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:70px}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.55 var(--f);padding-bottom:76px}
a{color:var(--brand)}h1,h2,h3{margin:0;line-height:1.12;text-wrap:balance;font-family:var(--h);font-weight:600;letter-spacing:-.01em}
h1{font-size:clamp(34px,8.6vw,60px)}h2{font-size:clamp(27px,6vw,38px)}h3{font-size:21px;font-family:var(--f);font-weight:700;letter-spacing:0}
p{margin:0}.muted{color:var(--muted)}.small{font-size:14px}
.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:var(--card);padding:8px 12px;z-index:20}
.w{max-width:1080px;margin:0 auto;padding:0 max(18px,env(safe-area-inset-left))}
.bar{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar .w{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:60px}
.logo{font:700 20px var(--f);color:var(--fg);text-decoration:none}.logo span{color:var(--brand)}
.nav{display:none;gap:22px}.nav a{color:var(--fg);text-decoration:none;font-weight:600;font-size:15px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:50px;padding:0 24px;border-radius:99px;border:2px solid var(--brand);
background:var(--brand);color:var(--on-brand);font:700 17px var(--f);text-decoration:none;cursor:pointer;text-align:center}
.btn:hover{filter:brightness(1.08)}.btn.ghost{background:transparent;color:var(--brand)}.btn.sm{min-height:40px;padding:0 16px;font-size:15px}
a:focus-visible,.btn:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
section{padding:56px 0}.sec-h{display:grid;gap:10px;margin-bottom:28px;max-width:640px}
.hero{padding-block:36px 40px;display:grid;gap:36px;align-items:center}
.hero .t{display:grid;gap:20px;max-width:560px}.lead{font-size:19px;color:var(--muted)}
.eyebrow{font:700 13px var(--f);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.phone{justify-self:center;border-radius:42px;padding:10px;background:#16201c;box-shadow:0 30px 60px -20px rgba(15,92,76,.45),0 0 0 2px #2b3a34;position:relative}
.phone .scr{border-radius:33px;overflow:hidden;aspect-ratio:500/1083;background:#111}
.phone img{display:block;width:100%;height:100%;object-fit:cover}
.phone::before{content:"";position:absolute;top:18px;left:50%;width:74px;height:20px;margin-left:-37px;background:#16201c;border-radius:99px;z-index:2}
.cap{text-align:center;margin-top:12px}
.cards{display:grid;gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:24px;display:grid;gap:10px;align-content:start}
.ico{width:48px;height:48px;border-radius:14px;background:var(--brand-2);color:var(--brand);display:grid;place-items:center}
.ico svg{width:26px;height:26px}
.steps{counter-reset:s;display:grid;gap:14px;padding:0;margin:0;list-style:none}
.steps li{counter-increment:s;display:grid;gap:6px;padding:22px 22px 22px 74px;position:relative;background:var(--card);border:1px solid var(--line);border-radius:var(--r)}
.steps li::before{content:counter(s);position:absolute;left:20px;top:20px;width:38px;height:38px;border-radius:50%;background:var(--accent);color:#fff;
font:700 18px/38px var(--f);text-align:center}
.alt{background:var(--sand)}
.plans{display:grid;gap:14px}
.plan{position:relative}.plan.hl{border:2px solid var(--brand)}
.price{font:700 34px var(--f);margin:0}.price small{display:block;font:400 14px var(--f);color:var(--muted)}
.plan ul{margin:6px 0 0;padding:0;list-style:none;display:grid;gap:8px;font-size:15px}
.plan li{padding-left:26px;position:relative}.plan li::before{content:"";position:absolute;left:2px;top:.45em;width:12px;height:7px;border-left:2.5px solid var(--ok);border-bottom:2.5px solid var(--ok);transform:rotate(-45deg)}
.plan .btn{margin-top:8px}
.tag{justify-self:start;font:700 12px var(--f);letter-spacing:.04em;padding:3px 11px;border-radius:99px;background:var(--brand-2);color:var(--brand)}
.tag.soon{background:#fff0c9;color:#6b4700}@media (prefers-color-scheme:dark){.tag.soon{background:#3a2e14;color:#f0c065}}
details{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:0 20px}
details+details{margin-top:10px}summary{cursor:pointer;font-weight:700;padding:18px 0;list-style:none;display:flex;justify-content:space-between;gap:12px;min-height:44px}
summary::-webkit-details-marker{display:none}summary::after{content:"+";font-size:24px;line-height:1;color:var(--brand)}details[open] summary::after{content:"–"}
details p{padding:0 0 18px;color:var(--muted)}
.final{background:var(--brand);color:var(--on-brand);border-radius:28px;padding:44px 24px;text-align:center;display:grid;gap:18px;justify-items:center}
.final .btn{background:var(--on-brand);color:var(--brand);border-color:var(--on-brand)}.final h2{color:var(--on-brand)}
footer{padding:36px 0 24px;border-top:1px solid var(--line);margin-top:56px}footer .w{display:grid;gap:8px}
.sticky{position:fixed;left:0;right:0;bottom:0;z-index:9;padding:10px max(16px,env(safe-area-inset-left)) calc(10px + env(safe-area-inset-bottom));
background:color-mix(in srgb,var(--bg) 94%,transparent);backdrop-filter:blur(8px);border-top:1px solid var(--line)}
.sticky .btn{width:100%}

.hero-bg{background:radial-gradient(900px 500px at 85% -10%,rgba(180,69,43,.16),transparent 60%),radial-gradient(800px 500px at 0% 10%,rgba(15,92,76,.16),transparent 60%)}
.hero h1 em{font-style:italic;color:var(--accent)}
.fine{font-size:14px;color:var(--muted);display:flex;gap:6px 16px;flex-wrap:wrap}.fine span::before{content:"✓ ";color:var(--ok);font-weight:700}
.stage{position:relative;justify-self:center;width:100%;display:grid;justify-items:center}
.phone{width:min(74vw,330px)}
.chip{position:absolute;z-index:3;display:flex;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:10px 14px;
box-shadow:0 14px 30px -12px rgba(0,0,0,.35);font-size:13.5px;line-height:1.3;max-width:230px;animation:fl 6s ease-in-out infinite}
.chip b{display:block;font-size:13px}.chip i{flex:none;width:34px;height:34px;border-radius:50%;background:#177a41;color:#fff;display:grid;place-items:center;font-style:normal}
.chip i svg{width:18px;height:18px}.chip.a{left:0;top:18%}.chip.b{right:0;bottom:22%;animation-delay:-3s}
.rise{animation:rise .6s cubic-bezier(.2,.7,.2,1) both}.rise.d1{animation-delay:.08s}.rise.d2{animation-delay:.16s}.rise.d3{animation-delay:.24s}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fl{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
.card{transition:transform .2s,box-shadow .2s}.card:hover{transform:translateY(-3px);box-shadow:0 16px 30px -18px rgba(15,92,76,.5)}
.btn.big{min-height:58px;padding:0 34px;font-size:19px;box-shadow:0 12px 26px -10px rgba(15,92,76,.6)}
@media(prefers-reduced-motion:reduce){.rise,.chip{animation:none}.card{transition:none}html{scroll-behavior:auto}}
@media(max-width:759px){.chip.a{left:-4px;top:6%}.chip.b{right:-4px;bottom:10%}.chip{max-width:190px;font-size:12.5px}}
@media(min-width:760px){body{padding-bottom:0}.sticky{display:none}.nav{display:flex}.cards.c3{grid-template-columns:repeat(3,1fr)}
.steps{grid-template-columns:repeat(3,1fr)}.steps li{padding:70px 22px 22px}.steps li::before{left:22px;top:22px}
.plans{grid-template-columns:repeat(2,1fr)}.hero{grid-template-columns:1.1fr .9fr;padding-block:64px 56px}section{padding:80px 0}}
@media(min-width:1040px){.plans{grid-template-columns:repeat(4,1fr)}}
"""

_I = {
    'site': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8M12 18v3"/></svg>',
    'google': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>',
    'wa': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-12.4 7.4L3 20.5l1.7-5.4A8.4 8.4 0 1 1 21 11.5z"/></svg>',
    'shield': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg>',
    'share': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="m8.6 10.5 6.8-3.9M8.6 13.5l6.8 3.9"/></svg>',
    'cap': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/></svg>',
}

FAQ = [
    ('¿De verdad es gratis?',
     'Sí. El plan Gratis incluye tu sitio en una dirección de Ficha Única y hasta 10 propiedades. No pedimos tarjeta para empezar. '
     'Si luego quieres tu propio dominio o más propiedades, hay planes de pago.'),
    ('¿Necesito saber de computadoras?',
     'No. Se hace desde el celular: subes las fotos, escribes los datos una sola vez y listo. Si ya tienes tus propiedades en una hoja de Excel o CSV, también las puedes importar.'),
    ('¿Cómo me llegan los clientes?',
     'Cada persona que te escribe desde tu sitio te llega por WhatsApp, con su nombre y la propiedad que le interesó. Tú contestas como siempre.'),
    ('¿Mis propiedades salen en los portales?',
     'Salen en tu sitio y en Google. Los portales los conectamos conforme cada uno nos da su acceso; en tu panel ves cuáles están activos y cuáles vienen en camino. Nunca te prometemos un portal que todavía no funciona.'),
    ('¿Puedo cancelar cuando quiera?',
     'Sí. No hay plazo forzoso. Los precios son en pesos mexicanos, con IVA incluido.'),
]


def _plans():
    from . import panel  # lazy: panel imports this module
    return panel.PLANS, panel.COMING_SOON


def _money(price):
    return 'Gratis' if not price else '$%d MXN' % price


def _plan_cards(reg, current=None):
    plans, soon = _plans()
    out = []
    for k, name, price, feats in plans:
        tag = ('<span class="tag soon">Próximamente</span>' if k in soon else
               '<span class="tag">Para empezar</span>' if k == 'gratis' else '')
        per = '' if not price else ' <small>al mes, IVA incluido</small>'
        cta = '' if k in soon else '<a class="btn%s" href="%s">%s</a>' % (
            '' if k == 'gratis' else ' ghost', e(reg), 'Crear mi sitio gratis' if k == 'gratis' else 'Empezar gratis')
        out.append('<div class="card plan%s">%s<h3>%s</h3><p class="price">%s%s</p><ul>%s</ul>%s</div>' % (
            ' hl' if k == 'gratis' else '', tag, e(name), _money(price), per,
            ''.join('<li>%s</li>' % e(f) for f in feats), cta))
    return ''.join(out)


def _head(title, desc, extra=''):
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s</title><meta name="description" content="%s"><meta property="og:title" content="%s"><meta property="og:description" content="%s">'
            '<meta property="og:locale" content="es_MX"><meta name="theme-color" content="#0f5c4c">%s'
            '<link rel="stylesheet" href="%s"><style>%s</style>%s</head>') % (
        e(title), e(desc), e(title), e(desc), PRECONNECT, FONTS, CSS, extra)


def _top(reg):
    app = db.origin('app')
    return ('<body><a class="skip" href="#main">Saltar al contenido</a><header class="bar"><div class="w">'
            '<a class="logo" href="/">Ficha <span>Única</span></a>'
            '<nav class="nav" aria-label="Principal"><a href="/#como">Cómo funciona</a><a href="/planes">Planes</a><a href="/#preguntas">Preguntas</a>'
            '<a href="/propiedades">Ver propiedades</a></nav>'
            '<span class="row" style="gap:8px"><a class="btn ghost sm" href="%s/entrar">Entrar</a><a class="btn sm" href="%s">Crear mi sitio</a></span>'
            '</div></header>') % (e(app), e(reg))


def _foot(reg, local):
    return ('<footer><div class="w small muted"><p>Ficha Única es un servicio de %s · <a href="/terminos">Términos</a> · <a href="/privacidad">Privacidad</a></p>%s</div></footer>'
            '<div class="sticky"><a class="btn" href="%s">Crear mi sitio gratis</a></div></body></html>') % (
        e(db.OWNER), '' if not local else '<p>Versión local de prueba. Nada aquí es público todavía.</p>', e(reg))


def _reg(ref=''):
    return '%s/registro%s' % (db.origin('app'), ('?ref=' + ref) if ref else '')


def landing(ref=''):
    reg = _reg(ref)
    local = db.ENV != 'production'
    desc = 'Tu sitio inmobiliario gratis, tus propiedades en Google y en los portales, y tus clientes directo en tu WhatsApp. Hecho en México.'
    ld = json.dumps({'@context': 'https://schema.org', '@graph': [
        {'@type': 'Organization', 'name': db.BRAND, 'parentOrganization': {'@type': 'Organization', 'name': db.OWNER}},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in FAQ]}]},
        ensure_ascii=False).replace('</', '<\\/')
    promises = [
        ('site', 'Tu sitio, gratis', 'Una página elegante con tu nombre, tu foto y tus propiedades. Se ve increíble en el celular y se arma sola con lo que subes.'),
        ('google', 'En Google y en los portales', 'Escribes cada propiedad una sola vez. Sale en tu sitio, en Google y en los portales que vamos conectando. Más gente la ve.'),
        ('wa', 'Tus clientes, en WhatsApp', 'Quien te busca te escribe directo a tu WhatsApp, con su nombre y la propiedad que vio. Tú solo contestas.')]
    steps = [('Crea tu cuenta', 'Tu nombre, tu WhatsApp y el nombre de tu marca. Sin tarjeta.'),
             ('Sube tu primera propiedad', 'Fotos y datos desde el celular. Una sola vez.'),
             ('Listo, ya estás en línea', 'Tu sitio se publica y los clientes empiezan a escribirte por WhatsApp.')]
    eco = [('shield', 'RentaPóliza', 'Ofrece póliza jurídica a tus clientes de renta y gana créditos cuando se emite una.'),
           ('share', 'Bolsa 50/50', 'Comparte una propiedad con otros asesores y cierren juntos. Tú pones la repartición; por defecto es mitad y mitad.'),
           ('cap', 'Academia', 'Clases cortas para vender y rentar más. Dentro de tu cuenta.')]
    main = ('<main id="main">'
            '<div class="hero-bg"><div class="w hero"><div class="t"><span class="eyebrow rise">Para asesores inmobiliarios en México</span>'
            '<h1 class="rise d1">Que tus clientes te encuentren, te vean y te <em>escriban</em>. Hoy.</h1>'
            '<p class="lead rise d2">Tu propio sitio inmobiliario, bonito y gratis. Sube cada propiedad una sola vez: sale en tu sitio, en Google y en los portales, y tus clientes llegan directo a tu WhatsApp.</p>'
            '<div class="row rise d3"><a class="btn big" href="%s">Crear mi sitio gratis</a></div>'
            '<p class="fine rise d3"><span>Sin tarjeta</span><span>Sin plazo forzoso</span><span>Hecho en México</span></p>'
            '<p class="small muted">¿Buscas casa o departamento? <a href="/propiedades">Ver propiedades</a></p></div>'
            '<figure style="margin:0" class="stage rise d2"><div class="chip a" aria-hidden="true"><i>@@wa@@</i><span><b>Nuevo mensaje</b>Hola, me interesa el departamento. ¿Sigue disponible?</span></div>'
            '<div class="phone"><div class="scr"><img src="/_s/agent-site-demo.webp" width="500" height="1083" '
            'alt="Sitio de ejemplo de un asesor en Polanco, con foto grande, botón de WhatsApp y lista de propiedades" fetchpriority="high"></div></div>'
            '<div class="chip b" aria-hidden="true"><i>@@google@@</i><span><b>Tu propiedad en Google</b>Con ficha y datos para buscadores</span></div>'
            '<figcaption class="small muted cap">Un sitio real hecho con Ficha Única (ejemplo: VIVE Polanco).</figcaption></figure></div></div>'
            '<section class="alt"><div class="w"><div class="sec-h"><h2>Todo lo que necesitas para vender más, sin complicarte</h2></div><div class="cards c3">%s</div></div></section>'
            '<section id="como"><div class="w"><div class="sec-h"><span class="eyebrow">Cómo funciona</span><h2>De cero a tu sitio en línea en tres pasos</h2></div>'
            '<ol class="steps">%s</ol><div class="row" style="margin-top:28px;justify-content:center"><a class="btn big" href="%s">Crear mi sitio gratis</a></div></div></section>'
            '<section class="alt" id="planes"><div class="w"><div class="sec-h"><span class="eyebrow">Planes</span><h2>Empieza gratis. Crece cuando quieras.</h2>'
            '<p class="muted">Precios en pesos mexicanos, con IVA incluido. Sin plazo forzoso.</p></div><div class="plans">%s</div>'
            '<p class="small muted" style="margin-top:16px"><a href="/planes">Ver todos los detalles de los planes</a></p></div></section>'
            '<section><div class="w"><div class="sec-h"><span class="eyebrow">Más que un sitio</span><h2>Todo lo que necesita un asesor, en un solo lugar</h2></div>'
            '<div class="cards c3">%s</div></div></section>'
            '<section class="alt" id="preguntas"><div class="w" style="max-width:760px"><div class="sec-h"><h2>Preguntas frecuentes</h2></div>%s</div></section>'
            '<section><div class="w"><div class="final"><h2>Hoy puede ser el día que tu sitio salga al aire</h2>'
            '<p>Gratis, sin tarjeta y sin compromiso. Empieza con una propiedad.</p><a class="btn big" href="%s">Crear mi sitio gratis</a></div></div></section>'
            '</main>') % (
        e(reg),
        ''.join('<div class="card"><div class="ico">%s</div><h3>%s</h3><p class="muted">%s</p></div>' % (_I[i], e(t), e(d)) for i, t, d in promises),
        ''.join('<li><h3>%s</h3><p class="muted">%s</p></li>' % (e(t), e(d)) for t, d in steps),
        e(reg),
        _plan_cards(reg),
        ''.join('<div class="card"><div class="ico">%s</div><h3>%s</h3><p class="muted">%s</p></div>' % (_I[i], e(t), e(d)) for i, t, d in eco),
        ''.join('<details><summary>%s</summary><p>%s</p></details>' % (e(q), e(a)) for q, a in FAQ),
        e(reg))
    return _head('Ficha Única · Tu sitio inmobiliario gratis', desc, '<script type="application/ld+json">%s</script>' % ld) + _top(reg) + main.replace('@@wa@@', _I['wa']).replace('@@google@@', _I['google']) + _foot(reg, local)


def public_plans(ref=''):
    reg = _reg(ref)
    local = db.ENV != 'production'
    main = ('<main id="main"><section style="padding-top:40px"><div class="w"><div class="sec-h"><span class="eyebrow">Planes</span>'
            '<h1 style="font-size:clamp(32px,7vw,48px)">Empieza gratis. Crece cuando quieras.</h1>'
            '<p class="lead">Precios en pesos mexicanos, con IVA incluido. Sin plazo forzoso: cambias o cancelas cuando quieras.</p></div>'
            '<div class="plans">%s</div>'
            '<p class="small muted" style="margin-top:18px">Pro + CRM llega pronto. Todavía no se puede contratar.</p>'
            '<div class="row" style="margin-top:24px"><a class="btn" href="%s">Crear mi sitio gratis</a><a class="btn ghost" href="/">Volver al inicio</a></div>'
            '</div></section></main>') % (_plan_cards(reg), e(reg))
    return _head('Planes · Ficha Única', 'Gratis, Pro $299 MXN, Agencia $799 MXN al mes. Sin plazo forzoso.') + _top(reg) + main + _foot(reg, local)
