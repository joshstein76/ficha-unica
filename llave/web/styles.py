"""CSS for the agent panel and the three free-site designs (Residencia / Ciudad / Costa). Mobile-first."""
import re

_FIG = 'family=Figtree:wght@400;600;700'
FONTS = 'https://fonts.googleapis.com/css2?%s&display=swap' % _FIG  # panel: Figtree only
PRECONNECT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')


def fonts_url(design):
    """Only the display family the design needs (ciudad uses Figtree for everything) + Figtree 400/600/700."""
    extra = {'residencia': 'family=Instrument+Serif&', 'costa': 'family=Fraunces:opsz,wght@9..144,500&'}.get(design, '')
    return 'https://fonts.googleapis.com/css2?%s%s&display=swap' % (extra, _FIG)

PANEL = r"""
:root{--bg:#f4f5f7;--card:#fff;--fg:#17202b;--muted:#5f6b7a;--line:#e1e5ea;--brand:#0f5c4c;--brand-2:#e7f3ef;
--on-brand:#fff;--pill:#434e5c;--field-border:#7a8594;--warn:#8a5a00;--warn-bg:#fff4dc;--bad:#a1323a;--bad-bg:#fdecee;--ok:#1d6b45;--ok-bg:#e5f5ec;--r:12px;
--f:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#11161c;--card:#19202a;--fg:#e8edf2;--muted:#9aa6b4;--line:#2a3340;
--brand:#4cc3a3;--on-brand:#0b1f1a;--pill:#b4bfcc;--field-border:#7d8a99;--brand-2:#173a33;--warn:#f0c065;--warn-bg:#3a2e14;--bad:#f08a92;--bad-bg:#3b1d21;--ok:#6fd39f;--ok-bg:#15352a;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 var(--f);padding-bottom:84px}
a{color:var(--brand)}h1,h2,h3{line-height:1.2;margin:0;text-wrap:balance}h1{font-size:24px}h2{font-size:18px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px max(16px,env(safe-area-inset-left));
background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.logo{font-weight:700;font-size:18px;color:var(--fg);text-decoration:none}
.logo span{color:var(--brand)}
.wrap{max-width:860px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-left)) 32px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px;display:grid;gap:12px;min-width:0}
.grid2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.grid2.wide{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.stats{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px}
.stat b{display:block;font-size:26px;font-variant-numeric:tabular-nums}.stat small{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:14px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 18px;border-radius:10px;
border:1px solid var(--brand);background:var(--brand);color:var(--on-brand);font:600 16px var(--f);text-decoration:none;cursor:pointer}
.btn.ghost{background:transparent;color:var(--brand)}.btn.small{min-height:36px;padding:0 12px;font-size:14px}
.btn.wa{background:#177a41;border-color:#177a41;color:#fff}
form.stack{display:grid;gap:12px}label{display:grid;gap:4px;font-weight:600;font-size:14px}
input,select,textarea{font:16px var(--f);padding:11px 12px;border-radius:10px;border:1px solid var(--field-border);background:var(--bg);color:var(--fg);width:100%}
textarea{min-height:120px}
input[type=checkbox],input[type=radio]{width:20px;height:20px;padding:0;flex:none}
.check{display:flex;gap:10px;align-items:flex-start;font-weight:500}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.list{display:grid;gap:10px}
.item{display:grid;grid-template-columns:84px 1fr;gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);
border-radius:var(--r);padding:10px;text-decoration:none;color:inherit;min-width:0}
.item img,.item .ph{width:84px;height:64px;object-fit:cover;border-radius:8px;background:var(--line)}
.item b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{justify-self:start;display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;background:var(--line);color:var(--pill)}
.pill.activa,.pill.en_feed,.pill.publicada,.pill.ok{background:var(--ok-bg);color:var(--ok)}
.pill.borrador,.pill.pausada,.pill.pendiente,.pill.dry_run{background:var(--warn-bg);color:var(--warn)}
.pill.error,.pill.sin_convenio{background:var(--bad-bg);color:var(--bad)}
.notice{border-radius:10px;padding:12px 14px;background:var(--brand-2)}.notice.err{background:var(--bad-bg);color:var(--bad)}
.notice.warn{background:var(--warn-bg);color:var(--warn)}
.thumbs{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(96px,1fr))}
.thumbs figure{margin:0;display:grid;gap:4px}.thumbs img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tbl{overflow-x:auto}
code{font-size:13px;word-break:break-all}
nav.tabs a.desk{display:none}nav.tabs{position:fixed;bottom:0;left:0;right:0;display:grid;grid-template-columns:repeat(6,1fr);background:var(--card);
border-top:1px solid var(--line);padding:6px max(4px,env(safe-area-inset-left)) calc(6px + env(safe-area-inset-bottom));z-index:9}
nav.tabs a{display:grid;justify-items:center;gap:2px;font-size:12px;color:var(--muted);text-decoration:none;padding:4px 0}
nav.tabs a.on{color:var(--brand);font-weight:700}nav.tabs svg{width:22px;height:22px}
@media(min-width:900px){body{padding-bottom:0}nav.tabs{position:static;display:flex;justify-content:center;gap:18px;border:0;
border-bottom:1px solid var(--line);padding:0}nav.tabs a{grid-auto-flow:column;font-size:14px;padding:12px 4px}nav.tabs a.desk{display:grid}}
.fab{display:none}@media(max-width:899px){.fab{display:flex;position:fixed;right:max(16px,env(safe-area-inset-right));bottom:calc(84px + env(safe-area-inset-bottom));width:56px;height:56px;border-radius:50%;font-size:28px;padding:0;z-index:8;box-shadow:0 6px 18px rgba(0,0,0,.3)}}
.wsteps{display:flex;gap:6px;flex-wrap:wrap;font-size:13px}.wsteps span{padding:4px 10px;border-radius:99px;background:var(--line);color:var(--muted)}
.wsteps .on{background:var(--brand);color:var(--on-brand)}.wsteps .done{background:var(--ok-bg);color:var(--ok)}
.bigpick{display:grid;justify-items:center;gap:6px;padding:28px 12px;border:2px dashed var(--line);border-radius:14px;cursor:pointer;text-align:center}
.bigpick{position:relative}.bigpick:focus-within{outline:3px solid var(--brand);outline-offset:2px}.bigpick span{font-size:20px;font-weight:700}.bigpick input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
fieldset{border:0;margin:0;padding:0;min-width:0}
.seg label,.chip{position:relative}
.seg{display:grid;grid-template-columns:1fr 1fr;gap:8px}.seg input,.chip input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}
.seg span,.chip span{display:flex;justify-content:center;align-items:center;min-height:44px;border:1px solid var(--field-border);border-radius:10px;cursor:pointer;font-weight:600}
.seg input:checked+span,.chip input:checked+span{border-color:var(--brand);background:var(--brand-2);color:var(--brand)}
.seg input:focus-visible+span,.chip input:focus-visible+span{outline:3px solid var(--brand)}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip span{padding:0 14px;font-weight:500}
.auth .btn{width:100%}
.filters{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
.map{border-radius:var(--r);border:1px solid var(--line);z-index:0}
.card.late{border-color:var(--bad)}
.bars{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:6px;align-items:end;height:140px}
.bar{display:grid;grid-template-rows:1fr auto;height:100%;text-align:center}.bar span{align-self:end;background:var(--brand);border-radius:6px 6px 0 0;min-height:2px}
.bar small{color:var(--muted);font-size:11px}
.plan.current{border-color:var(--brand)}.price{margin:0;font-size:15px}.price b{font-size:26px}.plan ul{margin:0;padding-left:18px;display:grid;gap:4px}
.auth{max-width:420px;margin:6vh auto;padding:0 16px;display:grid;gap:18px}
:focus-visible{outline:3px solid var(--brand);outline-offset:2px}
.vh{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.skip{position:absolute;left:8px;top:-80px;z-index:20;background:var(--brand);color:var(--on-brand);padding:10px 16px;border-radius:10px;font-weight:700;text-decoration:none}
.skip:focus{top:8px}
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


def site_css(design, accent):
    tokens = DESIGN_TOKENS.get(design, DESIGN_TOKENS['ciudad'])
    safe_accent = accent if re.match(r'^#[0-9a-fA-F]{6}$', accent or '') else '#1f4e79'
    safe_accent = safe_accent.lower()
    light_bg = re.search(r'--bg:(#[0-9a-fA-F]{6})', tokens).group(1)
    # A near-black or very dark accent disappears on the dark theme: swap in a light neutral there.
    dark_accent = '#d8d2c8' if luminance(safe_accent) < 0.05 else safe_accent
    dark = DARK.replace('color-scheme:dark}', '--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7d8a99;color-scheme:dark}' % (
        dark_accent, on_accent(dark_accent), accent_text(dark_accent, '#121212', dark=True)))
    return (tokens + ':root{--accent:%s;--on-accent:%s;--accent-text:%s;--field-border:#7a8594}' % (
        safe_accent, on_accent(safe_accent), accent_text(safe_accent, light_bg)) + dark + SITE_BASE)
