"""Public landing (app.<base>/) and public pricing (/planes, /precios when logged out), in the Ficha Única "Lotería" look
(approved by Josh 2026-11-03: papel + tinta outlines, hard shadows, colour walls, Bricolage / Shrikhand / Figtree, light only).
Server-rendered, inline CSS, one tiny inline script (live name preview + plan switch), no third-party images. Mexican Spanish, tú, mobile-first.
Never names competitors, never promises a portal that is not live. Prices and features come from panel.plan_list() so the landing, the pricing page and the panel never disagree."""
import datetime
import json

from .. import db
from .common import e, props
from .styles import BRAND_BASE, BRAND_COLOR, BRAND_TOKENS, FONTS, PRECONNECT, logo, mark_svg

CSS = BRAND_TOKENS + BRAND_BASE + r"""
:root{--sky:var(--cielo);--lilac:var(--rosa);--r:12px}
html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--papel);color:var(--tinta);font:400 17px/1.6 var(--texto);-webkit-font-smoothing:antialiased;overflow-x:clip;padding-bottom:calc(84px + env(safe-area-inset-bottom,0px))}
@media(min-width:960px){body{padding-bottom:0}}
img,svg{max-width:100%}
a{color:inherit}
h1,h2,h3{margin:0;text-wrap:balance}
h1,h2{font-family:var(--titulo);font-weight:800;font-stretch:80%;letter-spacing:-.025em}
h3{font:800 20px/1.2 var(--titulo);letter-spacing:-.01em}
p{margin:0}
.w{max-width:1160px;margin:0 auto;padding-left:max(20px,env(safe-area-inset-left,0px));padding-right:max(20px,env(safe-area-inset-right,0px))}
h2{font-size:clamp(34px,8.6vw,56px);line-height:1.02}
.eyebrow{display:inline-block;padding:6px 10px;border:2px solid var(--tinta);border-radius:6px;background:var(--blanco);color:var(--tinta);font:800 12px/1 var(--titulo);letter-spacing:.08em;text-transform:uppercase}
.lead{font-size:18px;font-weight:500;color:var(--tinta);max-width:36em}
.sec-h{display:grid;gap:12px;max-width:720px;justify-items:start}
.sec-h.c{margin:0 auto;text-align:center;justify-items:center}
section{padding-block:60px}
@media(min-width:960px){section{padding-block:104px}}
main>section+section{border-top:3px solid var(--tinta)}
mark{display:block;margin-top:6px;background:none;color:var(--jacaranda);font:400 1em/1.06 var(--carta);letter-spacing:0;font-stretch:100%;font-synthesis:none}

/* Buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:56px;padding:0 26px;border-radius:12px;border:3px solid var(--tinta);
  background:var(--chile);color:var(--tinta);font:800 18px/1.1 var(--titulo);text-decoration:none;cursor:pointer;box-shadow:4px 4px 0 var(--tinta);transition:transform .08s,box-shadow .08s}
.btn:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--tinta)}
.btn:active{transform:translate(3px,3px);box-shadow:1px 1px 0 var(--tinta)}
.btn svg{width:18px;height:18px}
.btn.alt{background:var(--blanco)}
.btn.sm{min-height:44px;padding:0 18px;font-size:15px;box-shadow:3px 3px 0 var(--tinta)}

/* Header */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:30;background:var(--cempa);border-bottom:3px solid var(--tinta)}
.bar .w{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:64px}
.nav{display:none;gap:22px}.nav a{display:inline-flex;align-items:center;min-height:44px;text-decoration:none;font-weight:700;font-size:15px;color:var(--tinta)}.nav a:hover{text-decoration:underline}
.acts{display:flex;align-items:center;gap:8px}
.acts .in{display:inline-flex;align-items:center;min-height:44px;font-weight:800;font-size:15px;text-decoration:none;padding:0 10px}
.acts .btn{display:none}
@media(min-width:960px){.nav{display:flex}.acts .btn{display:inline-flex}}

/* Hero: a cempa wall */
.hero{position:relative;overflow:hidden;padding-block:30px 56px;background:var(--cempa)}
.hero .w{position:relative;display:grid;gap:44px}
.hero .w>*{min-width:0}
.pill{display:inline-flex;align-items:center;gap:10px;padding:6px 14px 6px 8px;border-radius:99px;border:2.5px solid var(--tinta);background:var(--blanco);box-shadow:2px 2px 0 var(--tinta);font-size:14.5px;font-weight:700;color:var(--tinta)}
.pill .mark{flex:none;width:28px;height:28px;display:block}
h1{margin-top:18px;font-size:clamp(42px,11.5vw,66px);line-height:1}
.hero .lead{margin-top:16px}
.cta-row{margin-top:24px;display:flex;flex-wrap:wrap;gap:14px}
.micro{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px 16px;font-size:14.5px;font-weight:700;color:var(--tinta)}
.micro span{display:inline-flex;align-items:center;gap:6px}
.micro svg{width:17px;height:17px;color:var(--tinta)}

/* The example agent site (the hero picture) with floating cards */
.stage{position:relative;width:100%;margin:0 auto;padding:6px 0 0}
.browser{position:relative;background:var(--blanco);border:3px solid var(--tinta);border-radius:14px;overflow:hidden;box-shadow:6px 6px 0 var(--tinta)}
.bchrome{display:flex;align-items:center;gap:6px;padding:9px 12px;background:var(--papel);border-bottom:3px solid var(--tinta)}
.bchrome i{width:10px;height:10px;border:1.5px solid var(--tinta);border-radius:50%;background:var(--chile)}
.bchrome i:nth-child(2){background:var(--cempa)}.bchrome i:nth-child(3){background:var(--nopal)}
.burl{flex:1;min-width:0;margin-left:8px;display:flex;align-items:center;gap:6px;background:var(--blanco);border:2px solid var(--tinta);border-radius:99px;padding:4px 12px;font-size:12px;font-weight:700;color:var(--tinta)}
.burl svg{flex:none;width:11px;height:11px;color:var(--tinta)}
.burl span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.site{container-type:inline-size;font-size:12px;color:#1A1A22;background:#fff}
.shd{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #EEE}
.slogo{display:flex;align-items:center;gap:7px;min-width:0;font-weight:800;font-size:13.5px;letter-spacing:-.02em}
.slogo b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sini{flex:none;width:24px;height:24px;border-radius:7px;background:#1F4E79;color:#fff;display:grid;place-items:center;font-size:10px;font-weight:800;letter-spacing:0}
.snav{display:none;margin-left:auto;gap:14px;color:#55555F;font-weight:600}
.wa-pill{margin-left:auto;flex:none;display:inline-flex;align-items:center;gap:5px;background:#177A41;color:#fff;font-weight:700;font-size:11px;padding:6px 10px;border-radius:99px}
.wa-pill svg{width:12px;height:12px}
.shero{position:relative;aspect-ratio:16/8.4;overflow:hidden}
.shero img{width:100%;height:100%;object-fit:cover;object-position:50% 62%;display:block}
.shero::after{content:"";position:absolute;inset:0;background:rgba(27,18,54,.42)}
.sh-in{position:absolute;z-index:1;left:12px;right:12px;bottom:10px;display:grid;gap:7px}
.sh-in>b{color:#fff;font-size:17px;line-height:1.15;letter-spacing:-.02em}
.ssearch{display:flex;align-items:center;gap:6px;background:#fff;border:2px solid var(--tinta);border-radius:10px;padding:5px;box-shadow:2px 2px 0 var(--tinta)}
.seg2{display:flex;background:#F2F2F6;border-radius:7px;padding:2px;flex:none}
.seg2 em{font-style:normal;font-weight:700;font-size:10.5px;padding:4px 7px;border-radius:5px;color:#55555F}
.seg2 em.on{background:#fff;color:#1A1A22;box-shadow:inset 0 0 0 1px #D5D5DE}
.sq{flex:1;min-width:0;color:#6B6B7C;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sbtn{flex:none;background:#1F4E79;color:#fff;font-weight:700;padding:6px 10px;border-radius:7px}
.slist{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:11px 11px 42px}
.slist .scard:nth-child(4){display:none}
.slt{grid-column:1/-1;font-weight:800;font-size:13px;letter-spacing:-.02em}
.scard{border-radius:10px;overflow:hidden;box-shadow:0 0 0 1px #ECECF1;background:#fff}
.scard img{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;display:block}
.scard div{padding:7px 8px 9px;display:grid;gap:1px}
.sop{justify-self:start;font-size:9.5px;font-weight:800;color:#1F4E79;background:#E8F0F8;padding:2px 6px;border-radius:99px;margin-bottom:3px}
.scard b{font-size:13px;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.scard b small{font-size:10px;color:#66667A;font-weight:600}
.scard p{font-size:10.5px;color:#55555F;line-height:1.35}
@container (min-width:520px){.snav{display:flex}.shero{aspect-ratio:16/7}.sh-in{left:20px;right:auto;width:62%;bottom:16px}.sh-in>b{font-size:22px}
  .slist{grid-template-columns:repeat(3,1fr)}.slist .scard:nth-child(4){display:block}.site{font-size:12.5px}}
.exl{flex:none;padding:4px 8px;border:2px solid var(--tinta);border-radius:6px;background:var(--cempa);color:var(--tinta);font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}
.fc{position:absolute;background:var(--blanco);border:3px solid var(--tinta);border-radius:14px;box-shadow:4px 4px 0 var(--tinta);padding:12px}
.fc.pubc{position:relative;display:none;z-index:4;padding:10px 12px}
@media(min-width:960px){.fc.pubc{display:block}}
.fc .t{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13.5px;font-weight:800}
.fc .t em{font-style:normal;font-size:11px;font-weight:800;padding:3px 7px;border:2px solid var(--tinta);border-radius:6px;background:var(--cempa);color:var(--tinta);letter-spacing:.04em;text-transform:uppercase}
.chk{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:7px}
.chk li{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--tinta)}
.chk i{flex:none;width:20px;height:20px;border:2px solid var(--tinta);border-radius:50%;display:grid;place-items:center;background:var(--nopal);color:var(--tinta)}
.chk i svg{width:11px;height:11px}
.chk li.wait i{background:var(--blanco);color:transparent}
.chk li.wait{color:var(--suave)}
.fc.inc{position:relative;margin:-34px 0 0 auto;width:min(290px,82%);z-index:4}
.who{display:flex;align-items:center;gap:10px}
.av{flex:none;width:36px;height:36px;border:2.5px solid var(--tinta);border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:14px;color:var(--tinta);background:var(--rosa)}
.who b{display:block;font-size:14px}
.who small{display:block;font-size:12.5px;color:var(--suave)}
.wa{margin-left:auto;flex:none;width:32px;height:32px;border:2.5px solid var(--tinta);border-radius:50%;background:var(--nopal);display:grid;place-items:center;color:var(--tinta)}
.wa svg{width:16px;height:16px}
.bub{margin-top:9px;background:var(--papel);border:2px solid var(--tinta);border-radius:4px 14px 14px 14px;padding:9px 11px;font-size:14px;line-height:1.45;color:var(--tinta)}
.anim .fc{animation:pop .5s cubic-bezier(.3,1.5,.5,1) both}
.anim .fc.pubc{animation-delay:.3s}.anim .fc.inc{animation-delay:.55s}
@keyframes pop{from{transform:translateY(18px) scale(.97)}to{transform:none}}
.anim .float{animation:pop .5s cubic-bezier(.3,1.5,.5,1) .55s both,bob 7s ease-in-out 1.4s infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@media(min-width:960px){
  .hero{padding-block:64px 170px}
  .hero .w{grid-template-columns:.9fr 1.1fr;align-items:center;gap:56px}
  .slist{padding-bottom:11px}
  .fc.inc{position:absolute;left:-44px;bottom:-122px;margin:0;width:280px}
  .fc.pubc{position:absolute;right:-18px;top:96px}
}

/* Name box in the hero */
.namebox{margin-top:22px;display:grid;gap:10px;max-width:460px}
.namebox label{font-size:15px;font-weight:800;color:var(--tinta)}
.field{display:flex;align-items:center;background:var(--blanco);border:3px solid var(--tinta);border-radius:12px;box-shadow:4px 4px 0 var(--tinta);padding:4px 4px 4px 16px}
.field:focus-within{outline:3px solid var(--jacaranda);outline-offset:3px}
.field input{flex:1;min-width:0;border:0;background:transparent;color:var(--tinta);font:800 18px var(--texto);padding:10px 0;outline:none}
.urlb{display:flex;align-items:center;gap:8px;min-width:0;padding:9px 12px;border:2.5px solid var(--tinta);border-radius:10px;background:var(--blanco);font-weight:700;font-size:15px;color:var(--tinta)}
.urlb svg{flex:none;width:16px;height:16px;color:var(--tinta)}
.urlb span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.urlb b{color:var(--jacaranda)}
.urlb em{flex:none;font-style:normal;font-size:11px;font-weight:800;padding:3px 7px;border:2px solid var(--tinta);border-radius:6px;background:var(--cempa);color:var(--tinta);letter-spacing:.04em;text-transform:uppercase}
.urlb.dom{background:var(--sky)}.urlb.dom b{color:var(--tinta)}.urlb.dom em{background:var(--tinta);color:var(--papel)}
.hero .cta-row{margin-top:16px}

/* The four things nobody else gives you */
.pill-s{background:var(--papel)}
.pillars{margin-top:30px;display:grid;gap:18px}
.pl{background:var(--blanco);border:3px solid var(--tinta);border-radius:14px;padding:22px;box-shadow:4px 4px 0 var(--tinta);display:grid;gap:12px;align-content:start;min-width:0}
.pl .ic{width:52px;height:52px;border:2.5px solid var(--tinta);border-radius:12px;display:grid;place-items:center}
.pl .ic svg{width:26px;height:26px;color:var(--tinta)}
.pl h3{font-size:22px}
.pl p{color:var(--tinta);font-size:16.5px}
.pl .txt{display:grid;gap:12px;align-content:start}
.pl.feat{gap:18px}
.chat{background:#EFE7DD;border:3px solid var(--tinta);border-radius:14px;padding:12px;display:grid;gap:8px;min-width:0}
.chd{display:flex;align-items:center;gap:10px;padding:4px 4px 8px;border-bottom:2px solid var(--tinta)}
.chd b{display:block;font-size:14.5px}.chd small{display:block;font-size:12px;color:#4A5651}
.chd .exl{margin-left:auto}
.chat p{max-width:86%;padding:9px 11px;font-size:14.5px;line-height:1.45;border:2px solid var(--tinta);border-radius:4px 14px 14px 14px;background:#fff;color:#1A1A22}
.chat p.out{justify-self:end;border-radius:14px 4px 14px 14px;background:#D9FDD3}
.chat .lk{display:block;margin-top:4px;color:#0B6E99;font-size:12.5px;overflow-wrap:anywhere}
.urlb.sm2{font-size:14px}
.where{list-style:none;margin:2px 0 0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.where li{display:flex;align-items:center;gap:8px;padding:10px;border:2px solid var(--tinta);border-radius:10px;background:var(--papel);font-size:14px;font-weight:700;color:var(--tinta)}
.where i{flex:none;width:20px;height:20px;border:2px solid var(--tinta);border-radius:50%;display:grid;place-items:center;background:var(--nopal);color:var(--tinta)}
.where i svg{width:12px;height:12px}
.where li.wait{color:var(--suave)}.where li.wait i{background:var(--blanco)}
@media(min-width:760px){.pillars{grid-template-columns:repeat(3,1fr)}.pl.feat{grid-column:1/-1;grid-template-columns:1fr 1fr;align-items:center;padding:30px;gap:34px}}

/* Steps: a cielo wall */
#como{background:var(--cielo)}
.steps{margin-top:32px;list-style:none;padding:0;display:grid;gap:0}
.steps li{position:relative;display:grid;grid-template-columns:52px 1fr;gap:16px;padding-bottom:24px}
.steps li:not(:last-child)::before{content:"";position:absolute;left:24px;top:52px;bottom:0;width:3px;background:var(--tinta)}
.steps .n{width:52px;height:52px;border:3px solid var(--tinta);border-radius:50%;display:grid;place-items:center;font:800 22px/1 var(--titulo);background:var(--blanco);color:var(--tinta);box-shadow:3px 3px 0 var(--tinta)}
.steps li:last-child .n{background:var(--chile)}
.steps h3{font-size:20px;margin-top:12px}
.steps p{color:var(--tinta);font-size:16px;font-weight:500}
@media(min-width:960px){.steps{grid-template-columns:repeat(3,1fr);gap:28px}.steps li{grid-template-columns:1fr;padding:0}.steps li:not(:last-child)::before{left:64px;right:-14px;top:24px;bottom:auto;width:auto;height:3px}}

/* Plans */
.pseg{display:none;margin-top:24px;gap:6px;padding:5px;border:3px solid var(--tinta);border-radius:99px;background:var(--blanco)}
.js .pseg{display:inline-flex}
.pseg button{min-height:44px;border:2.5px solid transparent;background:transparent;color:var(--tinta);font:800 15px var(--titulo);padding:0 18px;border-radius:99px;cursor:pointer}
.pseg button[aria-pressed="true"]{background:var(--cempa);border-color:var(--tinta)}
.plans{margin-top:20px;display:grid;gap:22px}
.plan{background:var(--blanco);border:3px solid var(--tinta);border-radius:14px;padding:24px;box-shadow:4px 4px 0 var(--tinta);display:grid;gap:16px;align-content:start;position:relative}
.plan.top{box-shadow:6px 6px 0 var(--chile),6px 6px 0 3px var(--tinta)}
.plan .nm{display:flex;justify-content:space-between;align-items:center;gap:8px;font:800 20px/1.2 var(--titulo)}
.plan .badge{font-size:12px;font-weight:800;padding:4px 8px;border:2px solid var(--tinta);border-radius:6px;background:var(--nopal);color:var(--tinta);letter-spacing:.04em;text-transform:uppercase}
.plan .badge.soft{background:var(--cempa)}
.price{display:flex;align-items:baseline;gap:8px}
.price b{font:800 52px/1 var(--titulo);font-stretch:80%;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.price small{color:var(--suave);font-size:14.5px;line-height:1.3}
.plan ul{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.plan li{display:flex;gap:10px;font-size:15.5px;line-height:1.45;color:var(--tinta)}
.plan li svg{flex:none;width:19px;height:19px;color:var(--tinta);margin-top:2px}
.plan .btn{width:100%}
.fine2{margin-top:16px;font-size:14.5px;font-weight:500;color:var(--suave)}
.page{padding-block:44px 72px}
.page h1{margin:0;font-size:clamp(36px,8.6vw,56px);line-height:1}
@media(max-width:959px){.js .plans[data-on="gratis"] .plan:not([data-k="gratis"]),.js .plans[data-on="pro"] .plan:not([data-k="pro"]),.js .plans[data-on="ia"] .plan:not([data-k="ia"]){display:none}}
@media(min-width:960px){.pseg,.js .pseg{display:none}.plans{grid-template-columns:repeat(3,1fr);gap:26px}.page{padding-block:80px 120px}}

/* FAQ: a rosa wall */
#preguntas{background:var(--rosa)}
.faq{margin-top:22px;display:grid;gap:12px}
.faq details{background:var(--blanco);border:3px solid var(--tinta);border-radius:12px;box-shadow:3px 3px 0 var(--tinta)}
.faq summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 16px;font-weight:700;font-size:16.5px;line-height:1.35;min-height:56px}
.faq summary::-webkit-details-marker{display:none}
.faq summary i{flex:none;width:32px;height:32px;border:2px solid var(--tinta);border-radius:8px;display:grid;place-items:center;background:var(--cempa);color:var(--tinta);transition:transform .08s}
.faq summary i svg{width:14px;height:14px}
.faq details[open] summary i{transform:rotate(45deg)}
.faq details p{padding:0 16px 16px;color:var(--tinta);font-size:16px}
@media(min-width:960px){.faq-g{display:grid;grid-template-columns:.8fr 1.2fr;gap:56px;align-items:start}.faq{margin-top:0}}

/* Final CTA */
.final{padding-block:56px 64px}
.fin{border:3px solid var(--tinta);border-radius:16px;background:var(--chile);color:var(--tinta);padding:44px 24px;display:grid;gap:16px;text-align:center;justify-items:center;box-shadow:6px 6px 0 var(--tinta)}
.fin p{color:var(--tinta);font-size:17px;max-width:30em;font-weight:600}
@media(min-width:960px){.final{padding-block:80px 104px}.fin{padding:80px 48px}}

/* Footer */
footer{border-top:3px solid var(--tinta);padding-block:40px 28px;background:var(--papel)}
.fg{display:grid;gap:26px}
.fg h4{margin:0 0 8px;font:800 13px/1.2 var(--titulo);letter-spacing:.06em;text-transform:uppercase;color:var(--suave)}
.fg a{display:block;padding:10px 0;text-decoration:none;color:var(--tinta);font-size:15.5px;font-weight:500}
.fg a.logo{display:inline-flex;font-size:22px;padding:0;font-weight:400}
.fg .about p{margin-top:10px;color:var(--suave);font-size:15px;max-width:24em}
.legal{margin-top:30px;padding-top:18px;border-top:2px solid var(--tinta);font-size:14px;color:var(--suave);display:flex;flex-wrap:wrap;gap:6px 18px;justify-content:space-between}
@media(min-width:760px){.fg{grid-template-columns:1.4fr 1fr 1fr 1fr}}

/* Sticky phone CTA */
.sticky{position:fixed;z-index:40;left:0;right:0;bottom:0;padding:10px max(16px,env(safe-area-inset-right,0px)) calc(10px + env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px));background:var(--blanco);border-top:3px solid var(--tinta)}
.sticky .btn{width:100%}
@media(min-width:960px){.sticky{display:none}}
"""

_SPRITE = (
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">'
    '<symbol id="i-ar" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-ok" viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></symbol>'
    '<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></symbol>'
    '<symbol id="i-wa" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2c-1.5 0-3-.4-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5c-.2 0-.4.1-.7.3-.2.3-.9.9-.9 2.2s.9 2.5 1 2.7c.1.2 1.8 2.8 4.4 3.9 1.6.7 2.3.8 3.1.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1 0-.3-.1-.5-.2z"/></symbol>'
    '<symbol id="i-sheet2" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 9h16" stroke="currentColor" stroke-width="2"/><circle cx="7" cy="6.5" r=".9" fill="currentColor"/><circle cx="9.6" cy="6.5" r=".9" fill="currentColor"/></symbol>'
    '<symbol id="i-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5s1.2-6.1 3.6-8.5z" fill="none" stroke="currentColor" stroke-width="2"/></symbol>'
    '<symbol id="i-share" viewBox="0 0 24 24"><circle cx="6" cy="12" r="2.6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="18" cy="6" r="2.6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="18" cy="18" r="2.6" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.3 10.8l7.4-3.6M8.3 13.2l7.4 3.6" stroke="currentColor" stroke-width="2"/></symbol>'
    '<symbol id="i-lock" viewBox="0 0 24 24"><rect x="5" y="10.5" width="14" height="10" rx="2.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" fill="none" stroke="currentColor" stroke-width="2.2"/></symbol>'
    '</svg>')

# Live name preview (hero) + plan switch (phones). Plain script, no external file.
_JS_LIVE = r"""
(function(){var i=document.getElementById('marca');if(!i)return;
var g=document.getElementById('go'),base=g?g.getAttribute('href'):'';
var slug=function(s){return (s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,40)||'tu-inmobiliaria'};
var each=function(sel,fn){document.querySelectorAll(sel).forEach(fn)};
var paint=function(){var raw=(i.value||'').trim(),n=raw||'Tu inmobiliaria',s=slug(n);
each('[data-name]',function(el){el.textContent=n});each('[data-slug]',function(el){el.textContent=s});
each('[data-dom]',function(el){el.textContent=s.replace(/-/g,'')});
var ini=n.split(/\s+/).filter(Boolean).slice(0,2).map(function(w){return w[0]}).join('').toUpperCase()||'TU';
each('[data-ini]',function(el){el.textContent=ini});
if(g)g.setAttribute('href',base+(base.indexOf('?')<0?'?':'&')+'marca='+encodeURIComponent(raw))};
i.addEventListener('input',paint);paint()})();
"""
_JS_PLANS = r"""
var pb=document.querySelectorAll('.pseg button'),pl=document.getElementById('plans');
if(pl)pb.forEach(function(b){b.addEventListener('click',function(){pb.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false')});pl.setAttribute('data-on',b.getAttribute('data-p'))})});
"""


def _script(*parts):
    return "<script>(function(){document.documentElement.classList.add('js');var rm=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;" \
           "if(!rm)document.body.classList.add('anim');%s})();</script>" % ''.join(parts)


def _faq(gratis_limit):
    return [
        ('¿De verdad es gratis?',
         'Sí. El plan Gratis incluye tu sitio en una dirección de Ficha Única y %s. No pedimos tarjeta para empezar. '
         'Si luego quieres tu propio dominio o más propiedades, hay planes de pago.' % props(gratis_limit)),
        ('¿Cómo me llegan los clientes?',
         'Cada persona que te escribe desde tu sitio te llega por WhatsApp, con su nombre y la propiedad que le interesó. Tú contestas como siempre.'),
        ('¿Puedo usar mi propio dominio?',
         'Muy pronto, con el plan Pro. El dominio lo compras tú con el proveedor que quieras. '
         'Mientras, tu sitio funciona en tu dirección gratis de Ficha Única.'),
        ('¿Mis propiedades salen en los portales?',
         'Salen en tu sitio y en Google. Los portales los conectamos conforme cada uno nos da su acceso; en tu panel ves cuáles están activos y cuáles no. '
         'Nunca te prometemos un portal que todavía no funciona.'),
        ('¿Necesito saber de computadoras?',
         'No. Se hace desde el celular: subes las fotos, escribes los datos una sola vez y listo. '
         'Con el plan Pro, si ya tienes tus propiedades en una hoja de Excel o CSV, también las puedes importar.'),
    ]


FAQ = _faq(db.PLAN_LIMITS['gratis'])  # today's answers; faq_items() follows LLAVE_PLANS_V2


def faq_items():
    return _faq(db.plan_limits()['gratis'])


_CHECK = '<svg><use href="#i-ok"/></svg>'

_HERO = r"""
<section class="hero" aria-labelledby="h1">
  <div class="w">
    <div>
      <span class="pill">@@PILLMARK@@Para todos los asesores de México</span>
      <h1 id="h1">Tu sitio gratis. Tus clientes, <mark>directo a tu WhatsApp.</mark></h1>
      <p class="lead">Sube cada propiedad una vez. Sale en tu sitio y en Google, lista para la IA, y quien la ve te escribe a tu WhatsApp.</p>
      <div class="namebox" id="crear">
        <label for="marca">¿Cómo se llama tu inmobiliaria?</label>
        <div class="field"><input id="marca" value="Casa Coyoacán" maxlength="40" autocomplete="organization" spellcheck="false"></div>
        <div class="urlb" id="url" aria-live="polite"><svg><use href="#i-lock"/></svg><span><b data-slug>casa-coyoacan</b>.@@BASE@@</span><em>Gratis</em></div>
      </div>
      <div class="cta-row"><a class="btn" id="go" href="@@REG@@">Crear mi sitio gratis <svg><use href="#i-ar"/></svg></a></div>
      <p class="micro"><span><svg><use href="#i-ok"/></svg>Sin tarjeta</span><span><svg><use href="#i-ok"/></svg>Sin plazo forzoso</span><span><svg><use href="#i-ok"/></svg>Desde tu celular</span></p>
    </div>

    <div class="stage" role="img" aria-label="Ejemplo del sitio de un asesor hecho con Ficha Única, con buscador, propiedades y botón de WhatsApp">
      <div class="browser">
        <div class="bchrome"><i></i><i></i><i></i><span class="burl"><svg><use href="#i-lock"/></svg><span><span data-slug>casa-coyoacan</span>.@@BASE@@</span></span><span class="exl">Ejemplo</span></div>
        <div class="site">
          <div class="shd"><span class="slogo"><span class="sini" data-ini>CC</span><b data-name>Casa Coyoacán</b></span><span class="snav"><span>Propiedades</span><span>Vende tu casa</span><span>Contacto</span></span><span class="wa-pill"><svg><use href="#i-wa"/></svg>WhatsApp</span></div>
          <div class="shero"><img src="/_s/u-casa-2-pisos.webp" alt="" width="900" height="599" decoding="async"><div class="sh-in"><b>Encuentra tu casa con <span data-name>Casa Coyoacán</span></b>
            <div class="ssearch"><span class="seg2"><em class="on">Comprar</em><em>Rentar</em></span><span class="sq">Colonia o ciudad</span><span class="sbtn">Buscar</span></div></div></div>
          <div class="slist">
            <span class="slt">Propiedades</span>
            <div class="scard"><img src="/_s/u-depa-sala-balcon.webp" alt="" width="640" height="426" loading="lazy" decoding="async"><div><span class="sop">En renta</span><b>$18,500 <small>/mes</small></b><p>Depa con balcón · Narvarte</p><p>2 rec · 1 baño · 72 m²</p></div></div>
            <div class="scard"><img src="/_s/u-sala.webp" alt="" width="640" height="360" loading="lazy" decoding="async"><div><span class="sop">En venta</span><b>$2,950,000</b><p>Casa en Juriquilla, Qro.</p><p>3 rec · 2 baños · 160 m²</p></div></div>
            <div class="scard"><img src="/_s/u-depa-comedor.webp" alt="" width="640" height="426" loading="lazy" decoding="async"><div><span class="sop">En venta</span><b>$1,850,000</b><p>Depa en Roma Sur</p><p>1 rec · 1 baño · 48 m²</p></div></div>
          </div>
        </div>
      </div>
      <div class="fc pubc"><div class="t">Publicada en <em>Hoy</em></div>
        <ul class="chk"><li><i><svg><use href="#i-ok"/></svg></i>Tu sitio</li><li><i><svg><use href="#i-ok"/></svg></i>Google</li><li class="wait"><i></i>Portales, cuando se activen</li></ul></div>
      <div class="fc inc float">
        <div class="who"><span class="av">L</span><span><b>Laura</b><small>Ejemplo · hace 2 min</small></span><span class="wa"><svg><use href="#i-wa"/></svg></span></div>
        <p class="bub">Hola, ¿sigue disponible el depa con balcón?</p>
      </div>
    </div>
  </div>
</section>
"""

_PILLARS = r"""
<section class="pill-s" id="funciones" aria-labelledby="h-pl">
  <div class="w">
    <div class="sec-h"><span class="eyebrow">Lo que nadie más te da</span><h2 id="h-pl">Todo lo que necesitas. Nada que no.</h2></div>
    <div class="pillars">
      <article class="pl feat">
        <div class="txt">
          <span class="ic" style="background:var(--ok-soft)"><svg><use href="#i-wa"/></svg></span>
          <h3>Cada cliente, directo a tu WhatsApp</h3>
          <p>Tu sitio y cada propiedad llevan un botón de WhatsApp. El cliente te escribe con la propiedad que vio y tú contestas desde tu celular, como siempre.</p>
        </div>
        <div class="chat" role="img" aria-label="Ejemplo de conversación: una clienta pregunta por una propiedad y el asesor le contesta">
          <div class="chd"><span class="av">L</span><span><b>Laura</b><small>en línea</small></span><span class="exl">Ejemplo</span></div>
          <p class="in">Hola, me interesa esta propiedad: <b>Depa con balcón en Narvarte</b><br><span class="lk"><span data-slug>casa-coyoacan</span>.@@BASE@@/depa-balcon</span></p>
          <p class="out">¡Hola Laura! Sí está disponible. ¿Te gustaría verlo el sábado?</p>
        </div>
      </article>
      <article class="pl">
        <span class="ic" style="background:var(--o-soft)"><svg><use href="#i-sheet2"/></svg></span>
        <h3>Tu sitio web, gratis</h3>
        <p>Con tu nombre, tus propiedades y 3 diseños para elegir. Sin tarjeta, para siempre.</p>
        <div class="urlb sm2"><svg><use href="#i-lock"/></svg><span><b data-slug>casa-coyoacan</b>.@@BASE@@</span><em>Gratis</em></div>
      </article>
      <article class="pl">
        <span class="ic" style="background:var(--sky)"><svg><use href="#i-globe"/></svg></span>
        <h3>¿Tu propio dominio? Con Pro, muy pronto</h3>
        <p>Muy pronto: con Pro conectarás tu dominio, como el de abajo. El dominio lo compras aparte con tu proveedor.</p>
        <div class="urlb sm2 dom"><svg><use href="#i-lock"/></svg><span>www.<b data-dom>casacoyoacan</b>.mx</span><em>Pro</em></div>
      </article>
      <article class="pl">
        <span class="ic" style="background:var(--lilac)"><svg><use href="#i-share"/></svg></span>
        <h3>Publica una vez, sale en todas partes</h3>
        <p>Tu sitio y Google desde el primer día, y cada ficha lista para la IA. Los portales los vamos conectando; en tu panel ves cuáles están activos.</p>
        <ul class="where">
          <li><i><svg><use href="#i-ok"/></svg></i>Tu sitio</li>
          <li><i><svg><use href="#i-ok"/></svg></i>Google</li>
          <li><i><svg><use href="#i-ok"/></svg></i>Lista para ChatGPT</li>
          <li class="wait"><i></i>Portales, cuando se activen</li>
        </ul>
      </article>
    </div>
  </div>
</section>
"""

_STEPS = r"""
<section id="como" aria-labelledby="h-como">
  <div class="w">
    <div class="sec-h c"><span class="eyebrow">Así de fácil</span><h2 id="h-como">Tu sitio en línea en 3 pasos</h2></div>
    <ol class="steps">
      <li><span class="n" aria-hidden="true">1</span><div><h3>Crea tu cuenta</h3><p>Tu nombre, tu WhatsApp y el nombre de tu marca. Sin tarjeta.</p></div></li>
      <li><span class="n" aria-hidden="true">2</span><div><h3>Sube tu primera propiedad</h3><p>Fotos y datos desde el celular. Una sola vez.</p></div></li>
      <li><span class="n" aria-hidden="true">3</span><div><h3>Listo, ya estás en línea</h3><p>Tu sitio se publica y los clientes te escriben por WhatsApp.</p></div></li>
    </ol>
  </div>
</section>
"""

_FAQ_SEC = r"""
<section id="preguntas" aria-labelledby="h-faq">
  <div class="w faq-g">
    <div class="sec-h"><span class="eyebrow">Preguntas</span><h2 id="h-faq">Lo que todos preguntan.</h2></div>
    <div class="faq">@@FAQ@@</div>
  </div>
</section>
"""

_FINAL = r"""
<section class="final" aria-labelledby="h-fin">
  <div class="w">
    <div class="fin">
      <h2 id="h-fin">Empieza hoy. Es gratis.</h2>
      <p>Sin tarjeta y sin compromiso. Tu primera propiedad, en línea hoy mismo.</p>
      <a class="btn alt" href="@@REG@@">Crear mi sitio gratis <svg><use href="#i-ar"/></svg></a>
    </div>
  </div>
</section>
"""


def _fill(html, **kw):
    for k, v in kw.items():
        html = html.replace('@@%s@@' % k.upper(), v)
    return html


def _plans():
    from . import panel  # lazy: panel imports this module
    return panel.plan_list(), panel.COMING_SOON


def _plan_cards(reg):
    """The three plan cards, straight from panel.plan_list() (one source for prices and features)."""
    plans, soon = _plans()
    badges = {'gratis': '<span class="badge">Para todos</span>', 'ia': '<span class="badge soft">Con IA</span>'}
    out = []
    for k, name, price, feats in plans:
        badge = '<span class="badge soft">Próximamente</span>' if k in soon else badges.get(k, '')
        pr = ('<b>$%d</b> <small>MXN al mes,<br>IVA incluido</small>' % price) if price else '<b>$0</b> <small>para siempre</small>'
        cta = '' if k in soon else '<a class="btn%s" href="%s">%s</a>' % (
            '' if k == 'gratis' else ' alt', e(reg), 'Crear mi sitio gratis' if k == 'gratis' else 'Empezar gratis')
        out.append('<div class="card plan%s" data-k="%s"><div class="nm">%s %s</div><div class="price">%s</div><ul>%s</ul>%s</div>' % (
            ' top' if k == 'gratis' else '', e(k), e(name), badge, pr,
            ''.join('<li>%s%s</li>' % (_CHECK, e(f)) for f in feats), cta))
    return ''.join(out)


def _plan_switch():
    plans, _ = _plans()
    return ('<div class="pseg" role="group" aria-label="Elige un plan">%s</div>' % ''.join(
        '<button type="button" data-p="%s" aria-pressed="%s">%s</button>' % (e(k), 'true' if i == 0 else 'false', e(name))
        for i, (k, name, _p, _f) in enumerate(plans)))


def _head(title, desc, extra=''):
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s</title><meta name="description" content="%s"><meta property="og:title" content="%s"><meta property="og:description" content="%s">'
            '<meta property="og:locale" content="es_MX"><meta name="theme-color" content="%s">'
            '<link rel="icon" type="image/png" href="/_s/icon-192.png"><link rel="apple-touch-icon" href="/_s/apple-touch-icon.png">%s'
            '<link rel="stylesheet" href="%s"><style>%s</style>%s</head>') % (
        e(title), e(desc), e(title), e(desc), BRAND_COLOR, PRECONNECT, FONTS, CSS, extra)


def _top(reg, home=False):
    app = db.origin('app')
    p = '' if home else '/'
    return ('<body><a class="skip" href="#main">Saltar al contenido</a>%s<header class="bar"><div class="w">'
            '<a class="logo" href="/" aria-label="Ficha Única, inicio">%s</a>'
            '<nav class="nav" aria-label="Principal"><a href="%s#funciones">Funciones</a><a href="%s#como">Cómo funciona</a><a href="%s">Planes</a>'
            '<a href="%s#preguntas">Preguntas</a><a href="/propiedades">Ver propiedades</a></nav>'
            '<div class="acts"><a class="in" href="%s/entrar">Entrar</a><a class="btn sm" href="%s">Crear mi sitio gratis</a></div>'
            '</div></header>') % (_SPRITE, logo('fu-top'), p, p, '#planes' if home else '/planes', p, e(app), e(reg))


def _foot(reg, local, home=False):
    app = db.origin('app')
    p = '' if home else '/'
    return ('<footer><div class="w"><div class="fg">'
            '<div class="about"><a class="logo" href="/">%s</a><p>El sitio gratis para todos los asesores inmobiliarios de México. Ficha Única es un servicio de %s.</p></div>'
            '<div><h4>Producto</h4><a href="%s#funciones">Funciones</a><a href="%s#como">Cómo funciona</a><a href="%s">Planes</a><a href="/propiedades">Ver propiedades</a></div>'
            '<div><h4>Ayuda</h4><a href="%s#preguntas">Preguntas frecuentes</a><a href="%s/entrar">Entrar</a><a href="%s">Crear mi sitio</a></div>'
            '<div><h4>Legal</h4><a href="%s/terminos">Términos</a><a href="%s/privacidad">Aviso de privacidad</a></div>'
            '</div><div class="legal"><span>© %d Ficha Única · Un producto de %s</span><span>Hecho en México</span></div>%s</div></footer>'
            '<div class="sticky"><a class="btn" href="%s">Crear mi sitio gratis <svg><use href="#i-ar"/></svg></a></div>') % (
        logo('fu-foot'), e(db.OWNER), p, p, '#planes' if home else '/planes', p, e(app), e(reg), e(app), e(app),
        datetime.date.today().year, e(db.OWNER),
        '' if not local else '<p class="fine2">Versión local de prueba. Nada aquí es público todavía.</p>', e(reg))


def _reg(ref=''):
    return '%s/registro%s' % (db.origin('app'), ('?ref=' + ref) if ref else '')


def landing(ref=''):
    reg = _reg(ref)
    local = db.ENV != 'production'
    desc = 'Tu sitio inmobiliario gratis y tus clientes directo a tu WhatsApp. Sube cada propiedad una vez: sale en tu sitio y en Google, lista para la IA. Hecho en México.'
    ld = json.dumps({'@context': 'https://schema.org', '@graph': [
        {'@type': 'Organization', 'name': db.BRAND, 'parentOrganization': {'@type': 'Organization', 'name': db.OWNER}},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq_items()]}]},
        ensure_ascii=False).replace('</', '<\\/')
    plans = ('<section id="planes" aria-labelledby="h-plans"><div class="w"><div class="sec-h"><span class="eyebrow">Planes</span>'
             '<h2 id="h-plans">Empieza gratis. Crece cuando quieras.</h2><p class="lead">Precios en pesos mexicanos, con IVA incluido. Sin plazo forzoso.</p></div>'
             '%s<div class="plans" id="plans" data-on="gratis">%s</div>'
             '<p class="fine2">Empiezas gratis y subes de plan desde tu panel cuando quieras. El dominio propio se compra aparte con tu proveedor. '
             '<a href="/planes">Ver los planes en su propia página</a>.</p></div></section>') % (_plan_switch(), _plan_cards(reg))
    faq = _fill(_FAQ_SEC, faq=''.join(
        '<details><summary>%s<i><svg><use href="#i-plus"/></svg></i></summary><p>%s</p></details>' % (e(q), e(a)) for q, a in faq_items()))
    main = '<main id="main">%s%s%s%s%s%s</main>' % (_HERO, _PILLARS, _STEPS, plans, faq, _FINAL)
    main = _fill(main, base=e(db.BASE_DOMAIN), reg=e(reg), pillmark=mark_svg('fu-pill'))
    return (_head('Ficha Única · Tu sitio inmobiliario gratis', desc, '<script type="application/ld+json">%s</script>' % ld)
            + _top(reg, home=True) + main + _foot(reg, local, home=True) + _script(_JS_LIVE, _JS_PLANS) + '</body></html>')


def public_plans(ref=''):
    reg = _reg(ref)
    local = db.ENV != 'production'
    main = ('<main id="main"><section class="page" aria-labelledby="h1"><div class="w"><div class="sec-h"><span class="eyebrow">Planes</span>'
            '<h1 id="h1">Empieza gratis. Crece cuando quieras.</h1>'
            '<p class="lead">Precios en pesos mexicanos, con IVA incluido. Sin plazo forzoso: cambias o cancelas cuando quieras.</p></div>'
            '%s<div class="plans" id="plans" data-on="gratis">%s</div>'
            '<p class="fine2">Tu propio dominio llega muy pronto; se compra aparte con tu proveedor.</p>'
            '<div class="cta-row"><a class="btn" href="%s">Crear mi sitio gratis</a><a class="btn alt" href="/">Volver al inicio</a></div>'
            '</div></section></main>') % (_plan_switch(), _plan_cards(reg), e(reg))
    return (_head('Planes · Ficha Única', 'Gratis con %s, Pro $499 MXN y Pro + IA $999 MXN al mes. Sin plazo forzoso.' % props(db.plan_limits()['gratis']))
            + _top(reg) + main + _foot(reg, local) + _script(_JS_PLANS) + '</body></html>')
