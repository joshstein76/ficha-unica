"""Download listing photos from URLs in an agent's CSV (SSRF-proof), then hand bytes to photos.ingest.

Safety: http/https only, no userinfo, ports 80/443, hostnames only (or plain dotted-quad), every resolved
address must be global, connection is pinned to the validated IP, redirects are followed by hand (max 3)
and re-validated, content-type + magic bytes checked, hard byte cap while streaming.
"""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from llave import db, photos

MAX_PER_LISTING = 20
MAX_BYTES = 15 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = 'FichaUnica-PhotoImport/1.0'
ALLOWED_TYPES = ('image/jpeg', 'image/png', 'image/webp')
_NAT64 = ipaddress.ip_network('64:ff9b::/96')
_NUMERIC_LABEL = re.compile(r'^(0x[0-9a-f]*|[0-9]+)$')


def ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS photo_jobs (
        id INTEGER PRIMARY KEY,
        listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pendiente',
        error TEXT,
        photo_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(listing_id, url))""")
    con.commit()


def enqueue(con, photo_urls_by_listing):
    ensure_table(con)
    queued = 0
    for lid, urls in (photo_urls_by_listing or {}).items():
        seen = set()
        n = 0
        for url in urls or []:
            url = (url or '').strip()
            if not url or url in seen:
                continue
            seen.add(url)
            if con.execute('SELECT 1 FROM photo_jobs WHERE listing_id=? AND url=?', (lid, url)).fetchone():
                continue
            n += 1
            if n > MAX_PER_LISTING:
                con.execute("INSERT INTO photo_jobs(listing_id,url,status,error) VALUES (?,?,'omitida',?)",
                            (lid, url, 'Máximo 20 fotos por propiedad'))
            else:
                con.execute('INSERT INTO photo_jobs(listing_id,url) VALUES (?,?)', (lid, url))
                queued += 1
    con.commit()
    return queued


def _bad_ip(ip):
    if getattr(ip, 'ipv4_mapped', None):
        ip = ip.ipv4_mapped
    if ip.version == 6 and ip in _NAT64:
        return True
    return not ip.is_global or ip.is_multicast


def _check(url, resolver):
    """-> (ok, reason_es, host, port, [ips])"""
    def no(msg):
        return False, msg, None, None, []
    try:
        p = urlsplit((url or '').strip())
        port = p.port
        host = (p.hostname or '').lower().rstrip('.')
    except ValueError:
        return no('La dirección de la foto no es válida')
    if p.scheme not in ('http', 'https'):
        return no('Solo se aceptan direcciones http o https')
    if '@' in p.netloc:
        return no('La dirección no puede incluir usuario ni contraseña')
    if port not in (None, 80, 443):
        return no('Puerto no permitido')
    if not host:
        return no('La dirección de la foto no es válida')
    port = port or (443 if p.scheme == 'https' else 80)
    ips = []
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        labels = host.split('.')
        if all(_NUMERIC_LABEL.match(x) for x in labels) or _NUMERIC_LABEL.match(labels[-1]):
            return no('Dirección numérica no permitida')
        if not re.match(r'^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$', host):
            return no('Nombre de sitio no válido')
        base = (db.BASE_DOMAIN or '').lower()
        if (host == 'localhost' or host.endswith(('.localhost', '.local', '.internal'))
                or (base and (host == base or host.endswith('.' + base)))):
            return no('Sitio no permitido')
    if ips and re.match(r'^\d+$', host):
        return no('Dirección numérica no permitida')
    if not ips:
        try:
            infos = resolver(host, port, 0, socket.SOCK_STREAM)
        except Exception:
            return no('No se pudo encontrar el sitio de la foto')
        for info in infos:
            try:
                ips.append(ipaddress.ip_address(info[4][0].split('%')[0]))
            except ValueError:
                return no('Dirección del sitio no válida')
        if not ips:
            return no('No se pudo encontrar el sitio de la foto')
    for ip in ips:
        if _bad_ip(ip):
            return no('La dirección apunta a una red privada o no permitida')
    return True, '', host, port, ips


def is_safe_url(url, resolver=socket.getaddrinfo):
    ok, reason, _h, _p, _i = _check(url, resolver)
    return ok, reason


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def default_opener(url, ip, headers, timeout):
    """One GET, connected to `ip` (already validated), no redirects. Returns an HTTPResponse-like object."""
    p = urlsplit(url)
    host = p.hostname
    port = p.port or (443 if p.scheme == 'https' else 80)
    cls = _PinnedHTTPS if p.scheme == 'https' else _PinnedHTTP
    conn = cls(host, str(ip), port, timeout)
    path = (p.path or '/') + ('?' + p.query if p.query else '')
    conn.request('GET', path, headers=dict(headers, Host=p.netloc))
    resp = conn.getresponse()
    resp._conn = conn
    return resp


def _magic_ok(data):
    return (data[:3] == b'\xff\xd8\xff' or data[:4] == b'\x89PNG'
            or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'))


def fetch_bytes(url, opener=None, resolver=socket.getaddrinfo, max_bytes=MAX_BYTES, timeout=20):
    opener = opener or default_opener
    headers = {'User-Agent': USER_AGENT, 'Accept': 'image/jpeg,image/png,image/webp'}
    cur = url
    for _hop in range(MAX_REDIRECTS + 1):
        ok, reason, _h, _p, ips = _check(cur, resolver)
        if not ok:
            raise ValueError(reason)
        try:
            resp = opener(cur, ips[0], headers, timeout)
        except ValueError:
            raise
        except Exception:
            raise ValueError('No se pudo descargar la foto')
        try:
            status = resp.status
            if status in (301, 302, 303, 307, 308):
                loc = resp.getheader('Location')
                if not loc:
                    raise ValueError('Redirección inválida')
                cur = urljoin(cur, loc)
                continue
            if status != 200:
                raise ValueError('El sitio respondió con error %s' % status)
            ctype = (resp.getheader('Content-Type') or '').split(';')[0].strip().lower()
            if ctype not in ALLOWED_TYPES:
                raise ValueError('El archivo no es una foto JPG, PNG o WebP')
            clen = resp.getheader('Content-Length')
            if clen and clen.isdigit() and int(clen) > max_bytes:
                raise ValueError('La foto pesa demasiado (máximo 15 MB)')
            buf = bytearray()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > max_bytes:
                    raise ValueError('La foto pesa demasiado (máximo 15 MB)')
            data = bytes(buf)
            if not _magic_ok(data):
                raise ValueError('El archivo no es una foto válida')
            return data
        except ValueError:
            raise
        except Exception:
            raise ValueError('No se pudo descargar la foto')
        finally:
            try:
                resp.close()
                conn = getattr(resp, '_conn', None)
                if conn:
                    conn.close()
            except Exception:
                pass
    raise ValueError('Demasiadas redirecciones')


def run_jobs(con, limit=50, sleep_between=1.0, fetch=fetch_bytes):
    ensure_table(con)
    jobs = con.execute("SELECT * FROM photo_jobs WHERE status='pendiente' ORDER BY id LIMIT ?", (limit,)).fetchall()
    out = {'lista': 0, 'error': 0}
    last_host = {}
    for j in jobs:
        host = (urlsplit(j['url']).hostname or '').lower()
        if sleep_between and host in last_host:
            wait = sleep_between - (time.time() - last_host[host])
            if wait > 0:
                time.sleep(wait)
        elif sleep_between and last_host:
            time.sleep(min(sleep_between, 0.2))
        last_host[host] = time.time()
        row = con.execute('SELECT title FROM listings WHERE id=?', (j['listing_id'],)).fetchone()
        try:
            data = fetch(j['url'])
            pid = photos.ingest(con, j['listing_id'], data, alt=row['title'] if row else None)
            con.execute("UPDATE photo_jobs SET status='lista', photo_id=?, error=NULL WHERE id=?", (pid, j['id']))
            out['lista'] += 1
        except ValueError as e:
            con.execute("UPDATE photo_jobs SET status='error', error=? WHERE id=?", (str(e), j['id']))
            out['error'] += 1
        except Exception:
            con.execute("UPDATE photo_jobs SET status='error', error=? WHERE id=?",
                        ('No se pudo procesar la foto', j['id']))
            out['error'] += 1
        con.commit()
    return out


def summary(con, listing_id):
    ensure_table(con)
    res = {'pendiente': 0, 'lista': 0, 'error': 0, 'omitida': 0}
    for r in con.execute('SELECT status, COUNT(*) n FROM photo_jobs WHERE listing_id=? GROUP BY status', (listing_id,)):
        res[r['status']] = r['n']
    return res
