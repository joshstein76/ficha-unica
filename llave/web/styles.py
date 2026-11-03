"""CSS for the agent panel + logged-out pages (Ficha Única v7 brand, light only) and the three free-site designs
(Residencia / Ciudad / Costa, which are NOT part of the brand look and stay as they were). Mobile-first."""
import re

FONTS = 'https://fonts.googleapis.com/css2?family=Onest:wght@400..800&display=swap'  # brand pages: Onest only
_FIG = 'family=Figtree:wght@400;600;700'
PRECONNECT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
BRAND_COLOR = '#FF6B1A'  # mandarin: PWA theme_color + <meta name="theme-color">


def fonts_url(design):
    """Only the display family the design needs (ciudad uses Figtree for everything) + Figtree 400/600/700."""
    extra = {'residencia': 'family=Instrument+Serif&', 'costa': 'family=Fraunces:opsz,wght@9..144,500&'}.get(design, '')
    return 'https://fonts.googleapis.com/css2?%s%s&display=swap' % (extra, _FIG)


# Logo (Josh 2026-10-20): an orange chat bubble with a white house inside. Source: work/2026-10-20-REDESIGN/logo-final/ficha-unica-mark*.svg.
_MARK_BUBBLE = ('M19 6h26c7.2 0 13 5.8 13 13v19c0 7.2-5.8 13-13 13H29.5l-10.6 8.3c-1.4 1.1-3.4.1-3.4-1.7v-7.1C10.1 49.1 6 44 6 38V19C6 11.8 11.8 6 19 6z')
_MARK_ROOF = 'M19.5 30.5 32 20l12.5 10.5'
_MARK_HOUSE = 'M24 30v9.5c0 1.4 1.1 2.5 2.5 2.5H29v-6.5h6V42h2.5c1.4 0 2.5-1.1 2.5-2.5V30'


def mark_svg(uid):
    """The colour mark, inline. The gradient id must be unique per inline copy on a page, so every call site passes its own uid."""
    return ('<svg class="mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><defs><linearGradient id="%(u)s" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#FFB347"/><stop offset=".55" stop-color="#FF6B1A"/><stop offset="1" stop-color="#EC4614"/></linearGradient></defs>'
            '<path d="%(b)s" fill="url(#%(u)s)"/><path d="%(r)s" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="%(h)s" fill="none" stroke="#fff" stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round"/></svg>') % {
        'u': uid, 'b': _MARK_BUBBLE, 'r': _MARK_ROOF, 'h': _MARK_HOUSE}


def logo(uid):
    """Lockup: mark (36 px) + "Ficha Única" in Onest 800 (the .logo class). One uid per inline copy on a page."""
    return mark_svg(uid) + 'Ficha Única'


# Brand tokens (home-v7): white + soft, ink, mandarin, success green, WhatsApp green. Light only, by Josh's choice.
BRAND_TOKENS = (
    ':root{--bg:#FFFFFF;--soft:#F6F6F9;--card:#FFFFFF;--ink:#1A1A22;--ink-2:#464653;--muted:#636371;--line:#E6E6EE;--field:#8B8B99;'
    '--o:#FF6B1A;--o-2:#FF9A3D;--o-3:#FFC24B;--o-ink:#B83F0A;--o-soft:#FFF1E7;--on-o:#1A1A22;'
    '--grad:linear-gradient(115deg,#FFC24B 0%,#FF9A3D 38%,#FF6B1A 72%,#F2501F 100%);'
    '--wa:#0F8043;--ok:#0F6F50;--ok-soft:#E3F5EC;--bad:#B3261E;--bad-soft:#FDECEA;'
    '--shadow:0 18px 44px -18px rgba(26,26,34,.28);--shadow-o:0 12px 26px -12px rgba(255,107,26,.7);'
    '--font:"Onest",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color-scheme:light}')

# The logo lockup; also used on the public directory page.
MARK_CSS = r"""
.logo{display:inline-flex;align-items:center;gap:9px;text-decoration:none;color:var(--ink);font-weight:800;font-size:20px;letter-spacing:-.035em;white-space:nowrap}
.logo .mark{flex:none;width:36px;height:36px;display:block}
"""

# Shared bits (focus, skip link, reduced motion) used by both the landing CSS and the panel CSS.
BRAND_BASE = MARK_CSS + r"""
*{box-sizing:border-box}
a{color:var(--o-ink);text-underline-offset:3px}
:focus-visible{outline:3px solid var(--o-ink);outline-offset:3px;border-radius:10px}
.skip{position:absolute;left:8px;top:-80px;z-index:50;background:var(--ink);color:#fff;padding:10px 16px;border-radius:99px;font-weight:700;text-decoration:none}
.skip:focus{top:8px}
.vh{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}html{scroll-behavior:auto!important}}
"""

PANEL = BRAND_TOKENS + BRAND_BASE + r"""
body{margin:0;min-height:100vh;background:var(--soft);color:var(--ink);font:16px/1.5 var(--font);-webkit-font-smoothing:antialiased;padding-bottom:calc(84px + env(safe-area-inset-bottom,0px))}
body:has(.auth.pub){background:radial-gradient(60% 40% at 92% 0%,rgba(255,154,61,.26),transparent 70%) no-repeat,radial-gradient(55% 35% at 0% 100%,rgba(255,194,75,.2),transparent 70%) no-repeat,var(--soft)}
h1,h2,h3{line-height:1.2;margin:0;text-wrap:balance;letter-spacing:-.02em;font-weight:800}h1{font-size:26px;letter-spacing:-.03em}h2{font-size:18px}h3{font-size:16px}
p{margin:0}
.top{display:flex;align-items:center;justify-content:space-between;gap:10px 12px;flex-wrap:wrap;padding:12px max(16px,env(safe-area-inset-left,0px));
background:rgba(255,255,255,.92);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.top .logo{font-size:19px}
.wrap{max-width:860px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-left,0px)) 32px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px;display:grid;gap:12px;min-width:0}
.tiles{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.tile{position:relative;display:grid;justify-items:center;gap:8px;text-align:center;padding:16px 8px;background:var(--card);border:1px solid var(--line);border-radius:20px;color:var(--ink);text-decoration:none;min-height:104px}
.tile svg{width:30px;height:30px;color:var(--brand,#FF6B1A)}.tile b{font-size:14px;font-weight:700}
.tile small{position:absolute;top:8px;right:10px;font-size:11px;color:var(--muted)}
.progress{height:10px;border-radius:99px;background:var(--line);overflow:hidden}.progress i{display:block;height:100%;background:#FF6B1A;border-radius:99px}
.grid2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.grid2.wide{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.stats{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px 16px}
.stat b{display:block;font-size:28px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.stat small{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:14px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:46px;padding:0 22px;border-radius:99px;border:0;
background:var(--o);color:var(--on-o);font:800 16px var(--font);text-decoration:none;cursor:pointer;text-align:center;box-shadow:0 10px 22px -12px rgba(255,107,26,.75);transition:transform .18s ease}
.btn:hover{transform:translateY(-1px)}
.btn.ghost{background:var(--card);color:var(--ink);box-shadow:inset 0 0 0 1.5px var(--line)}
.btn.small{min-height:40px;padding:0 16px;font-size:14.5px;box-shadow:none}
.btn.wa{background:var(--wa);color:#fff;box-shadow:none}
form.stack{display:grid;gap:12px}label{display:grid;gap:5px;font-weight:700;font-size:14px;color:var(--ink-2)}
input,select,textarea{font:16px var(--font);color:var(--ink);padding:12px 14px;border-radius:14px;border:1.5px solid var(--field);background:#fff;width:100%}
input:focus,select:focus,textarea:focus{border-color:var(--o-ink)}
::placeholder{color:var(--muted);opacity:1}
textarea{min-height:120px}
input[type=checkbox],input[type=radio]{width:20px;height:20px;padding:0;flex:none;accent-color:var(--o-ink)}
.check{display:flex;gap:10px;align-items:flex-start;font-weight:500;color:var(--ink)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.list{display:grid;gap:10px}
.item{display:grid;grid-template-columns:84px 1fr;gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);
border-radius:18px;padding:10px;text-decoration:none;color:inherit;min-width:0}
.item img,.item .ph{width:84px;height:64px;object-fit:cover;border-radius:12px;background:var(--line)}
.item b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{justify-self:start;display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700;background:var(--soft);color:var(--ink-2);box-shadow:inset 0 0 0 1px var(--line)}
.pill.activa,.pill.en_feed,.pill.publicada,.pill.ok{background:var(--ok-soft);color:var(--ok);box-shadow:none}
.pill.borrador,.pill.pausada,.pill.pendiente,.pill.dry_run{background:var(--o-soft);color:var(--o-ink);box-shadow:none}
.pill.error,.pill.sin_convenio{background:var(--bad-soft);color:var(--bad);box-shadow:none}
.notice{border-radius:16px;padding:13px 16px;background:var(--ok-soft);color:var(--ink);box-shadow:inset 0 0 0 1px rgba(15,111,80,.18)}
.notice.err{background:var(--bad-soft);color:var(--bad);box-shadow:inset 0 0 0 1px rgba(179,38,30,.22)}
.notice.warn{background:var(--o-soft);color:var(--o-ink);box-shadow:inset 0 0 0 1px rgba(184,63,10,.22)}
.thumbs{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(96px,1fr))}
.thumbs figure{margin:0;display:grid;gap:4px}.thumbs img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:700}
.tbl{overflow-x:auto}
code{font-size:13px;word-break:break-all}
nav.tabs a.desk{display:none}nav.tabs{position:fixed;bottom:0;left:0;right:0;display:grid;grid-template-columns:repeat(6,1fr);gap:0;background:rgba(255,255,255,.96);
backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:6px max(2px,env(safe-area-inset-left,0px)) calc(6px + env(safe-area-inset-bottom,0px));z-index:9}
nav.tabs a{display:grid;justify-items:center;gap:2px;font-size:10.5px;letter-spacing:-.02em;font-weight:600;color:var(--ink-2);text-decoration:none;padding:6px 0 4px;border-radius:14px;min-width:0}
nav.tabs a span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav.tabs a.on{color:var(--o-ink);font-weight:700;background:var(--o-soft)}nav.tabs svg{width:22px;height:22px}
@media(min-width:900px){body{padding-bottom:0}nav.tabs{position:static;display:flex;flex-wrap:wrap;justify-content:center;gap:4px 10px;border:0;background:var(--card);
border-bottom:1px solid var(--line);padding:6px 8px}nav.tabs a{grid-auto-flow:column;font-size:14px;padding:8px 14px;white-space:nowrap}nav.tabs a.desk{display:grid}}
.fab{display:none}@media(max-width:899px){.fab{display:flex;position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(84px + env(safe-area-inset-bottom,0px));width:56px;height:56px;border-radius:50%;font-size:28px;padding:0;z-index:8;box-shadow:0 12px 26px -10px rgba(255,107,26,.8)}}
.wsteps{display:flex;gap:6px;flex-wrap:wrap;font-size:13px}.wsteps span{padding:4px 12px;border-radius:99px;background:var(--card);color:var(--muted);font-weight:600;box-shadow:inset 0 0 0 1px var(--line)}
.wsteps .on{background:var(--o);color:var(--on-o);font-weight:800;box-shadow:none}.wsteps .done{background:var(--ok-soft);color:var(--ok);box-shadow:none}
.bigpick{display:grid;justify-items:center;gap:6px;padding:28px 12px;border:2px dashed var(--field);border-radius:22px;background:var(--soft);cursor:pointer;text-align:center}
.bigpick{position:relative}.bigpick:focus-within{outline:3px solid var(--o-ink);outline-offset:2px}.bigpick span{font-size:20px;font-weight:800}.bigpick input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
fieldset{border:0;margin:0;padding:0;min-width:0}
.seg label,.chip{position:relative}
.seg{display:grid;grid-template-columns:1fr 1fr;gap:8px}.seg input,.chip input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}
.seg span,.chip span{display:flex;justify-content:center;align-items:center;min-height:46px;border:1.5px solid var(--field);border-radius:99px;background:#fff;color:var(--ink);cursor:pointer;font-weight:700}
.seg input:checked+span,.chip input:checked+span{border-color:var(--o);box-shadow:inset 0 0 0 1.5px var(--o);background:var(--o-soft);color:var(--o-ink)}
.seg input:focus-visible+span,.chip input:focus-visible+span{outline:3px solid var(--o-ink);outline-offset:2px}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip span{padding:0 16px;font-weight:600}
.auth .btn{width:100%}
.filters{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
.map{border-radius:22px;border:1px solid var(--line);z-index:0}
.card.late{border-color:var(--bad);box-shadow:inset 0 0 0 1px var(--bad)}
.bars{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:6px;align-items:end;height:140px}
.bar{display:grid;grid-template-rows:1fr auto;height:100%;text-align:center}.bar span{align-self:end;background:var(--grad);border-radius:8px 8px 0 0;min-height:2px}
.bar small{color:var(--muted);font-size:11px}
.plan.current{border-color:var(--o);box-shadow:inset 0 0 0 1.5px var(--o)}.price{margin:0;font-size:15px}.price b{font-size:28px;font-weight:800;letter-spacing:-.03em}.plan ul{margin:0;padding-left:18px;display:grid;gap:4px}
.auth{max-width:440px;margin:5vh auto;padding:0 16px;display:grid;gap:18px}
.auth h1{font-size:clamp(28px,7.4vw,38px);line-height:1.08;font-weight:800;letter-spacing:-.035em}
.auth p.muted{color:var(--ink-2);font-size:17px}
.intro{display:grid;gap:12px}
.micro{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14.5px;font-weight:600;color:var(--ink-2)}
.micro span{display:inline-flex;align-items:center;gap:6px}
.micro span::before{content:"";flex:none;width:16px;height:16px;border-radius:50%;background:var(--ok) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M5 12.5l4.2 4.2L19 7' fill='none' stroke='white' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/11px no-repeat}
"""

SITE_BASE = r"""
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 var(--body)}
img,picture{max-width:100%;display:block}a{color:inherit}
h1,h2,h3{font-family:var(--display);font-weight:var(--dw);line-height:1.12;margin:0;text-wrap:balance}
.in{max-width:1120px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left));padding-right:max(16px,env(safe-area-inset-right))}
header.sh{position:sticky;top:0;z-index:5;background:var(--hdr);border-bottom:1px solid var(--line)}
header.sh .in{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:64px}
.brand{font-family:var(--display);font-size:22px;text-decoration:none;font-weight:var(--dw)}
.brand img{height:40px;width:auto}
.wa{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 16px;border-radius:var(--br);background:#177a41;color:#fff;
text-decoration:none;font-weight:600;font-family:var(--body);font-size:15px;white-space:nowrap}
.hero{position:relative;color:#fff;background:#222}
.hero img{width:100%;height:min(68vh,560px);object-fit:cover;opacity:.78}
.hero .cap{position:absolute;inset:auto 0 0 0;padding-block:28px;background:linear-gradient(transparent,rgba(0,0,0,.62))}
.hero h1{font-size:clamp(32px,6vw,58px)}.hero p{margin:8px 0 0;max-width:56ch;opacity:.92}
.sec{padding-block:40px;display:grid;gap:22px}
.cards{display:grid;gap:20px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.lc{display:grid;gap:10px;text-decoration:none;background:var(--card);border-radius:var(--br);overflow:hidden;border:1px solid var(--line)}
.lc img{aspect-ratio:4/3;object-fit:cover;width:100%;height:auto}.lc .t{padding:0 16px 16px;display:grid;gap:4px}
.lc .p{font-weight:700;font-size:19px}.lc .f{color:var(--muted);font-size:15px}
.tag{display:inline-block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent-text);font-weight:700}
.gal{display:grid;gap:8px;grid-template-columns:2fr 1fr;grid-template-rows:1fr 1fr;height:min(60vh,520px)}
.gal picture{display:block;min-height:0;height:100%;overflow:hidden}.gal img{width:100%;height:100%;object-fit:cover;border-radius:calc(var(--br)/2)}.gal picture:first-child{grid-row:span 2}
.strip{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:6px}
.strip img{height:180px;width:auto;scroll-snap-align:start;border-radius:calc(var(--br)/2)}
@media(max-width:700px){.gal{grid-template-columns:1fr}.gal picture:not(:first-child){display:none}.hero img{height:52vh}}
.lp{display:grid;gap:28px;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);align-items:start}
@media(max-width:860px){.lp{grid-template-columns:1fr}}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.facts div{background:var(--card);border:1px solid var(--line);border-radius:calc(var(--br)/2);padding:12px}
.facts b{display:block;font-size:20px}.facts small{color:var(--muted)}
.box{background:var(--card);border:1px solid var(--line);border-radius:var(--br);padding:20px;display:grid;gap:12px;position:sticky;top:84px}
.box form,.alertf{display:grid;gap:10px}.alertf input,.alertf select{font:16px var(--body);padding:11px;border:1px solid var(--line);border-radius:8px;width:100%;background:var(--bg);color:var(--fg)}.alertf button{min-height:46px;border:0;border-radius:var(--br);background:var(--accent);color:var(--on-accent);font:600 16px var(--body);cursor:pointer}.box input,.box textarea{font:16px var(--body);padding:11px;border:1px solid var(--field-border);border-radius:8px;width:100%;background:var(--bg);color:var(--fg)}
.box button{min-height:46px;border:0;border-radius:var(--br);background:var(--accent);color:var(--on-accent);font:600 16px var(--body);cursor:pointer}
.check{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--muted)}.check input{width:20px;height:20px;padding:0;margin-top:2px;flex:none}.box label{display:grid;gap:4px;font-size:14px;font-weight:600}.box label.check{display:flex;font-weight:400}
.desc{white-space:pre-line;max-width:68ch}.faq{border-top:1px solid var(--line);padding:10px 0}.faq summary{cursor:pointer;font-weight:600}.muted{color:var(--muted)}
.am{display:flex;flex-wrap:wrap;gap:8px;padding:0;margin:0;list-style:none}.am li{border:1px solid var(--line);border-radius:99px;padding:4px 12px;font-size:14px}
.agent{display:flex;gap:14px;align-items:center;text-decoration:none}.agent .av{width:56px;height:56px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:grid;place-items:center;font-weight:700;object-fit:cover;flex:0 0 auto}
.agent.big .av{width:120px;height:120px;font-size:40px}.team{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
footer.sf{border-top:1px solid var(--line);padding-block:28px;color:var(--muted);font-size:14px}
footer.sf .in{display:flex;flex-wrap:wrap;gap:12px 24px;justify-content:space-between}
.float{position:fixed;right:max(16px,env(safe-area-inset-right));bottom:calc(16px + env(safe-area-inset-bottom));z-index:9;box-shadow:0 6px 20px rgba(0,0,0,.25)}
.lp-price{margin:6px 0 0;font-size:22px;font-weight:700}.lp-price .muted{font-size:15px;font-weight:400}
.swipe,.swipe-hint,.mbar{display:none}
@media(max-width:700px){.gal,.strip{display:none}.swipe{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;
margin-inline:calc(-1 * max(16px,env(safe-area-inset-left)));padding-inline:max(16px,env(safe-area-inset-left))}
.swipe picture{flex:0 0 88%;scroll-snap-align:center}.swipe img{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;border-radius:calc(var(--br)/2)}
.swipe-hint{display:block;margin:-12px 0 0}.float{display:none}.box{position:static}
.mbar{display:grid;grid-template-columns:1fr 1fr;gap:8px;position:fixed;left:0;right:0;bottom:0;z-index:9;background:var(--hdr);
border-top:1px solid var(--line);padding:10px max(16px,env(safe-area-inset-left)) calc(10px + env(safe-area-inset-bottom))}
.mbar a{justify-content:center;min-height:48px}.mbar .ask{display:flex;align-items:center;border-radius:var(--br);background:var(--accent);
color:var(--on-accent);text-decoration:none;font-weight:600;font-family:var(--body)}body:has(.mbar){padding-bottom:76px}}
:focus-visible{outline:3px solid var(--accent-text);outline-offset:2px}
.vh{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.skip{position:absolute;left:8px;top:-80px;z-index:20;background:var(--fg);color:var(--bg);padding:10px 16px;border-radius:var(--br);font-weight:700;text-decoration:none}
.skip:focus{top:8px}
fieldset{border:0;margin:0;padding:0}
"""

DESIGN_TOKENS = {
    # Lotería (Josh 2026-11-03): white page, tinta text + 3 px outlines, hard offset shadows. Light only, no dark theme.
    'loteria': ':root{--bg:#ffffff;--card:#ffffff;--fg:#1B1236;--muted:#5E5478;--line:#1B1236;--hdr:#ffffff;--br:12px;'
               '--display:"Bricolage Grotesque","Arial Narrow",Impact,sans-serif;--dw:800;'
               '--body:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif;'
               '--papel:#FFF9EE;--nopal:#0FB56D;--jac:#5B2EE6;color-scheme:light}',
    'residencia': ':root{--bg:#f7f5f2;--card:#fff;--fg:#1b1a19;--muted:#6b665f;--line:#e6e1da;--hdr:#f7f5f2;--br:2px;'
                  '--display:"Instrument Serif",Georgia,serif;--dw:400;--body:"Figtree",system-ui,sans-serif}',
    'ciudad': ':root{--bg:#ffffff;--card:#f6f7f9;--fg:#121417;--muted:#5d6570;--line:#e3e6ea;--hdr:#ffffff;--br:10px;'
              '--display:"Figtree",system-ui,sans-serif;--dw:700;--body:"Figtree",system-ui,sans-serif}',
    'costa': ':root{--bg:#f3f8f9;--card:#ffffff;--fg:#14313a;--muted:#5a7179;--line:#d9e8eb;--hdr:#f3f8f9;--br:18px;'
             '--display:"Fraunces",Georgia,serif;--dw:500;--body:"Figtree",system-ui,sans-serif}',
}
DARK = ('@media (prefers-color-scheme:dark){:root{--bg:#121212;--card:#1b1b1b;--fg:#ece9e4;--muted:#a59f97;'
        '--line:#2c2a27;--hdr:#121212;color-scheme:dark}}')


def _lin(c):
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def on_accent(accent):
    """White or near-black text, whichever has the better WCAG contrast on the accent."""
    return '#ffffff' if contrast('#ffffff', accent) >= contrast('#121212', accent) else '#121212'


def _mix(hexcolor, target, t):
    c = [int(hexcolor[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (target - x) * t) for x in c)


def accent_text(accent, bg, dark=False):
    """The accent, darkened (light theme) or lightened (dark theme) until it reads at >= 4.5:1 on bg."""
    out, t = accent, 0.0
    while contrast(out, bg) < 4.5 and t < 1:
        t = min(1, t + 0.05)
        out = _mix(accent, 255 if dark else 0, t)
    return out


# ---------------------------------------------------------------- Lotería (Josh 2026-11-03)
TINTA = '#1B1236'
LOTERIA_FONTS = ('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,800&%s&display=swap' % _FIG)
# The "ficha" coin from the design system (config/design-system/logo/ficha-unica-mark.svg), inline, decorative
# (the text link beside it says the name).
COIN_SVG = ('<svg class="coin" width="24" height="24" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><g fill="#1B1236">'
            '<circle cx="50" cy="50" r="40"/><circle cx="88" cy="50" r="11"/><circle cx="82.9" cy="69" r="11"/><circle cx="69" cy="82.9" r="11"/>'
            '<circle cx="50" cy="88" r="11"/><circle cx="31" cy="82.9" r="11"/><circle cx="17.1" cy="69" r="11"/><circle cx="12" cy="50" r="11"/>'
            '<circle cx="17.1" cy="31" r="11"/><circle cx="31" cy="17.1" r="11"/><circle cx="50" cy="12" r="11"/><circle cx="69" cy="17.1" r="11"/>'
            '<circle cx="82.9" cy="31" r="11"/></g><g fill="#FF4F1F" transform="translate(50 50) scale(.87) translate(-50 -50)">'
            '<circle cx="50" cy="50" r="40"/><circle cx="88" cy="50" r="11"/><circle cx="82.9" cy="69" r="11"/><circle cx="69" cy="82.9" r="11"/>'
            '<circle cx="50" cy="88" r="11"/><circle cx="31" cy="82.9" r="11"/><circle cx="17.1" cy="69" r="11"/><circle cx="12" cy="50" r="11"/>'
            '<circle cx="17.1" cy="31" r="11"/><circle cx="31" cy="17.1" r="11"/><circle cx="50" cy="12" r="11"/><circle cx="69" cy="17.1" r="11"/>'
            '<circle cx="82.9" cy="31" r="11"/></g><circle cx="50" cy="50" r="31" fill="#FFF9EE"/>'
            '<polygon points="50,28 74,49 67,49 67,72 56,72 56,57 44,57 44,72 33,72 33,49 26,49" fill="#1B1236"/></svg>')

# Layered after SITE_BASE, so the HTML and class names are the ones every design shares. Colours come from the tokens
# (--fg = tinta, --accent = the agent's colour, --on-accent = readable text on it). No dark block: the page is light on purpose.
LOTERIA_CSS = r"""
body{overflow-x:clip}
h1,h2,h3{font-stretch:80%;letter-spacing:-.025em;line-height:1.02}
h1{font-size:clamp(34px,9.4vw,60px)}h2{font-size:clamp(28px,7.4vw,42px)}h3{font-size:21px;line-height:1.08}
h1,h2,h3,.desc,.lc .f{overflow-wrap:break-word}
main h2{text-decoration:underline;text-decoration-color:var(--accent);text-decoration-thickness:.16em;text-underline-offset:.1em;text-decoration-skip-ink:none}
.small{font-size:14px}
::placeholder{color:var(--muted);opacity:1}
:focus-visible{outline:3px solid var(--jac);outline-offset:3px}
main a:not([class]){font-weight:700;text-decoration-thickness:2px}
main>p>a:only-child:not(.wa),a.small{display:inline-flex;align-items:center;min-height:44px}
header.sh{border-bottom:3px solid var(--fg)}
header.sh .in{min-height:68px;flex-wrap:nowrap}
.brand{display:inline-flex;align-items:center;min-width:0;min-height:44px;font:800 clamp(20px,5.8vw,26px)/1 var(--display);font-stretch:80%;letter-spacing:-.025em;overflow-wrap:anywhere}
.brand img{max-width:100%}
.wa,.box button,.alertf button,.mbar .ask,.lc,a.agent{transition:transform .08s,box-shadow .08s}
.wa{flex:none;gap:8px;padding:0 14px;border:3px solid var(--fg);border-radius:10px;background:var(--nopal);color:var(--fg);box-shadow:3px 3px 0 var(--fg);font:800 15px/1 var(--display);letter-spacing:-.005em}
.hero{position:relative;width:min(1088px,calc(100% - 2 * max(16px,env(safe-area-inset-left,0px))));margin:20px auto 0;overflow:hidden;
border:3px solid var(--fg);border-radius:18px;box-shadow:6px 6px 0 var(--fg);background:var(--accent);color:var(--on-accent)}
.hero img{height:clamp(320px,62vw,520px);opacity:1}
.hero .cap{position:static;padding:30px 18px;background:none}
.hero .cap .in{max-width:none;padding:0}
.hero h1{font-size:clamp(34px,9.4vw,62px)}
.hero p{margin:10px 0 0;max-width:46ch;opacity:1;font-size:clamp(16px,4.2vw,19px);line-height:1.35;font-weight:600}
.hero p:empty{display:none}
.hero picture+.cap{position:absolute;inset:auto 12px 12px 12px;padding:12px 14px 14px;background:var(--accent);border:3px solid var(--fg);border-radius:12px;box-shadow:3px 3px 0 var(--fg)}
.cards{grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));gap:22px}
.lc{position:relative;gap:0;background:#fff;border:3px solid var(--fg);border-radius:14px;box-shadow:4px 4px 0 var(--fg)}
.lc picture{border-bottom:3px solid var(--fg)}
.lc .t{padding:12px 14px 15px;gap:3px}
.lc .t h3{margin:2px 0 4px}
.lc .p{font:800 26px/1 var(--display);font-stretch:80%;letter-spacing:-.025em}
.lc .f{font-size:15px;line-height:1.3}
.lc picture+.t .tag{position:absolute;left:10px;top:10px}
.tag{justify-self:start;padding:6px 8px;border:2px solid var(--fg);border-radius:6px;background:var(--accent);color:var(--on-accent);font:700 12px/1 var(--body);letter-spacing:.05em}
main>div>.tag{margin-bottom:12px}
.gal{gap:14px}
.gal picture{overflow:visible}
.gal img,.strip img,.swipe img{border:3px solid var(--fg);border-radius:12px}
.gal img{box-shadow:4px 4px 0 var(--fg)}
.strip{gap:14px;padding:2px 6px 10px}.strip img{box-shadow:3px 3px 0 var(--fg)}
.swipe{gap:12px;padding-bottom:8px}.swipe img{box-shadow:3px 3px 0 var(--fg)}
.lp-price{margin:10px 0 0;font:800 clamp(32px,9vw,48px)/1 var(--display);font-stretch:80%;letter-spacing:-.025em}
.lp-price .muted{display:block;margin-top:8px;font:600 16px/1.4 var(--body);letter-spacing:0}
.facts{gap:12px}
.facts div{padding:10px 12px;border:3px solid var(--fg);border-radius:12px;background:#fff;box-shadow:3px 3px 0 var(--fg)}
.facts b{font:800 24px/1.05 var(--display);font-stretch:80%;letter-spacing:-.02em;overflow-wrap:anywhere}
.facts small{font-size:14px;font-weight:600}
.am{gap:8px}.am li{padding:6px 12px;border:2.5px solid var(--fg);background:var(--papel);font-weight:700}
.box{padding:18px;gap:14px;border:3px solid var(--fg);border-radius:16px;box-shadow:6px 6px 0 var(--fg)}
.box h2{font-size:26px}
.box input,.box select,.box textarea,.alertf input,.alertf select{min-height:48px;padding:12px 14px;border:3px solid var(--fg);border-radius:10px;background:var(--papel);color:var(--fg);font:500 16px/1.3 var(--body);width:100%}
.box textarea{min-height:104px;resize:vertical}
.box input[type=checkbox]{width:24px;height:24px;min-height:0;margin:0;padding:0;border:0;background:none;accent-color:var(--fg)}
.check{align-items:center;min-height:44px;font-size:14px}
.box label{font-weight:700}.box label.check{font-weight:500}
.box button,.alertf button,.mbar .ask{display:flex;align-items:center;justify-content:center;min-height:52px;padding:10px 18px;border:3px solid var(--fg);border-radius:12px;
background:var(--accent);color:var(--on-accent);box-shadow:4px 4px 0 var(--fg);font:800 18px/1.1 var(--display);letter-spacing:-.01em;text-align:center;cursor:pointer}
@media (hover:hover){.box button:hover,.alertf button:hover,.mbar .ask:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--fg)}
.wa:hover{transform:translate(-1px,-1px);box-shadow:4px 4px 0 var(--fg)}
.lc:hover,a.agent:hover{transform:translate(-1px,-1px);box-shadow:6px 6px 0 var(--fg)}}
.lc:active,a.agent:active,.box button:active,.alertf button:active,.mbar .ask:active{transform:translate(3px,3px);box-shadow:1px 1px 0 var(--fg)}
.wa:active{transform:translate(2px,2px);box-shadow:1px 1px 0 var(--fg)}
.faq{margin-top:12px;padding:0;border:3px solid var(--fg);border-radius:12px;background:#fff}
.faq summary{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px;padding:10px 14px;list-style:none;font-weight:700}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";flex:none;font:800 26px/1 var(--display)}
.faq[open] summary::after{content:"\2212"}
.faq p{margin:0;padding:0 14px 14px}
.notice{margin:0;padding:12px 14px;border:3px solid var(--fg);border-radius:12px;background:var(--papel);font-weight:600}
.map{position:relative;z-index:0;border:3px solid var(--fg);border-radius:14px;overflow:hidden}
.agent .av{border:3px solid var(--fg);background:var(--accent);color:var(--on-accent);font:800 24px/1 var(--display)}
.agent.big .av{box-shadow:4px 4px 0 var(--fg);font-size:44px}
.agent>div{min-width:0}.agent h1,.agent b{overflow-wrap:anywhere}
a.agent{padding:12px;border:3px solid var(--fg);border-radius:14px;background:#fff;box-shadow:4px 4px 0 var(--fg)}
.team{gap:18px}
footer.sf{padding-block:22px;border-top:3px solid var(--fg);background:var(--papel);font-size:15px}
footer.sf .in{align-items:center;gap:4px 24px}
footer.sf .in>span{display:inline-flex;align-items:center;flex-wrap:wrap;column-gap:6px;min-height:44px}
footer.sf a{display:inline-flex;align-items:center;min-height:44px;color:var(--fg);font-weight:700}
.coin{flex:none;width:24px;height:24px}
.float{box-shadow:4px 4px 0 var(--fg)}
.wa.float{width:56px;height:56px;padding:0;justify-content:center;border-radius:14px}.wa.float svg{width:26px;height:26px}
@media(max-width:700px){.hero img{height:clamp(320px,86vw,420px)}.mbar{gap:12px;border-top:3px solid var(--fg)}.mbar a{min-height:50px}body:has(.mbar){padding-bottom:calc(88px + env(safe-area-inset-bottom,0px))}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
"""

DEFAULT_DESIGN_FALLBACK = 'loteria'  # same value as db.DEFAULT_DESIGN (a test keeps them equal); styles stays free of db imports


def resolve_design(design):
    """The design key to render: any key we do not know (old rows, typos) falls back to Lotería."""
    return design if design in DESIGN_TOKENS else DEFAULT_DESIGN_FALLBACK


def site_fonts_url(design):
    """Google Fonts URL for an agent site: Lotería needs Bricolage Grotesque (with the width axis); the rest are unchanged."""
    design = resolve_design(design)
    return LOTERIA_FONTS if design == 'loteria' else fonts_url(design)


def safe_accent(accent):
    accent = accent if re.match(r'^#[0-9a-fA-F]{6}$', accent or '') else '#1f4e79'
    return accent.lower()


def loteria_on_accent(accent):
    """Text colour on the agent's accent in Lotería. on_accent() decides light or dark; the dark one becomes tinta when tinta
    reads too, and black/white is the last resort, so text is >= 4.5:1 on any accent (on_accent alone dips to ~4.3 around mid tones)."""
    pick = on_accent(accent)
    if pick == '#121212' and contrast(TINTA, accent) >= 4.5:
        return TINTA
    if contrast(pick, accent) >= 4.5:
        return pick
    return max(('#ffffff', '#000000'), key=lambda c: contrast(c, accent))


def site_css(design, accent, dark_mode=True):
    design = resolve_design(design)
    tokens = DESIGN_TOKENS[design]
    safe = safe_accent(accent)
    light_bg = re.search(r'--bg:(#[0-9a-fA-F]{6})', tokens).group(1)
    root = ':root{--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7a8594}' % (
        safe, on_accent(safe), accent_text(safe, light_bg))
    if design == 'loteria':  # light only: dark_mode is ignored, there is no dark block to opt out of
        return tokens + root + ':root{--on-accent:%s}' % loteria_on_accent(safe) + SITE_BASE + LOTERIA_CSS
    # A near-black or very dark accent disappears on the dark theme: swap in a light neutral there.
    dark_accent = '#d8d2c8' if luminance(safe) < 0.05 else safe
    dark = DARK.replace('color-scheme:dark}', '--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7d8a99;color-scheme:dark}' % (
        dark_accent, on_accent(dark_accent), accent_text(dark_accent, '#121212', dark=True)))
    return tokens + root + (dark if dark_mode else '') + SITE_BASE
