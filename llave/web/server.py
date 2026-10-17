"""LLAVE local server. Routes by Host header:
  app.<base>        agent panel      ·  <slug>.<base>  agent site (+ /feeds/<portal>.xml)
  <custom domain>   agent site (verified only)  ·  <base>  landing
Run: python3 -m llave.web.server   (then open http://app.fichaunica.localhost:8640)"""
import cgi
import datetime
import gzip
import hashlib
import json
import mimetypes
import os
import posixpath
import re
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import threading

from .. import auth, cards, db, geo, importer, lead_watch, media, ml_oauth, photo_fetch, photos, price_check, replies, stats, whatsapp
from ..feeds import build_feed, registry
from ..leads import create_lead
from . import panel, site
from .common import csrf_ok, to_cents, to_num

MAX_UPLOAD = 40 * 1024 * 1024
_SCHEMA_OK = False
SESSION_DAYS = 30


class Ctx(dict):
    pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'FichaUnica/0.1'
    protocol_version = 'HTTP/1.1'
    _body_read = False

    # ---------- plumbing ----------
    def log_message(self, fmt, *args):
        sys.stderr.write('[llave] %s %s\n' % (self.address_string(), fmt % args))

    def send(self, body, status=200, ctype='text/html; charset=utf-8', headers=None):
        data = body.encode('utf-8') if isinstance(body, str) else body
        headers = dict(headers or {})
        base_type = ctype.split(';')[0].strip().lower()
        compressible = base_type in ('text/html', 'text/plain', 'text/xml', 'application/xml', 'application/json') \
            or base_type.endswith(('+xml', '+json'))
        if compressible:
            headers['Vary'] = 'Accept-Encoding'
            if len(data) > 1024 and 'gzip' in (self.headers.get('Accept-Encoding') or '').lower():
                data = gzip.compress(data, 6, mtime=0)
                headers['Content-Encoding'] = 'gzip'
        if base_type == 'text/html' and 'Cache-Control' not in headers:
            headers['Cache-Control'] = 'private, no-store' if self.host() == 'app.' + db.BASE_DOMAIN else 'no-cache'
        if self.command == 'POST' and not self._body_read:
            headers['Connection'] = 'close'  # unread request body would corrupt the next keep-alive request
            self.close_connection = True
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def redirect(self, to, headers=None):
        h = {'Location': to}
        h.update(headers or {})
        self.send('', 303, headers=h)

    def host(self):
        return (self.headers.get('Host') or '').split(':')[0].lower()

    def cookie(self, name):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == name:
                return v
        return None

    def form(self):
        self._body_read = True
        ctype = self.headers.get('Content-Type', '')
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_UPLOAD:
            raise ValueError('Archivo demasiado grande (máximo 40 MB por envío).')
        if ctype.startswith('multipart/form-data'):
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                  environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': ctype, 'CONTENT_LENGTH': str(length)})
            out, files = {}, {}
            for k in fs.keys():
                items = fs[k] if isinstance(fs[k], list) else [fs[k]]
                for it in items:
                    if it.filename:
                        files.setdefault(k, []).append(it.file.read())
                    else:
                        out[k] = it.value
            return out, files
        raw = self.rfile.read(length).decode('utf-8', 'replace')
        return {k: v[-1] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}, {}

    def media(self, rel):
        rel = posixpath.normpath(urllib.parse.unquote(rel)).lstrip('/')
        if rel.startswith('..') or '\\' in rel:
            return self.send('No encontrado', 404, 'text/plain; charset=utf-8')
        path = os.path.join(db.MEDIA_DIR, rel)
        if not os.path.isfile(path):
            return self.send('No encontrado', 404, 'text/plain; charset=utf-8')
        etag = '"%s"' % hashlib.sha1(rel.encode('utf-8')).hexdigest()
        cache = 'public, max-age=31536000, immutable'
        inm = [x.strip() for x in (self.headers.get('If-None-Match') or '').split(',')]
        if etag in inm or '*' in inm:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.send_header('Cache-Control', cache)
        self.send_header('ETag', etag)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if self.command != 'HEAD':
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    # ---------- dispatch ----------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def route(self, method):
        self._body_read = False
        con = db.connect()
        global _SCHEMA_OK
        if not _SCHEMA_OK:
            lead_watch.ensure_columns(con)  # adds leads.first_response_at / reminded_at + listing_views
            con.commit()
            _SCHEMA_OK = True
        try:
            u = urllib.parse.urlsplit(self.path)
            path, query = u.path, {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
            if path.startswith('/media/'):
                return self.media(path[len('/media/'):])
            h = self.host()
            base = db.BASE_DOMAIN
            if h == 'app.' + base:
                return self.panel(con, method, path, query)
            if h.endswith('.' + base):
                a = con.execute('SELECT * FROM agencies WHERE slug=?', (h[:-len(base) - 1],)).fetchone()
            else:
                a = con.execute('SELECT * FROM agencies WHERE custom_domain=? AND domain_verified_at IS NOT NULL', (h,)).fetchone()
            if a:
                return self.agency_site(con, a, method, path)
            if h in (base, 'localhost', '127.0.0.1'):
                return self.send(panel.landing((query.get('ref') or '')[:60]))
            return self.send('Sitio no encontrado', 404, 'text/plain; charset=utf-8')
        except Exception:
            traceback.print_exc()
            self.send('<h1>Algo salió mal</h1><p>Intenta de nuevo en un momento.</p>', 500)
        finally:
            con.close()

    # ---------- agent site ----------
    def agency_site(self, con, a, method, path):
        if method == 'POST' and path == '/contacto':
            f, _ = self.form()
            if f.get('website'):  # honeypot: bots fill every field; pretend success, store nothing
                return self.redirect('/gracias')
            lid = int(f.get('listing') or 0) or None
            if lid and lid not in db.public_listing_ids(con, a['id']):
                lid = None
            try:
                r = create_lead(con, a['id'], lid, f.get('name', ''), f.get('phone', ''), f.get('email', ''),
                                f.get('message', ''), 'sitio', f.get('consent') == '1')
            except ValueError as ex:
                c = db.canonical(con, lid) if lid else None
                return self.send(site.listing(con, a, c, error=str(ex)) if c else site.not_found(a), 400)
            return self.redirect('/gracias?l=%s' % (lid or ''))
        if path == '/':
            return self.send(site.home(con, a))
        if path == '/gracias':
            msg = 'Hola, acabo de dejar mis datos en su sitio.'
            return self.send(site.thanks(a, whatsapp.wa_link(a['whatsapp'], msg) if a['whatsapp'] else ''))
        if path == '/aviso-de-privacidad':
            return self.send(site.privacy(a))
        if path == '/sitemap.xml':
            return self.send(site.sitemap(con, a), ctype='application/xml; charset=utf-8')
        if path == '/robots.txt':
            return self.send(site.robots(a), ctype='text/plain; charset=utf-8')
        m = re.match(r'^/asesor/([a-z0-9-]+)/?$', path)
        if m:
            u = con.execute('SELECT * FROM users WHERE agency_id=? AND slug=?', (a['id'], m.group(1))).fetchone()
            return self.send(site.agent_profile(con, a, u)) if u else self.send(site.not_found(a), 404)
        if path == '/llms.txt':
            return self.send(site.llms(con, a), ctype='text/plain; charset=utf-8')
        m = re.match(r'^/feeds/([a-z0-9_]+)\.(xml|json)$', path)
        if m:
            key = m.group(1) + ('_json' if m.group(2) == 'json' else '')
            try:
                ctype, body = build_feed(con, a['id'], key)
            except ValueError:
                return self.send('Feed no disponible', 404, 'text/plain; charset=utf-8')
            con.commit()
            return self.send(body, ctype=ctype)
        m = re.match(r'^/propiedad/([a-z0-9-]+)/tarjeta-(post|historia)\.jpg$', path)
        if m:
            row = con.execute("SELECT id FROM listings WHERE agency_id=? AND slug=? AND status IN ('activa','apartada')",
                              (a['id'], m.group(1))).fetchone()
            if not row:
                return self.send('No encontrada', 404, 'text/plain; charset=utf-8')
            rel = cards.render_cached(con, row['id'], 'post' if m.group(2) == 'post' else 'story')
            return self.media(rel)
        m = re.match(r'^/propiedad/([a-z0-9-]+)(/ficha)?/?$', path)
        if m:
            for lid in db.public_listing_ids(con, a['id']):
                c = db.canonical(con, lid)
                if c['slug'] == m.group(1):
                    if not m.group(2) and method == 'GET' and not stats.is_bot(self.headers.get('User-Agent')):
                        stats.record_view(con, lid)
                        con.commit()
                    return self.send(site.ficha(a, c) if m.group(2) else site.listing(con, a, c))
            return self.send(site.not_found(a), 404)
        return self.send(site.not_found(a), 404)

    # ---------- panel ----------
    def session(self, con):
        tok = self.cookie('llave_s')
        if not tok:
            return None
        row = con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? "
                          "AND s.expires_at > datetime('now')", (tok,)).fetchone()
        if not row:
            return None
        a = con.execute('SELECT * FROM agencies WHERE id=?', (row['agency_id'],)).fetchone()
        return Ctx(user=row, agency=a, token=tok)

    def start_session(self, con, user_id, to='/'):
        tok = auth.new_session_token()
        exp = (datetime.datetime.utcnow() + datetime.timedelta(days=SESSION_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        con.execute('INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)', (tok, user_id, exp))
        con.commit()
        self.redirect(to, {'Set-Cookie': 'llave_s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d' % (tok, SESSION_DAYS * 86400)})

    def panel(self, con, method, path, query):
        ctx = self.session(con)
        if path == '/registro':
            if method == 'POST':
                f, _ = self.form()
                try:
                    uid = signup(con, f)
                except ValueError as ex:
                    return self.send(panel.signup(str(ex), f), 400)
                return self.start_session(con, uid, '/nueva?bienvenida=1')
            return self.send(panel.signup(ref=(query.get('ref') or '')[:60]))
        if path == '/entrar':
            if method == 'POST':
                f, _ = self.form()
                u = con.execute('SELECT * FROM users WHERE email=?', ((f.get('email') or '').strip().lower(),)).fetchone()
                if not u or not auth.verify_password(f.get('password', ''), u['password_hash']):
                    return self.send(panel.login('Correo o contraseña incorrectos.'), 401)
                return self.start_session(con, u['id'])
            return self.send(panel.login())
        if path in ('/terminos', '/privacidad'):
            return self.send(panel.legal(path[1:]))
        if not ctx:
            return self.redirect('/entrar') if path != '/' else self.send(panel.landing())
        f, files = ({}, {})
        if method == 'POST':
            try:
                f, files = self.form()
            except ValueError as ex:
                return self.send(panel.layout('Error', panel.notice(str(ex), 'err'), ctx), 413)
            if not csrf_ok(ctx['token'], f.get('csrf')):
                return self.send(panel.layout('Error', panel.notice('La sesión expiró. Recarga la página.', 'err'), ctx), 403)
        a, uid = ctx['agency'], ctx['user']['id']
        actor = 'user:%d' % uid

        if path == '/salir' and method == 'POST':
            con.execute('DELETE FROM sessions WHERE token=?', (ctx['token'],))
            con.commit()
            return self.redirect('/entrar', {'Set-Cookie': 'llave_s=; Path=/; Max-Age=0'})
        if path == '/':
            return self.send(panel.dashboard(con, ctx, welcome=query.get('bienvenida') == '1'))
        if path == '/propiedades':
            return self.send(panel.listings(con, ctx))
        if path == '/nueva':
            if method != 'POST':
                if over_limit(con, a):
                    return self.send(panel.listings(con, ctx, panel.notice('Llegaste al límite de tu plan. Marca alguna como vendida o cambia de plan.', 'warn')))
                return self.send(panel.wizard_1(ctx, welcome=query.get('bienvenida') == '1'))
            if over_limit(con, a):
                return self.redirect('/propiedades')
            imgs = files.get('fotos', [])
            if not imgs:
                return self.send(panel.wizard_1(ctx, error='Elige al menos una foto.'), 400)
            lid = create_draft(con, a, uid, f.get('operation'), f.get('property_type'))
            ok, bad = 0, []
            for data in imgs:
                try:
                    photos.ingest(con, lid, data)
                    ok += 1
                except ValueError as ex:
                    bad.append(str(ex))
            con.commit()
            if not ok:
                con.execute('DELETE FROM listings WHERE id=?', (lid,))
                con.commit()
                return self.send(panel.wizard_1(ctx, error='Ninguna foto sirvió: %s' % (bad[0] if bad else '')), 400)
            return self.redirect('/nueva/%d/2' % lid)
        m = re.match(r'^/nueva/(\d+)/(2|3|lista)$', path)
        if m:
            l = con.execute('SELECT * FROM listings WHERE id=? AND agency_id=?', (int(m.group(1)), a['id'])).fetchone()
            if not l:
                return self.redirect('/nueva')
            step = m.group(2)
            if step == '2':
                if method == 'POST':
                    try:
                        wizard_save_2(con, l, f)
                    except ValueError as ex:
                        return self.send(panel.wizard_2(con, ctx, l, str(ex)), 400)
                    return self.redirect('/nueva/%d/3' % l['id'])
                return self.send(panel.wizard_2(con, ctx, l))
            if step == '3':
                if method == 'POST':
                    title = (f.get('title') or '').strip()
                    if len(title) < 8:
                        return self.send(panel.wizard_3(ctx, l, 'Escribe un título de al menos 8 letras.'), 400)
                    con.execute("UPDATE listings SET title=?, description=?, status='activa', updated_at=datetime('now') WHERE id=?",
                                (title[:100], (f.get('description') or '').strip()[:8000], l['id']))
                    if f.get('portales') == '1':
                        for p in ('trovit', 'mitula'):
                            con.execute('INSERT OR IGNORE INTO portal_publications(listing_id, portal, enabled) VALUES (?,?,1)', (l['id'], p))
                    db.audit(con, actor, 'wizard_publish', 'listing:%d' % l['id'])
                    con.commit()
                    return self.redirect('/nueva/%d/lista' % l['id'])
                return self.send(panel.wizard_3(ctx, l))
            return self.send(panel.wizard_done(ctx, l))
        if path == '/precios':
            return self.send(panel.prices(con, ctx))
        m = re.match(r'^/precios/(\d+)$', path)
        if m and method == 'POST':
            ok = price_check.confirm(con, int(m.group(1)), a['id'])
            con.commit()
            return self.send(panel.prices(con, ctx, panel.notice('Precio confirmado.' if ok else 'No encontramos esa propiedad.', '' if ok else 'err')))
        if path == '/admin':
            if ctx['user']['role'] != 'admin':
                return self.send(panel.layout('No encontrado', panel.notice('Página no encontrada.', 'err'), ctx), 404)
            return self.send(panel.admin(con, ctx))
        if path == '/invitar':
            return self.send(panel.invite(con, ctx))
        if path == '/servicios':
            return self.send(panel.services(ctx))
        if path == '/academia':
            return self.send(panel.academy(ctx))
        if path == '/propiedades/importar':
            if method != 'POST':
                return self.send(panel.import_page(ctx))
            text = (files.get('archivo') or [b''])[0].decode('utf-8-sig', 'replace') or f.get('csv', '')
            if not text.strip():
                return self.send(panel.import_page(ctx, error='Sube un archivo CSV o pega el contenido.'), 400)
            if len(text) > 2 * 1024 * 1024:
                return self.send(panel.import_page(ctx, error='El archivo es muy grande (máximo 2 MB).'), 400)
            if f.get('step') == 'commit':
                done = importer.commit(con, a['id'], uid, text)
                photo_fetch.ensure_table(con)
                done['photos_queued'] = photo_fetch.enqueue(con, done.get('photo_urls') or {})
                con.commit()
                if done['photos_queued']:
                    start_photo_worker()
                return self.send(panel.import_page(ctx, done=done))
            return self.send(panel.import_page(ctx, importer.preview(con, a['id'], text), text))
        if path == '/propiedades/nueva':
            if method == 'POST':
                try:
                    lid = save_listing(con, a, uid, f)
                except ValueError as ex:
                    return self.send(panel.listing_form(con, ctx, None, str(ex)), 400)
                return self.redirect('/propiedades/%d?ok=creada' % lid)
            n = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
            if n >= db.listing_limit(con, a):
                return self.send(panel.listings(con, ctx, panel.notice(
                    'Llegaste al límite de tu plan (%d propiedades). Marca alguna como vendida o cambia de plan.' % n, 'warn')))
            return self.send(panel.listing_form(con, ctx))
        m = re.match(r'^/propiedades/(\d+)(/.*)?$', path)
        if m:
            l = con.execute('SELECT * FROM listings WHERE id=? AND agency_id=?', (int(m.group(1)), a['id'])).fetchone()
            if not l:
                return self.send(panel.layout('No encontrada', panel.notice('Esa propiedad no existe.', 'err'), ctx), 404)
            sub = m.group(2) or ''
            if sub == '/fotos' and method == 'POST':
                ok, bad = 0, []
                for data in files.get('fotos', []):
                    try:
                        photos.ingest(con, l['id'], data, alt=l['title'])
                        ok += 1
                    except ValueError as ex:
                        bad.append(str(ex))
                touch(con, l['id'])
                db.audit(con, actor, 'photos_upload', 'listing:%d ok=%d bad=%d' % (l['id'], ok, len(bad)))
                con.commit()
                msg = '%d fotos listas.' % ok + ((' %d no se pudieron usar: %s' % (len(bad), bad[0])) if bad else '')
                return self.send(panel.listing_form(con, ctx, l, ok=msg))
            mm = re.match(r'^/fotos/(\d+)/borrar$', sub)
            if mm and method == 'POST':
                p = con.execute('SELECT id FROM photos WHERE id=? AND listing_id=?', (int(mm.group(1)), l['id'])).fetchone()
                if p:
                    photos.delete(con, p['id'])
                    touch(con, l['id'])
                    con.commit()
                return self.redirect('/propiedades/%d' % l['id'])
            if method == 'POST' and not sub:
                try:
                    save_listing(con, a, uid, f, l)
                except ValueError as ex:
                    return self.send(panel.listing_form(con, ctx, l, str(ex)), 400)
                l = con.execute('SELECT * FROM listings WHERE id=?', (l['id'],)).fetchone()
                return self.send(panel.listing_form(con, ctx, l, ok='Guardado. Tu sitio y tus feeds ya tienen el cambio.'))
            ok = 'Propiedad creada. Ahora sube las fotos.' if query.get('ok') == 'creada' else ''
            return self.send(panel.listing_form(con, ctx, l, ok=ok))
        if path == '/clientes':
            return self.send(panel.leads(con, ctx, query.get('estado')))
        m = re.match(r'^/clientes/(\d+)/(whatsapp|estado)$', path)
        if m:
            lid = int(m.group(1))
            if m.group(2) == 'whatsapp':
                ld = con.execute('SELECT * FROM leads WHERE id=? AND agency_id=?', (lid, a['id'])).fetchone()
                if not ld or not ld['phone']:
                    return self.redirect('/clientes')
                lead_watch.mark_responded(con, lid, a['id'])
                con.commit()
                lst = con.execute('SELECT title FROM listings WHERE id=?', (ld['listing_id'],)).fetchone() if ld['listing_id'] else None
                text = replies.render(a, ld['name'], lst['title'] if lst else None, ctx['user']['name'])
                return self.redirect(whatsapp.wa_link(ld['phone'], text))
            if method == 'POST':
                lead_watch.set_status(con, lid, a['id'], f.get('status', ''))
                con.commit()
            return self.redirect('/clientes' + (('?estado=' + query['estado']) if query.get('estado') else ''))
        if path == '/perfil':
            if method == 'POST':
                try:
                    save_profile(con, a, ctx['user'], f, files)
                except ValueError as ex:
                    return self.send(panel.profile(ctx, error=str(ex)), 400)
                ctx['user'] = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                return self.send(panel.profile(ctx, ok='Perfil guardado.'))
            return self.send(panel.profile(ctx))
        if path == '/plan':
            return self.send(panel.plans(con, ctx))
        m = re.match(r'^/plan/(gratis|pro|agencia)$', path)
        if m:
            key = m.group(1)
            if method == 'POST':
                n = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
                if n > db.listing_limit(con, a, key):
                    return self.send(panel.plan_checkout(ctx, key, 'Tienes %d propiedades; este plan permite %d. Marca algunas como vendidas primero.'
                                                          % (n, db.listing_limit(con, a, key))), 400)
                con.execute('UPDATE agencies SET plan=? WHERE id=?', (key, a['id']))
                db.audit(con, actor, 'plan_change_test_mode', '%s -> %s (no payment)' % (a['plan'], key))
                con.commit()
                ctx['agency'] = con.execute('SELECT * FROM agencies WHERE id=?', (a['id'],)).fetchone()
                return self.send(panel.plans(con, ctx, ok='Listo: ahora tienes el plan %s (modo prueba, sin cobro).' % key))
            return self.send(panel.plan_checkout(ctx, key))
        if path == '/estadisticas':
            return self.send(panel.stats_page(ctx, stats.agency_stats(con, a['id'])))
        if path == '/portales':
            return self.send(panel.portals(con, ctx))
        if path == '/portales/mercadolibre/conectar':
            if method == 'POST' and f.get('demo') == '1':
                ml_oauth.connect_demo(con, a['id'])
                con.commit()
                return self.redirect('/portales')
            url = ml_oauth.start(con, a['id'])
            con.commit()
            if url:
                return self.redirect(url)
            return self.send(panel.portals(con, ctx, panel.notice(
                'La conexión con Mercado Libre se activa cuando Ficha Única registre su app. Mientras tanto puedes ver el flujo en modo demo.', 'warn')))
        if path == '/portales/mercadolibre/desconectar' and method == 'POST':
            ml_oauth.disconnect(con, a['id'])
            con.commit()
            return self.redirect('/portales')
        if path == '/oauth/mercadolibre/callback':
            try:
                ml_oauth.finish(con, query.get('state', ''), query.get('code', ''))
                con.commit()
                return self.redirect('/portales')
            except (ValueError, RuntimeError) as ex:
                con.commit()
                return self.send(panel.portals(con, ctx, panel.notice(str(ex), 'err')), 400)
        m = re.match(r'^/portales/(\d+)/([a-z0-9_]+)$', path)
        if m and method == 'POST':
            l = con.execute("SELECT * FROM listings WHERE id=? AND agency_id=?", (int(m.group(1)), a['id'])).fetchone()
            key = m.group(2)
            if not l or key not in registry.PORTALS or registry.PORTALS[key]['status'] not in ('open', 'api'):
                return self.redirect('/portales')
            cur = con.execute('SELECT enabled FROM portal_publications WHERE listing_id=? AND portal=?', (l['id'], key)).fetchone()
            on = 0 if (cur and cur['enabled']) else 1
            con.execute('INSERT INTO portal_publications(listing_id, portal, enabled, status) VALUES (?,?,?,?) '
                        'ON CONFLICT(listing_id, portal) DO UPDATE SET enabled=excluded.enabled, status=excluded.status',
                        (l['id'], key, on, 'pendiente'))
            if on and key == 'mercadolibre':
                ml_oauth.publish(con, l['id'])  # live only with a connected account + LLAVE_ML_LIVE=1; else outbox dry-run
            db.audit(con, actor, 'portal_toggle', '%s listing:%d -> %d' % (key, l['id'], on))
            con.commit()
            return self.redirect('/portales')
        if path == '/bolsa':
            return self.send(panel.bolsa(con, ctx, query))
        m = re.match(r'^/bolsa/(\d+)/(compartir|retirar)$', path)
        if m and method == 'POST':
            l = con.execute("SELECT * FROM listings WHERE id=? AND share_in_bolsa=1 AND agency_id!=?", (int(m.group(1)), a['id'])).fetchone()
            if l:
                if m.group(2) == 'compartir':
                    con.execute("INSERT INTO shares(listing_id, sharing_agency_id, split_pct) VALUES (?,?,?) "
                                "ON CONFLICT(listing_id, sharing_agency_id) DO UPDATE SET status='activa'",
                                (l['id'], a['id'], 100 - int(l['share_split_pct'] or 50)))
                else:
                    con.execute("UPDATE shares SET status='retirada' WHERE listing_id=? AND sharing_agency_id=?", (l['id'], a['id']))
                db.audit(con, actor, 'bolsa_' + m.group(2), 'listing:%d' % l['id'])
                con.commit()
            return self.redirect('/bolsa')
        if path == '/sitio':
            if method == 'POST':
                try:
                    save_site(con, a, f, files)
                except ValueError as ex:
                    return self.send(panel.site_settings(con, ctx, error=str(ex)), 400)
                ctx['agency'] = con.execute('SELECT * FROM agencies WHERE id=?', (a['id'],)).fetchone()
                return self.send(panel.site_settings(con, ctx, ok='Guardado. Tu sitio ya se ve así.'))
            return self.send(panel.site_settings(con, ctx))
        if path == '/sitio/dominio' and method == 'POST':
            d = (f.get('domain') or '').strip().lower().replace('https://', '').replace('http://', '').strip('/')
            if d.startswith('www.'):
                d = d[4:]
            if d and not re.match(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', d):
                return self.send(panel.site_settings(con, ctx, error='Ese dominio no parece válido (ej. micasa.mx).'), 400)
            con.execute('UPDATE agencies SET custom_domain=?, domain_verified_at=NULL WHERE id=?', (d or None, a['id']))
            con.commit()
            return self.redirect('/sitio')
        return self.send(panel.layout('No encontrado', panel.notice('Página no encontrada.', 'err'), ctx), 404)


# ---------- background photo downloads (CSV import) ----------
_worker_lock = threading.Lock()


def start_photo_worker():
    """One worker at a time, own DB connection; downloads queued CSV photo URLs (SSRF-guarded in photo_fetch)."""
    if not _worker_lock.acquire(blocking=False):
        return

    def run():
        c = db.connect()
        try:
            photo_fetch.ensure_table(c)
            while True:
                r = photo_fetch.run_jobs(c, limit=20)
                if not (r.get('lista', 0) + r.get('error', 0)):
                    break
        finally:
            c.close()
            _worker_lock.release()
    threading.Thread(target=run, daemon=True).start()


# ---------- actions (module-level so tests can call them) ----------
RESERVED = {'app', 'www', 'api', 'admin', 'sites', 'mail', 'feeds', 'static', 'llave'}


def unique_slug(con, name):
    base = db.slugify(name)[:40] or 'inmobiliaria'
    if base in RESERVED:
        base += '-mx'
    slug, n = base, 2
    while con.execute('SELECT 1 FROM agencies WHERE slug=?', (slug,)).fetchone():
        slug, n = '%s-%d' % (base, n), n + 1
    return slug


def signup(con, f):
    name, agency = (f.get('name') or '').strip(), (f.get('agency') or '').strip()
    email = (f.get('email') or '').strip().lower()
    wa = whatsapp.norm_phone(f.get('whatsapp'))
    pw = f.get('password') or ''
    if not (name and agency and email):
        raise ValueError('Completa tu nombre, tu inmobiliaria y tu correo.')
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        raise ValueError('El correo no parece válido.')
    if not wa:
        raise ValueError('Revisa tu WhatsApp: 10 dígitos, por ejemplo 55 1234 5678.')
    if len(pw) < 8:
        raise ValueError('La contraseña debe tener al menos 8 caracteres.')
    if f.get('terms') != '1':
        raise ValueError('Acepta los términos para continuar.')
    if con.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
        raise ValueError('Ya existe una cuenta con ese correo. Entra con tu contraseña.')
    slug = unique_slug(con, agency)
    ref = con.execute('SELECT id FROM agencies WHERE slug=?', ((f.get('ref') or '').strip().lower()[:60],)).fetchone()
    cur = con.execute('INSERT INTO agencies(slug, name, whatsapp, email, city, tagline, referred_by) VALUES (?,?,?,?,?,?,?)',
                      (slug, agency, wa, email, 'Ciudad de México', 'Bienes raíces', ref['id'] if ref else None))
    aid = cur.lastrowid
    uid = con.execute('INSERT INTO users(agency_id, name, email, whatsapp, password_hash) VALUES (?,?,?,?,?)',
                      (aid, name, email, wa, auth.hash_password(pw))).lastrowid
    db.audit(con, 'user:%d' % uid, 'signup', 'agency:%d %s' % (aid, slug))
    con.commit()
    return uid


def over_limit(con, a):
    n = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
    return n >= db.listing_limit(con, a)


def create_draft(con, a, uid, op, ptype):
    """Wizard step 1: an empty draft that only has operation + type; the rest comes in steps 2-3."""
    op = op if op in ('venta', 'renta') else 'venta'
    ptype = ptype if ptype in ('departamento', 'casa', 'terreno', 'oficina', 'local', 'bodega') else 'departamento'
    prefix = re.sub(r'[^A-Z]', '', a['slug'].upper())[:4] or 'LLV'
    n = con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=?', (a['id'],)).fetchone()[0] + 1
    ref = '%s-%04d' % (prefix, n)
    while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND ref=?', (a['id'], ref)).fetchone():
        n += 1
        ref = '%s-%04d' % (prefix, n)
    slug = 'borrador-%s' % ref.lower()
    lid = con.execute('INSERT INTO listings(agency_id, agent_id, ref, slug, status, operation, property_type, title, price_date) '
                      "VALUES (?,?,?,?, 'borrador', ?,?,?, date('now'))",
                      (a['id'], uid, ref, slug, op, ptype, panel.DRAFT_TITLE)).lastrowid
    db.audit(con, 'user:%d' % uid, 'wizard_draft', 'listing:%d' % lid)
    return lid


def wizard_save_2(con, l, f):
    for k in ('colonia', 'municipio', 'estado'):
        if not (f.get(k) or '').strip():
            raise ValueError('Falta la colonia, el municipio o el estado.')
    vals = (to_cents(f.get('price')), 'USD' if f.get('currency') == 'USD' else 'MXN', f['colonia'].strip(), f['municipio'].strip(),
            f['estado'].strip(), to_num(f.get('m2_built')), to_num(f.get('bedrooms'), int), to_num(f.get('bathrooms')))
    con.execute("UPDATE listings SET price_cents=?, currency=?, colonia=?, municipio=?, estado=?, m2_built=?, bedrooms=?, bathrooms=?, "
                "price_date=date('now'), updated_at=datetime('now') WHERE id=?", vals + (l['id'],))
    l2 = con.execute('SELECT * FROM listings WHERE id=?', (l['id'],)).fetchone()
    base, k = db.slugify(panel.suggested_title(l2)), 2
    slug = base
    while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND slug=? AND id!=?', (l['agency_id'], slug, l['id'])).fetchone():
        slug, k = '%s-%d' % (base, k), k + 1
    con.execute('UPDATE listings SET slug=? WHERE id=?', (slug, l['id']))
    con.commit()


def touch(con, lid):
    con.execute("UPDATE listings SET updated_at=datetime('now') WHERE id=?", (lid,))


def save_listing(con, a, uid, f, existing=None):
    title = (f.get('title') or '').strip()
    if len(title) < 8:
        raise ValueError('Escribe un título de al menos 8 letras.')
    op = f.get('operation') if f.get('operation') in ('venta', 'renta') else 'venta'
    ptype = f.get('property_type') or 'departamento'
    status = f.get('status') or 'borrador'
    if status not in ('borrador', 'activa', 'apartada', 'pausada', 'vendida', 'rentada'):
        status = 'borrador'
    for k in ('colonia', 'municipio', 'estado'):
        if not (f.get(k) or '').strip():
            raise ValueError('Falta la colonia, el municipio o el estado.')
    split = to_num(f.get('share_split_pct'), int)
    if split is not None and not 0 <= split <= 100:
        raise ValueError('El porcentaje compartido va de 0 a 100.')
    am = json.dumps([x.strip() for x in (f.get('amenities') or '').split(',') if x.strip()][:40], ensure_ascii=False)
    price_date = (f.get('price_date') or '').strip() or datetime.date.today().isoformat()
    vals = dict(
        title=title[:100], description=(f.get('description') or '').strip()[:8000], operation=op, property_type=ptype,
        status=status, price_cents=to_cents(f.get('price')), currency='USD' if f.get('currency') == 'USD' else 'MXN',
        price_date=price_date, maintenance_cents=to_cents(f.get('maintenance')),
        m2_built=to_num(f.get('m2_built')), m2_land=to_num(f.get('m2_land')),
        bedrooms=to_num(f.get('bedrooms'), int), bathrooms=to_num(f.get('bathrooms')), parking=to_num(f.get('parking'), int),
        furnished=int(f.get('furnished') == '1'), pets=int(f.get('pets') == '1'), amenities=am,
        street=(f.get('street') or '').strip(), ext_number=(f.get('ext_number') or '').strip(),
        colonia=f['colonia'].strip(), municipio=f['municipio'].strip(), estado=f['estado'].strip(),
        cp=(f.get('cp') or '').strip(), show_exact_location=int(f.get('show_exact_location') == '1'),
        share_in_bolsa=int(f.get('share_in_bolsa') == '1'), share_split_pct=split if split is not None else 50,
        commission_pct=to_num(f.get('commission_pct')), rentapoliza_offer=int(f.get('rentapoliza_offer') == '1' and op == 'renta'),
        internal_note=(f.get('internal_note') or '').strip()[:2000])
    raw_maps = (f.get('maps') or '').strip()
    if raw_maps:
        pt = geo.parse_maps_link(raw_maps)
        if not pt:
            raise ValueError('No pudimos leer ese enlace del mapa. Copia el enlace largo de Google Maps (con @latitud,longitud) o escribe "19.43, -99.19".')
        vals.update(lat=pt[0], lng=pt[1])
    elif existing is not None and 'maps' in f:
        vals.update(lat=None, lng=None)
    if existing:
        sets = ', '.join('%s=?' % k for k in vals)
        con.execute("UPDATE listings SET %s, updated_at=datetime('now') WHERE id=?" % sets, list(vals.values()) + [existing['id']])
        lid = existing['id']
        db.audit(con, 'user:%d' % uid, 'listing_update', 'listing:%d' % lid)
    else:
        n = con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=?', (a['id'],)).fetchone()[0] + 1
        prefix = re.sub(r'[^A-Z]', '', a['slug'].upper())[:4] or 'LLV'
        ref = '%s-%04d' % (prefix, n)
        while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND ref=?', (a['id'], ref)).fetchone():
            n += 1
            ref = '%s-%04d' % (prefix, n)
        slug, k = db.slugify(title), 2
        base = slug
        while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND slug=?', (a['id'], slug)).fetchone():
            slug, k = '%s-%d' % (base, k), k + 1
        vals.update(agency_id=a['id'], agent_id=uid, ref=ref, slug=slug)
        cols = ', '.join(vals)
        lid = con.execute('INSERT INTO listings(%s) VALUES (%s)' % (cols, ','.join('?' * len(vals))), list(vals.values())).lastrowid
        db.audit(con, 'user:%d' % uid, 'listing_create', 'listing:%d' % lid)
    con.commit()
    return lid


def save_profile(con, a, u, f, files):
    name = (f.get('name') or '').strip()
    if len(name) < 3:
        raise ValueError('Escribe tu nombre.')
    wa = whatsapp.norm_phone(f.get('whatsapp')) if (f.get('whatsapp') or '').strip() else None
    if (f.get('whatsapp') or '').strip() and not wa:
        raise ValueError('Revisa tu WhatsApp: 10 dígitos.')
    photo = u['photo_path']
    if files.get('photo'):
        photo = media.save_brand_image(files['photo'][0], 'avatar')
    slug = None
    if f.get('public') == '1':
        slug = u['slug'] or db.slugify(name)[:40]
        base, k = slug, 2
        while con.execute('SELECT 1 FROM users WHERE agency_id=? AND slug=? AND id!=?', (a['id'], slug, u['id'])).fetchone():
            slug, k = '%s-%d' % (base, k), k + 1
    con.execute('UPDATE users SET name=?, whatsapp=?, zones=?, bio=?, photo_path=?, slug=? WHERE id=?',
                (name[:80], wa, (f.get('zones') or '').strip()[:200], (f.get('bio') or '').strip()[:600], photo, slug, u['id']))
    db.audit(con, 'user:%d' % u['id'], 'profile_update', 'public' if slug else 'hidden')
    con.commit()


def save_site(con, a, f, files):
    name = (f.get('name') or '').strip()
    if not name:
        raise ValueError('El nombre no puede ir vacío.')
    wa = whatsapp.norm_phone(f.get('whatsapp'))
    if not wa:
        raise ValueError('Revisa el WhatsApp.')
    design = f.get('design') if f.get('design') in ('residencia', 'ciudad', 'costa') else a['design']
    accent = f.get('accent') if re.match(r'^#[0-9a-fA-F]{6}$', f.get('accent') or '') else a['accent']
    fr, frn = (f.get('first_reply') or '').strip(), (f.get('first_reply_noname') or '').strip()
    err = replies.check(fr) or replies.check(frn, need_name=False)
    if err:
        raise ValueError(err)
    logo = a['logo_path']
    if files.get('logo'):
        logo = media.save_brand_image(files['logo'][0], 'logo')
    con.execute('UPDATE agencies SET first_reply=?, first_reply_noname=? WHERE id=?', (fr or None, frn or None, a['id']))
    con.execute('UPDATE agencies SET name=?, tagline=?, about=?, whatsapp=?, email=?, city=?, design=?, accent=?, logo_path=? WHERE id=?',
                (name[:80], (f.get('tagline') or '').strip()[:90], (f.get('about') or '').strip()[:2000], wa,
                 (f.get('email') or '').strip()[:120], (f.get('city') or '').strip()[:60], design, accent, logo, a['id']))
    db.audit(con, 'agency:%d' % a['id'], 'site_update', design)
    con.commit()


def main():
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    con = db.connect()
    db.init(con)
    con.close()
    srv = ThreadingHTTPServer(('127.0.0.1', db.PORT), Handler)
    print('Ficha Única (LLAVE) local: panel http://app.%s:%d · sitios http://<slug>.%s:%d' % (db.BASE_DOMAIN, db.PORT, db.BASE_DOMAIN, db.PORT))
    srv.serve_forever()


if __name__ == '__main__':
    main()
