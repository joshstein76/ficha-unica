"""The search bar on the agent site home (LLAVE_SITE_ASK=1): form + answer area, its CSS and its plain JS (no libraries).
Class names (idxb-ask-*) are shared with IDX Bloom. Colours come ONLY from the --idxb-ask-* variables, set here from the site's accent.
The example questions are painted in an overlay span (pointer-events:none), never written into the input."""
import json
import os

from .. import whatsapp
from .common import e
from .styles import loteria_on_accent, safe_accent

EXAMPLES = ['2 recámaras en Roma', 'depa en renta hasta 25 mil', 'casa en venta']
EMPTY = 'No encontré nada con esas palabras. Pruebe con otras, o escríbame y le ayudo.'
FAIL = 'Ahora mismo no puedo buscar. Escríbame y le ayudo.'

SEARCH_ICON = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
               'aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>')

CSS = r"""
.idxb-ask{--idxb-ask-gap:12px;max-width:760px;margin:-30px auto 4px;position:relative;z-index:2;padding:0;font-family:var(--idxb-ask-font);color:var(--idxb-ask-ink);box-sizing:border-box}
.idxb-ask *{box-sizing:border-box}
.idxb-ask-bar{display:flex;align-items:center;gap:8px;min-width:0;padding:6px 6px 6px 14px;border:1px solid color-mix(in srgb,var(--idxb-ask-ink) 14%,transparent);border-radius:var(--idxb-ask-rad);background:#fff;box-shadow:0 18px 40px -18px rgba(0,0,0,.45)}
.idxb-ask-bar:focus-within{border-color:var(--idxb-ask-btn);box-shadow:0 0 0 3px color-mix(in srgb,var(--idxb-ask-btn) 25%,transparent)}
.idxb-ask-icon{display:flex;flex:none;opacity:.6}
.idxb-ask-field{position:relative;flex:1;min-width:0;display:block}
.idxb-ask-input{display:block;width:100%;min-width:0;min-height:44px;border:0;outline:0;background:transparent;color:inherit;font:inherit;font-size:16px;padding:0}
.idxb-ask-ex{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);pointer-events:none;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:16px;opacity:.55;transition:opacity .35s}
.idxb-ask-ex.is-off{opacity:0}
.idxb-ask-go{flex:none;min-height:44px;padding:0 18px;border:0;border-radius:calc(var(--idxb-ask-rad) - 3px);background:var(--idxb-ask-btn);color:var(--idxb-ask-btn-fg);font:inherit;font-weight:700;cursor:pointer}
.idxb-ask-go:focus-visible,.idxb-ask-x:focus-visible,.idxb-ask-wa:focus-visible,.idxb-ask-card:focus-visible{outline:3px solid var(--idxb-ask-btn);outline-offset:2px}
.idxb-ask-answer{margin-top:14px}
.idxb-ask-answer[hidden]{display:none}
.idxb-ask-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.idxb-ask-q{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-weight:700}
.idxb-ask-x{flex:none;min-width:44px;min-height:44px;border:0;background:transparent;color:inherit;font-size:22px;line-height:1;cursor:pointer;border-radius:var(--idxb-ask-rad)}
.idxb-ask-h{margin:4px 0 2px;font-size:18px}
.idxb-ask-sum{margin:0 0 10px;opacity:.75;font-size:14px}
.idxb-ask-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,230px),1fr));gap:var(--idxb-ask-gap)}
.idxb-ask-card{display:flex;flex-direction:column;min-width:0;overflow:hidden;border:1.5px solid color-mix(in srgb,var(--idxb-ask-ink) 18%,transparent);border-radius:var(--idxb-ask-rad);color:inherit;text-decoration:none}
.idxb-ask-card img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:color-mix(in srgb,var(--idxb-ask-ink) 8%,transparent)}
.idxb-ask-card span{display:block;padding:0 12px;overflow-wrap:anywhere}
.idxb-ask-card .p{padding-top:10px;font-weight:800;font-size:17px}
.idxb-ask-card .l{font-size:12px;font-weight:700;opacity:.7;text-transform:uppercase;letter-spacing:.04em}
.idxb-ask-card .n{padding-top:2px;padding-bottom:12px;font-size:14px}
.idxb-ask-more,.idxb-ask-msg{margin:10px 0 0;font-size:14px;opacity:.85}
.idxb-ask-wa{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;margin-top:14px;padding:0 20px;border-radius:var(--idxb-ask-rad);background:var(--idxb-ask-btn);color:var(--idxb-ask-btn-fg);font-weight:700;text-decoration:none;max-width:100%}
@media (prefers-reduced-motion:reduce){.idxb-ask-ex{transition:none}}
"""

JS = r"""(function(){
var root=document.currentScript.closest('.idxb-ask');if(!root)return;
var form=root.querySelector('.idxb-ask-bar'),input=root.querySelector('.idxb-ask-input'),ex=root.querySelector('.idxb-ask-ex'),
box=root.querySelector('.idxb-ask-answer'),cfg=JSON.parse(root.getAttribute('data-ask')),n=0,i=0,timer=null,seq=0;
var calm=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function stop(){if(timer){clearInterval(timer);timer=null}}
function paint(){ex.textContent=cfg.examples[i%cfg.examples.length]}
function sync(){ex.classList.toggle('is-off',input.value!=='')}
paint();
if(!calm&&cfg.examples.length>1){timer=setInterval(function(){i++;paint()},3600)}
['pointerdown','keydown','focusin','touchstart'].forEach(function(t){form.addEventListener(t,stop,{passive:true})});
input.addEventListener('input',sync);
function el(tag,cls,text){var x=document.createElement(tag);if(cls)x.className=cls;if(text!=null)x.textContent=text;return x}
function safe(u){return /^https?:\/\//i.test(u||'')?u:'#'}
function card(h){
  var a=el('a','idxb-ask-card');a.href=safe(h.u);
  if(h.img){var im=el('img');im.src=safe(h.img);im.alt='';im.loading='lazy';im.width=400;im.height=300;a.appendChild(im)}
  a.appendChild(el('span','p',h.p));a.appendChild(el('span','l',h.label));a.appendChild(el('span','n',h.n));return a}
function wa(q,list){
  if(!cfg.wa)return null;
  var lines=['Hola, busco: '+q].concat(list.map(function(h){return h.p+' · '+h.label+' · '+h.n+' · '+h.u}));
  var a=el('a','idxb-ask-wa','Escribir por WhatsApp');a.href=cfg.wa+'?text='+encodeURIComponent(lines.join('\n'));
  a.rel='nofollow noopener';a.target='_blank';return a}
function show(q,d){
  box.textContent='';box.hidden=false;
  var head=el('div','idxb-ask-head'),x=el('button','idxb-ask-x','×');x.type='button';x.setAttribute('aria-label','Cerrar resultados');
  head.appendChild(el('span','idxb-ask-q',q));head.appendChild(x);box.appendChild(head);
  x.addEventListener('click',function(){box.hidden=true;box.textContent='';input.focus()});
  var list=d&&d.kind==='homes'?d.listings:[];
  if(!list.length){box.appendChild(el('p','idxb-ask-msg',d?cfg.empty:cfg.fail))}
  else{
    var s=el('section','idxb-ask-homes');s.appendChild(el('h3','idxb-ask-h','Esto encontré'));s.appendChild(el('p','idxb-ask-sum',d.summary));
    var c=el('div','idxb-ask-cards');list.forEach(function(h){c.appendChild(card(h))});s.appendChild(c);
    if(d.total>list.length)s.appendChild(el('p','idxb-ask-more','Hay '+(d.total-list.length)+' más. Escríbame y se las muestro.'));
    box.appendChild(s)}
  var w=wa(q,list);if(w)box.appendChild(w)}
form.addEventListener('submit',function(ev){
  ev.preventDefault();stop();var q=input.value.trim();if(!q){input.focus();return}
  var my=++seq,ph=window.innerWidth<600?1:0;
  fetch('/buscar?q='+encodeURIComponent(q)+'&ph='+ph,{headers:{Accept:'application/json'}})
    .then(function(r){if(!r.ok)throw 0;return r.json()})
    .then(function(d){if(my===seq)show(q,d)},function(){if(my===seq)show(q,null)})});
})();"""


def enabled():
    return os.environ.get('LLAVE_SITE_ASK') == '1'


def bar(agency):
    """The search bar block for the home page, or '' with the switch off (the page then renders exactly as before)."""
    if not enabled():
        return ''
    acc = safe_accent(agency['accent'])
    wa = whatsapp.wa_link(agency['whatsapp']) if agency['whatsapp'] else ''
    cfg = json.dumps({'examples': EXAMPLES, 'wa': wa, 'empty': EMPTY, 'fail': FAIL}, ensure_ascii=False)
    vars_ = ('--idxb-ask-btn:%s;--idxb-ask-btn-fg:%s;--idxb-ask-rad:12px;--idxb-ask-ink:var(--fg,#121417);--idxb-ask-font:var(--body,system-ui,sans-serif)'
             % (acc, loteria_on_accent(acc)))
    return ('<div class="in"><style>.idxb-ask{%s}%s</style>'
            '<div class="idxb-ask" data-ask="%s"><form class="idxb-ask-bar" role="search" action="/buscar" method="get" autocomplete="off">'
            '<span class="idxb-ask-icon">%s</span>'
            '<span class="idxb-ask-field"><input class="idxb-ask-input" name="q" type="search" maxlength="200" aria-label="Buscar propiedades" '
            'enterkeyhint="search" autocapitalize="none"><span class="idxb-ask-ex" aria-hidden="true">%s</span></span>'
            '<button class="idxb-ask-go" type="submit">Buscar</button></form>'
            '<div class="idxb-ask-answer" aria-live="polite" hidden></div><script>%s</script></div></div>') % (
        vars_, CSS, e(cfg), SEARCH_ICON, e(EXAMPLES[0]), JS)
