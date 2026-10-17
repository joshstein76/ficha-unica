"""CSS for the agent panel and the three free-site designs (Residencia / Ciudad / Costa). Mobile-first."""

FONTS = ('https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Figtree:wght@400;500;600;700'
         '&family=Fraunces:opsz,wght@9..144,500&display=swap')

PANEL = r"""
:root{--bg:#f4f5f7;--card:#fff;--fg:#17202b;--muted:#5f6b7a;--line:#e1e5ea;--brand:#0f5c4c;--brand-2:#e7f3ef;
--warn:#8a5a00;--warn-bg:#fff4dc;--bad:#a1323a;--bad-bg:#fdecee;--ok:#1d6b45;--ok-bg:#e5f5ec;--r:12px;
--f:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#11161c;--card:#19202a;--fg:#e8edf2;--muted:#9aa6b4;--line:#2a3340;
--brand:#4cc3a3;--brand-2:#173a33;--warn:#f0c065;--warn-bg:#3a2e14;--bad:#f08a92;--bad-bg:#3b1d21;--ok:#6fd39f;--ok-bg:#15352a;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 var(--f);padding-bottom:84px}
a{color:var(--brand)}h1,h2,h3{line-height:1.2;margin:0;text-wrap:balance}h1{font-size:24px}h2{font-size:18px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px max(16px,env(safe-area-inset-left));
background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.logo{font-weight:700;letter-spacing:.14em;font-size:15px;color:var(--fg);text-decoration:none}
.logo span{color:var(--brand)}
.wrap{max-width:860px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-left)) 32px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px;display:grid;gap:12px;min-width:0}
.grid2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.stats{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px}
.stat b{display:block;font-size:26px;font-variant-numeric:tabular-nums}.stat small{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:14px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 18px;border-radius:10px;
border:1px solid var(--brand);background:var(--brand);color:#fff;font:600 16px var(--f);text-decoration:none;cursor:pointer}
.btn.ghost{background:transparent;color:var(--brand)}.btn.small{min-height:36px;padding:0 12px;font-size:14px}
.btn.wa{background:#1f8f4e;border-color:#1f8f4e}
form.stack{display:grid;gap:12px}label{display:grid;gap:4px;font-weight:600;font-size:14px}
input,select,textarea{font:16px var(--f);padding:11px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);width:100%}
textarea{min-height:120px}input[type=checkbox]{width:auto}
.check{display:flex;gap:10px;align-items:flex-start;font-weight:500}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.list{display:grid;gap:10px}
.item{display:grid;grid-template-columns:84px 1fr;gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);
border-radius:var(--r);padding:10px;text-decoration:none;color:inherit;min-width:0}
.item img,.item .ph{width:84px;height:64px;object-fit:cover;border-radius:8px;background:var(--line)}
.item b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;background:var(--line);color:var(--muted)}
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
nav.tabs{position:fixed;bottom:0;left:0;right:0;display:grid;grid-template-columns:repeat(6,1fr);background:var(--card);
border-top:1px solid var(--line);padding:6px max(4px,env(safe-area-inset-left)) calc(6px + env(safe-area-inset-bottom));z-index:9}
nav.tabs a{display:grid;justify-items:center;gap:2px;font-size:11px;color:var(--muted);text-decoration:none;padding:4px 0}
nav.tabs a.on{color:var(--brand);font-weight:700}nav.tabs svg{width:22px;height:22px}
@media(min-width:900px){body{padding-bottom:0}nav.tabs{position:static;display:flex;justify-content:center;gap:18px;border:0;
border-bottom:1px solid var(--line);padding:0}nav.tabs a{grid-auto-flow:column;font-size:14px;padding:12px 4px}}
.auth{max-width:420px;margin:6vh auto;padding:0 16px;display:grid;gap:18px}
:focus-visible{outline:3px solid var(--brand);outline-offset:2px}
"""

SITE_BASE = r"""
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 var(--body)}
img{max-width:100%;display:block}a{color:inherit}
h1,h2,h3{font-family:var(--display);font-weight:var(--dw);line-height:1.12;margin:0;text-wrap:balance}
.in{max-width:1120px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left));padding-right:max(16px,env(safe-area-inset-right))}
header.sh{position:sticky;top:0;z-index:5;background:var(--hdr);border-bottom:1px solid var(--line)}
header.sh .in{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:64px}
.brand{font-family:var(--display);font-size:22px;text-decoration:none;font-weight:var(--dw)}
.brand img{height:40px;width:auto}
.wa{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 16px;border-radius:var(--br);background:#1f8f4e;color:#fff;
text-decoration:none;font-weight:600;font-family:var(--body);font-size:15px;white-space:nowrap}
.hero{position:relative;color:#fff;background:#222}
.hero img{width:100%;height:min(68vh,560px);object-fit:cover;opacity:.78}
.hero .cap{position:absolute;inset:auto 0 0 0;padding-block:28px;background:linear-gradient(transparent,rgba(0,0,0,.62))}
.hero h1{font-size:clamp(32px,6vw,58px)}.hero p{margin:8px 0 0;max-width:56ch;opacity:.92}
.sec{padding-block:40px;display:grid;gap:22px}
.cards{display:grid;gap:20px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.lc{display:grid;gap:10px;text-decoration:none;background:var(--card);border-radius:var(--br);overflow:hidden;border:1px solid var(--line)}
.lc img{aspect-ratio:4/3;object-fit:cover;width:100%}.lc .t{padding:0 16px 16px;display:grid;gap:4px}
.lc .p{font-weight:700;font-size:19px}.lc .f{color:var(--muted);font-size:15px}
.tag{display:inline-block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}
.gal{display:grid;gap:8px;grid-template-columns:2fr 1fr;grid-auto-rows:minmax(120px,1fr)}
.gal img{width:100%;height:100%;object-fit:cover;border-radius:calc(var(--br)/2)}.gal img:first-child{grid-row:span 2}
.strip{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:6px}
.strip img{height:180px;width:auto;scroll-snap-align:start;border-radius:calc(var(--br)/2)}
@media(max-width:700px){.gal{grid-template-columns:1fr}.gal img:not(:first-child){display:none}.hero img{height:52vh}}
.lp{display:grid;gap:28px;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);align-items:start}
@media(max-width:860px){.lp{grid-template-columns:1fr}}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.facts div{background:var(--card);border:1px solid var(--line);border-radius:calc(var(--br)/2);padding:12px}
.facts b{display:block;font-size:20px}.facts small{color:var(--muted)}
.box{background:var(--card);border:1px solid var(--line);border-radius:var(--br);padding:20px;display:grid;gap:12px;position:sticky;top:84px}
.box form{display:grid;gap:10px}.box input,.box textarea{font:16px var(--body);padding:11px;border:1px solid var(--line);border-radius:8px;width:100%;background:var(--bg);color:var(--fg)}
.box button{min-height:46px;border:0;border-radius:var(--br);background:var(--accent);color:#fff;font:600 16px var(--body);cursor:pointer}
.check{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--muted)}.check input{width:auto;margin-top:4px}
.desc{white-space:pre-line;max-width:68ch}.muted{color:var(--muted)}
.am{display:flex;flex-wrap:wrap;gap:8px;padding:0;margin:0;list-style:none}.am li{border:1px solid var(--line);border-radius:99px;padding:4px 12px;font-size:14px}
.agent{display:flex;gap:14px;align-items:center}.agent .av{width:56px;height:56px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700}
footer.sf{border-top:1px solid var(--line);padding-block:28px;color:var(--muted);font-size:14px}
footer.sf .in{display:flex;flex-wrap:wrap;gap:12px 24px;justify-content:space-between}
.float{position:fixed;right:max(16px,env(safe-area-inset-right));bottom:calc(16px + env(safe-area-inset-bottom));z-index:9;box-shadow:0 6px 20px rgba(0,0,0,.25)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
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


def site_css(design, accent):
    tokens = DESIGN_TOKENS.get(design, DESIGN_TOKENS['ciudad'])
    safe_accent = accent if (accent or '').startswith('#') and len(accent) in (4, 7) else '#1f4e79'
    return tokens + ':root{--accent:%s}' % safe_accent + DARK + SITE_BASE
