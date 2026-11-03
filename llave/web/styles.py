"""CSS for the agent panel + logged-out pages (Ficha Única "Lotería" look, approved by Josh 2026-11-03, light only) and the three
free-site designs (Residencia / Ciudad / Costa, which are NOT part of the brand look and stay as they were). Mobile-first.
The rules of the look live in the Command Center: clients/mx-broker-platform/config/design-system/MASTER.md."""
import re

FONTS = ('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400..800'
         '&family=Figtree:wght@400..800&family=Shrikhand&display=swap')  # brand pages: Bricolage (numbers, buttons) + Shrikhand (titles) + Figtree (text)
_FIG = 'family=Figtree:wght@400;600;700'
PRECONNECT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
BRAND_COLOR = '#FFB800'  # cempasúchil: PWA theme_color + <meta name="theme-color"> (same as the app icon and the header bar)


def fonts_url(design):
    """Only the display family the design needs (ciudad uses Figtree for everything) + Figtree 400/600/700."""
    extra = {'residencia': 'family=Instrument+Serif&', 'costa': 'family=Fraunces:opsz,wght@9..144,500&'}.get(design, '')
    return 'https://fonts.googleapis.com/css2?%s%s&display=swap' % (extra, _FIG)


# Logo (Lotería, 2026-11-03): the ficha, a chile coin with a scalloped edge and a white house. Source: config/design-system/logo/ficha-unica-mark.svg
# in the Command Center. It has no gradients and no ids, so any number of inline copies can share a page.
_COIN = ('<circle cx="50" cy="50" r="40"/><circle cx="88" cy="50" r="11"/><circle cx="82.9" cy="69" r="11"/><circle cx="69" cy="82.9" r="11"/>'
         '<circle cx="50" cy="88" r="11"/><circle cx="31" cy="82.9" r="11"/><circle cx="17.1" cy="69" r="11"/><circle cx="12" cy="50" r="11"/>'
         '<circle cx="17.1" cy="31" r="11"/><circle cx="31" cy="17.1" r="11"/><circle cx="50" cy="12" r="11"/><circle cx="69" cy="17.1" r="11"/>'
         '<circle cx="82.9" cy="31" r="11"/>')
_HOUSE = '<polygon points="50,28 74,49 67,49 67,72 56,72 56,57 44,57 44,72 33,72 33,49 26,49" fill="#1B1236"/>'


def mark_svg(uid=''):
    """The coin mark, inline. `uid` is ignored (the old gradient mark needed one id per copy); call sites keep passing it."""
    return ('<svg class="mark" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><g fill="#1B1236">%s</g>'
            '<g fill="#FF4F1F" transform="translate(50 50) scale(.87) translate(-50 -50)">%s</g>'
            '<circle cx="50" cy="50" r="31" fill="#FFF9EE"/>%s</svg>') % (_COIN, _COIN, _HOUSE)


def logo(uid=''):
    """Lockup: the coin (36 px) + "Ficha Única" in Shrikhand (the .logo class)."""
    return mark_svg(uid) + 'Ficha Única'


# Brand tokens (Lotería): tinta (text, outlines, hard shadows), papel (page), blanco (card faces), then the colour walls.
# Text on chile / cempa / rosa / nopal / cielo is tinta; white text only on jacaranda; suave (secondary text) only on papel or blanco.
# The old v7 names (--bg --soft --card --ink --ink-2 --muted --line --field --o --o-ink --o-soft --on-o --wa --ok --bad ...) still exist
# and now point at the Lotería colours, so the landing, the panel and the directory page keep working.
BRAND_TOKENS = (
    ':root{--tinta:#1B1236;--papel:#FFF9EE;--blanco:#FFFFFF;--cempa:#FFB800;--chile:#FF4F1F;--jacaranda:#5B2EE6;--rosa:#FF4FA3;--nopal:#0FB56D;--cielo:#37C5F2;--suave:#5E5478;'
    '--bg:var(--papel);--soft:var(--papel);--card:var(--blanco);--ink:var(--tinta);--ink-2:var(--tinta);--muted:var(--suave);--line:rgba(27,18,54,.18);--field:var(--tinta);'
    '--o:var(--chile);--o-2:var(--cempa);--o-3:var(--cempa);--o-ink:var(--jacaranda);--o-soft:var(--cempa);--on-o:var(--tinta);'
    '--wa:var(--nopal);--ok:var(--nopal);--ok-soft:var(--nopal);--bad:var(--chile);--bad-soft:var(--chile);'
    '--shadow:4px 4px 0 var(--tinta);--shadow-o:4px 4px 0 var(--tinta);'
    '--titulo:"Bricolage Grotesque","Arial Narrow",Impact,sans-serif;--carta:"Shrikhand","Cooper Black",Georgia,serif;'
    '--texto:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif;--font:var(--texto);color-scheme:light}')

# The logo lockup; also used on the public directory page.
MARK_CSS = r"""
.logo{display:inline-flex;align-items:center;gap:9px;min-height:44px;text-decoration:none;color:var(--tinta);font:400 22px/1 var(--carta);white-space:nowrap;font-synthesis:none}
.logo .mark{flex:none;width:36px;height:36px;display:block}
"""

# Shared bits (focus, skip link, reduced motion) used by both the landing CSS and the panel CSS.
BRAND_BASE = MARK_CSS + r"""
*{box-sizing:border-box}
a{color:var(--jacaranda);text-underline-offset:3px}
:focus-visible{outline:3px solid var(--jacaranda);outline-offset:3px}
.skip{position:absolute;left:8px;top:-80px;z-index:50;background:var(--tinta);color:var(--papel);padding:10px 16px;border-radius:10px;font-weight:800;text-decoration:none}
.skip:focus{top:8px}
.vh{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}html{scroll-behavior:auto!important}}
"""

# Buttons, notices and the bottom bar: shared by the panel and the Home page (kit_page), which does not load PANEL.
BTN_CSS = r"""
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:0 22px;border-radius:12px;border:3px solid var(--tinta);
background:var(--chile);color:var(--tinta);font:800 17px/1.1 var(--titulo);text-decoration:none;cursor:pointer;text-align:center;box-shadow:4px 4px 0 var(--tinta);transition:transform .08s,box-shadow .08s}
.btn:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--tinta)}
.btn:active{transform:translate(3px,3px);box-shadow:1px 1px 0 var(--tinta)}
.btn.ghost{background:var(--blanco)}
.btn.small{min-height:44px;padding:0 16px;font-size:15px;box-shadow:3px 3px 0 var(--tinta)}
.btn.small:hover{box-shadow:4px 4px 0 var(--tinta)}.btn.small:active{box-shadow:1px 1px 0 var(--tinta)}
.btn.wa{background:var(--nopal)}
.btn[disabled]{background:var(--blanco);color:var(--suave);box-shadow:none;transform:none;cursor:not-allowed}
.notice{border:3px solid var(--tinta);border-radius:12px;padding:12px 16px;background:var(--nopal);color:var(--tinta);box-shadow:3px 3px 0 var(--tinta);font-weight:600}
.notice.err{background:var(--chile)}.notice.warn{background:var(--cempa)}
.notice a,.notice .muted{color:var(--tinta)}.notice a{font-weight:800}
"""

NAV_CSS = r"""
nav.tabs a.desk{display:none}
nav.tabs{position:fixed;bottom:0;left:0;right:0;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);background:var(--blanco);border-top:3px solid var(--tinta);
padding:0 max(0px,env(safe-area-inset-left,0px)) env(safe-area-inset-bottom,0px);z-index:9}
nav.tabs a{display:grid;justify-items:center;align-content:center;gap:3px;min-height:56px;min-width:0;padding:7px 1px 6px;font:700 11.5px/1 var(--texto);color:var(--tinta);text-decoration:none}
@media(max-width:899px){nav.tabs:has(a:nth-child(6)) a{font-size:10.5px;letter-spacing:-.02em}}
nav.tabs a span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav.tabs a.on{background:var(--cempa)}
nav.tabs svg{width:23px;height:23px}
@media(min-width:900px){html body{padding-bottom:0}nav.tabs{position:static;display:flex;flex-wrap:wrap;justify-content:center;gap:6px 10px;border-top:0;border-bottom:3px solid var(--tinta);padding:8px}
nav.tabs a{grid-auto-flow:column;gap:8px;min-height:44px;font-size:15px;padding:0 16px;white-space:nowrap;border-radius:99px;border:2.5px solid transparent}
nav.tabs a.on{border-color:var(--tinta);box-shadow:2px 2px 0 var(--tinta)}nav.tabs a.desk{display:grid}}
"""

PANEL = BRAND_TOKENS + BRAND_BASE + BTN_CSS + NAV_CSS + r"""
body{margin:0;min-height:100vh;background:var(--papel);color:var(--tinta);font:400 16px/1.5 var(--texto);-webkit-font-smoothing:antialiased;overflow-x:clip;padding-bottom:calc(84px + env(safe-area-inset-bottom,0px))}
body:has(.auth.pub){background:var(--cempa)}
body:has(.auth.pub) footer.muted,body:has(.auth.pub) footer a{color:var(--tinta)}
h1,h2,h3{margin:0;text-wrap:balance}
h1,h2{font-family:var(--carta);font-weight:400;font-synthesis:none;line-height:1.12}h1{font-size:30px}h2{font-size:21px}
h3{font:800 17px/1.2 var(--titulo);letter-spacing:-.01em}
p{margin:0}
.top{display:flex;align-items:center;justify-content:space-between;gap:10px 12px;flex-wrap:wrap;padding:10px max(16px,env(safe-area-inset-left,0px));
background:var(--cempa);border-bottom:3px solid var(--tinta);position:sticky;top:0;z-index:5}
.top .logo{font-size:21px}
.top a:not(.btn):not(.logo){color:var(--tinta);font-weight:700;display:inline-flex;align-items:center;min-height:44px;padding:0 4px}
.wrap{max-width:860px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-left,0px)) 32px;display:grid;gap:18px}
.card{background:var(--blanco);border:3px solid var(--tinta);border-radius:14px;box-shadow:4px 4px 0 var(--tinta);padding:18px;display:grid;gap:12px;min-width:0}
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.tile{position:relative;display:grid;justify-items:center;align-content:center;gap:8px;text-align:center;padding:16px 8px;background:var(--blanco);border:3px solid var(--tinta);border-radius:12px;
box-shadow:4px 4px 0 var(--tinta);color:var(--tinta);text-decoration:none;min-height:104px;transition:transform .08s,box-shadow .08s}
.tile:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--tinta)}.tile:active{transform:translate(2px,2px);box-shadow:2px 2px 0 var(--tinta)}
.tile svg{width:46px;height:46px;padding:10px;border:2.5px solid var(--tinta);border-radius:12px;background:var(--cempa);color:var(--tinta)}
.tile:nth-child(4n+2) svg{background:var(--rosa)}.tile:nth-child(4n+3) svg{background:var(--cielo)}.tile:nth-child(4n) svg{background:var(--nopal)}
.tile b{font:800 15px/1.15 var(--titulo)}
.tile small{position:absolute;top:7px;right:7px;padding:3px 5px;border:2px solid var(--tinta);border-radius:6px;background:var(--cempa);color:var(--tinta);font:700 10.5px/1 var(--texto);letter-spacing:.04em;text-transform:uppercase}
.progress{height:16px;border:3px solid var(--tinta);border-radius:99px;background:var(--blanco);overflow:hidden}.progress i{display:block;height:100%;background:var(--chile)}
.grid2{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.grid2.wide{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.stats{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.stat{background:var(--blanco);border:3px solid var(--tinta);border-radius:12px;box-shadow:3px 3px 0 var(--tinta);padding:14px 16px}
.stat b{display:block;font:800 32px/1.05 var(--titulo);font-stretch:80%;letter-spacing:-.025em;font-variant-numeric:tabular-nums}.stat small{color:var(--suave);font-weight:600}
.muted{color:var(--suave)}.small{font-size:14px}
form.stack{display:grid;gap:12px}label{display:grid;gap:5px;font-weight:700;font-size:15px;color:var(--tinta)}
input,select,textarea{font:16px var(--texto);color:var(--tinta);padding:12px 14px;min-height:48px;border-radius:10px;border:3px solid var(--tinta);background:var(--papel);width:100%}
input:focus,select:focus,textarea:focus{background:var(--blanco)}
::placeholder{color:var(--suave);opacity:1}
textarea{min-height:120px}
input[type=checkbox],input[type=radio]{width:24px;height:24px;min-height:0;padding:0;flex:none;accent-color:var(--jacaranda)}
.check{display:flex;gap:10px;align-items:center;min-height:44px;font-weight:500;color:var(--tinta)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.list{display:grid;gap:12px}
.item{display:grid;grid-template-columns:84px 1fr;gap:12px;align-items:center;background:var(--blanco);border:3px solid var(--tinta);border-radius:12px;box-shadow:3px 3px 0 var(--tinta);
padding:10px;text-decoration:none;color:inherit;min-width:0;min-height:44px}
a.item{transition:transform .08s,box-shadow .08s}a.item:hover{transform:translate(-1px,-1px);box-shadow:4px 4px 0 var(--tinta)}
.item img,.item .ph{width:84px;height:64px;object-fit:cover;border:2.5px solid var(--tinta);border-radius:8px;background:var(--papel)}
.item b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{justify-self:start;display:inline-block;padding:4px 8px;border-radius:6px;border:2px solid var(--tinta);background:var(--blanco);color:var(--tinta);font:700 12px/1.1 var(--texto);letter-spacing:.04em;text-transform:uppercase}
.pill.activa,.pill.en_feed,.pill.publicada,.pill.ok{background:var(--nopal)}
.pill.borrador,.pill.pausada,.pill.pendiente,.pill.dry_run{background:var(--cempa)}
.pill.error,.pill.sin_convenio{background:var(--chile)}
.thumbs{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(96px,1fr))}
.thumbs figure{margin:0;display:grid;gap:4px}.thumbs img{width:100%;aspect-ratio:4/3;object-fit:cover;border:2.5px solid var(--tinta);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--suave);font-weight:700;border-bottom:2px solid var(--tinta)}
.tbl{overflow-x:auto}
code{font-size:13px;word-break:break-all}
.fab{display:none}@media(max-width:899px){.fab{display:flex;position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(88px + env(safe-area-inset-bottom,0px));width:56px;height:56px;border-radius:50%;font-size:28px;padding:0;z-index:8}}
.wsteps{display:flex;gap:8px;flex-wrap:wrap;font-size:13px}.wsteps span{padding:5px 12px;border-radius:99px;border:2px solid var(--tinta);background:var(--blanco);color:var(--suave);font-weight:700}
.wsteps .on{background:var(--chile);color:var(--tinta);font-weight:800}.wsteps .done{background:var(--nopal);color:var(--tinta)}
.bigpick{position:relative;display:grid;justify-items:center;gap:6px;padding:28px 12px;border:3px dashed var(--tinta);border-radius:14px;background:var(--papel);cursor:pointer;text-align:center}
.bigpick:focus-within{outline:3px solid var(--jacaranda);outline-offset:3px}.bigpick span{font:800 20px/1.2 var(--titulo)}.bigpick input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
fieldset{border:0;margin:0;padding:0;min-width:0}
.seg label,.chip{position:relative}
.seg{display:grid;grid-template-columns:1fr 1fr;gap:10px}.seg input,.chip input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}
.seg span,.chip span{display:flex;justify-content:center;align-items:center;min-height:48px;border:3px solid var(--tinta);border-radius:10px;background:var(--blanco);color:var(--tinta);cursor:pointer;font-weight:700;
box-shadow:3px 3px 0 var(--tinta);transition:transform .08s,box-shadow .08s}
.seg input:checked+span,.chip input:checked+span{background:var(--cempa);font-weight:800;transform:translate(2px,2px);box-shadow:1px 1px 0 var(--tinta)}
.seg input:focus-visible+span,.chip input:focus-visible+span{outline:3px solid var(--jacaranda);outline-offset:3px}
.chips{display:flex;flex-wrap:wrap;gap:10px}.chip span{padding:0 16px;border-radius:99px;font-weight:600}
.auth .btn{width:100%}
.filters{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
.map{border-radius:14px;border:3px solid var(--tinta);box-shadow:4px 4px 0 var(--tinta);z-index:0}
.card.late{box-shadow:4px 4px 0 var(--chile),4px 4px 0 3px var(--tinta)}
.bars{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:6px;align-items:end;height:140px}
.bar{display:grid;grid-template-rows:1fr auto;height:100%;text-align:center}.bar span{align-self:end;background:var(--chile);border:2.5px solid var(--tinta);border-bottom:0;border-radius:6px 6px 0 0;min-height:3px}
.bar small{color:var(--suave);font-size:11px;font-weight:600}
.plan.current{background:var(--cempa)}.plan.current .muted{color:var(--tinta)}.price{margin:0;font-size:15px}.price b{font:800 34px/1 var(--titulo);font-stretch:80%;letter-spacing:-.025em}.plan ul{margin:0;padding-left:18px;display:grid;gap:4px}
.auth{max-width:440px;margin:5vh auto;padding:0 16px;display:grid;gap:18px}
.auth h1{font-size:clamp(32px,9vw,44px);line-height:1.08}
.auth p.muted{color:var(--tinta);font-size:17px;font-weight:500}
.intro{display:grid;gap:12px}
.micro{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14.5px;font-weight:700;color:var(--tinta)}
.micro span{display:inline-flex;align-items:center;gap:6px}
.micro span::before{content:"";flex:none;width:18px;height:18px;border-radius:50%;border:2px solid var(--tinta);background:var(--nopal) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M5 12.5l4.2 4.2L19 7' fill='none' stroke='%231B1236' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/11px no-repeat}
"""

# Home on the shared agent dashboard kit (panel.kit_page): the kit draws its own header and top tabs, this is everything around it
# (page, notices, footer, and the same bottom bar every other page has; the kit's top tabs only show from 900 px up).
KIT_SHELL = BRAND_TOKENS + BRAND_BASE + BTN_CSS + NAV_CSS + r"""
body{margin:0;background:var(--papel);color:var(--tinta);font:400 16px/1.5 var(--texto);-webkit-font-smoothing:antialiased;overflow-x:clip;padding-bottom:calc(84px + env(safe-area-inset-bottom,0px))}
@media(min-width:900px){nav.tabs.kitnav{display:none}}
.small{font-size:14px}.muted{color:var(--suave)}
body>.notice{margin:12px max(16px,env(safe-area-inset-left,0px)) 0}
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


def site_css(design, accent, dark_mode=True):
    tokens = DESIGN_TOKENS.get(design, DESIGN_TOKENS['ciudad'])
    safe_accent = accent if re.match(r'^#[0-9a-fA-F]{6}$', accent or '') else '#1f4e79'
    safe_accent = safe_accent.lower()
    light_bg = re.search(r'--bg:(#[0-9a-fA-F]{6})', tokens).group(1)
    # A near-black or very dark accent disappears on the dark theme: swap in a light neutral there.
    dark_accent = '#d8d2c8' if luminance(safe_accent) < 0.05 else safe_accent
    dark = DARK.replace('color-scheme:dark}', '--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7d8a99;color-scheme:dark}' % (
        dark_accent, on_accent(dark_accent), accent_text(dark_accent, '#121212', dark=True)))
    return (tokens + ':root{--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7a8594}' % (
        safe_accent, on_accent(safe_accent), accent_text(safe_accent, light_bg)) + (dark if dark_mode else '') + SITE_BASE)
