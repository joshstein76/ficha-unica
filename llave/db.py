"""SQLite access + the canonical listing contract every module (site, feeds, GHL) reads from."""
import datetime
import json
import os
import re
import sqlite3
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('LLAVE_DB', os.path.join(ROOT, 'data', 'llave.db'))
MEDIA_DIR = os.environ.get('LLAVE_MEDIA', os.path.join(ROOT, 'data', 'media'))
BASE_DOMAIN = os.environ.get('LLAVE_BASE_DOMAIN', 'fichaunica.localhost')  # prod: the public brand domain
MARKETING_URL = os.environ.get('LLAVE_MARKETING_URL', '').rstrip('/')  # WordPress marketing site; set => logged-out app '/' redirects there
PORT = int(os.environ.get('LLAVE_PORT', '8640'))
ENV = os.environ.get('LLAVE_ENV', 'local')               # local | production
# Public URLs: behind the reverse proxy in production they are https on 443 (no port in links).
SCHEME = os.environ.get('LLAVE_PUBLIC_SCHEME', 'https' if ENV == 'production' else 'http')
PUBLIC_PORT = os.environ.get('LLAVE_PUBLIC_PORT')         # None = same as PORT locally, none in production


# Test tunnels only (never in production): {"app": "https://x.trycloudflare.com", "<slug>": "https://y..."} overrides the links we generate.
TEST_ORIGINS = {}
if ENV != 'production':
    try:
        TEST_ORIGINS = json.loads(os.environ.get('LLAVE_TEST_ORIGINS') or '{}')
    except ValueError:
        TEST_ORIGINS = {}


def origin(host_prefix=''):
    """'https://app.fichaunica.mx' style origin for app./<slug>./'' (bare brand domain)."""
    if TEST_ORIGINS.get(host_prefix or ''):
        return TEST_ORIGINS[host_prefix or '']
    host = ('%s.%s' % (host_prefix, BASE_DOMAIN)) if host_prefix else BASE_DOMAIN
    pp = int(PUBLIC_PORT) if PUBLIC_PORT else (None if ENV == 'production' else PORT)
    port = '' if pp in (None, 80, 443) else ':%d' % pp
    return '%s://%s%s' % (SCHEME, host, port)

PLAN_LIMITS = {'gratis': 1, 'pro': 5, 'ia': 25}  # Josh 10-19: Gratis 1 · Pro MXN 499 = 5 · Pro + IA MXN 999 = 25
LEGACY_PLANS = {'agencia': 'ia', 'pro_crm': 'ia'}  # retired 10-19 (Agencia dropped; Pro + CRM became Pro + IA)
# What each plan unlocks (Claude's split of Josh's 10-19 plans, logged in docs/DECISIONS.md).
PLAN_FEATURES = {
    'domain': ('pro', 'ia'),  # own domain
    'tools': ('pro', 'ia'),   # Instagram images, printable sheet, Excel/CSV import, Bolsa 50/50, full stats
    'ai': ('ia',),            # AI writer, photo review + order, suggested price, weekly social kit
    'team': (),               # team invites: off until teams come back (Josh 10-19: drop Agencia)
}
PUBLIC_STATUSES = ('activa', 'apartada')  # shown on sites + fed to portals
REFERRAL_BONUS_LISTINGS = 1  # extra listing per invited colleague who publishes (Claude's call; was 5 until the 10-19 plans, when 5 = the whole Pro plan)

BRAND = 'Ficha Única'                 # public name (Josh 10-17); LLAVE = internal code name
OWNER = 'Ciao Bella Marketing'        # legal owner of the platform (Josh 10-17)


def connect(path=None):
    con = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def init(con):
    with open(os.path.join(ROOT, 'llave', 'schema.sql'), encoding='utf-8') as f:
        con.executescript(f.read())
    # light migrations for databases created before a column existed
    cols = {r[1] for r in con.execute('PRAGMA table_info(agencies)')}
    for col in ('first_reply', 'first_reply_noname'):
        if col not in cols:
            con.execute('ALTER TABLE agencies ADD COLUMN %s TEXT' % col)
    if 'referred_by' not in cols:  # agent referral loop
        con.execute('ALTER TABLE agencies ADD COLUMN referred_by INTEGER REFERENCES agencies(id)')
    ucols = {r[1] for r in con.execute('PRAGMA table_info(users)')}
    if 'novedades_seen' not in ucols:  # last Novedades date this user opened (YYYY-MM-DD)
        con.execute('ALTER TABLE users ADD COLUMN novedades_seen TEXT')
    for col in ('slug', 'bio', 'zones'):  # agent public profile
        if col not in ucols:
            con.execute('ALTER TABLE users ADD COLUMN %s TEXT' % col)
    for col in ('stripe_customer_id', 'stripe_subscription_id'):  # Stripe billing (llave/billing.py)
        if col not in cols:
            con.execute('ALTER TABLE agencies ADD COLUMN %s TEXT' % col)
    if 'plan_until' not in cols:  # pilot: plan given free until this date (tools/set_plan.py)
        con.execute('ALTER TABLE agencies ADD COLUMN plan_until TEXT')
    con.execute("CREATE TABLE IF NOT EXISTS stripe_events ("  # one row per Stripe event id we processed: replays are no-ops
                "event_id TEXT PRIMARY KEY, type TEXT NOT NULL, outcome TEXT, received_at TEXT NOT NULL DEFAULT (datetime('now')))")
    con.execute("UPDATE agencies SET plan='ia' WHERE plan IN ('agencia','pro_crm')")  # 10-19 plans
    con.commit()


def slugify(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:80] or 'propiedad'


def site_url(agency):
    """Public base URL of an agency site (custom domain once verified, else the free address)."""
    a = dict(agency)
    if a.get('custom_domain') and a.get('domain_verified_at'):
        return 'https://' + a['custom_domain']
    return origin(a['slug'])


def listing_url(agency, listing):
    return '%s/propiedad/%s' % (site_url(agency), dict(listing)['slug'])


def photo_urls(agency, photo_row, size='1600'):
    sizes = json.loads(photo_row['sizes'])
    rel = sizes.get(size) or sizes.get('1600')
    return '%s/media/%s' % (site_url(agency), rel)


def photo_set(agency, photo_row):
    """jpg + webp URLs for 400/800/1600 (webp falls back to the jpg for photos stored before webp existed)."""
    sizes = json.loads(photo_row['sizes'])
    base = site_url(agency)
    out = {}
    for s in ('400', '800', '1600'):
        jpg = sizes.get(s) or sizes.get('1600')
        out['jpg_' + s] = '%s/media/%s' % (base, jpg)
        out['webp_' + s] = '%s/media/%s' % (base, sizes.get(s + 'w') or jpg)
    return out


def canonical(con, listing_id):
    """THE contract. A plain dict describing one listing, used by the site, every feed adapter and GHL.
    Keys (stable): id, ref, slug, url, status, operation, property_type, title, description,
    price (int pesos/dollars or None), price_cents, currency, price_date, maintenance (int or None),
    m2_built, m2_land, bedrooms, bathrooms, parking, floor, year_built, furnished, pets, amenities[list],
    address{street, ext_number, colonia, municipio, estado, cp, country:'MX', lat, lng, show_exact},
    photos[list of {url, url_800, url_400, width, height, alt}], agency{id, slug, name, whatsapp, email, site_url},
    agent{name, whatsapp, email} or None, share_in_bolsa, share_split_pct, rentapoliza_offer, updated_at.
    Never includes internal_note or commission_pct."""
    l = con.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
    if not l:
        return None
    a = con.execute('SELECT * FROM agencies WHERE id=?', (l['agency_id'],)).fetchone()
    u = con.execute('SELECT * FROM users WHERE id=?', (l['agent_id'],)).fetchone() if l['agent_id'] else None
    ph = con.execute('SELECT * FROM photos WHERE listing_id=? ORDER BY position, id', (listing_id,)).fetchall()
    cents = l['price_cents']
    return {
        'id': l['id'], 'ref': l['ref'], 'slug': l['slug'], 'url': listing_url(a, l),
        'status': l['status'], 'operation': l['operation'], 'property_type': l['property_type'],
        'title': l['title'], 'description': l['description'] or '',
        'price': (cents // 100) if cents is not None else None, 'price_cents': cents,
        'currency': l['currency'], 'price_date': l['price_date'],
        'maintenance': (l['maintenance_cents'] // 100) if l['maintenance_cents'] is not None else None,
        'm2_built': l['m2_built'], 'm2_land': l['m2_land'], 'bedrooms': l['bedrooms'],
        'bathrooms': l['bathrooms'], 'parking': l['parking'], 'floor': l['floor'], 'year_built': l['year_built'],
        'furnished': bool(l['furnished']), 'pets': bool(l['pets']), 'amenities': json.loads(l['amenities'] or '[]'),
        'address': {'street': l['street'], 'ext_number': l['ext_number'], 'colonia': l['colonia'],
                    'municipio': l['municipio'], 'estado': l['estado'], 'cp': l['cp'], 'country': 'MX',
                    'lat': l['lat'], 'lng': l['lng'], 'show_exact': bool(l['show_exact_location'])},
        'photos': [{'url': photo_urls(a, p, '1600'), 'url_800': photo_urls(a, p, '800'),
                    'url_400': photo_urls(a, p, '400'),
                    'webp_400': photo_set(a, p)['webp_400'], 'webp_800': photo_set(a, p)['webp_800'],
                    'webp_1600': photo_set(a, p)['webp_1600'], 'width': p['width'], 'height': p['height'],
                    'alt': p['alt'] or l['title']} for p in ph],
        'agency': {'id': a['id'], 'slug': a['slug'], 'name': a['name'], 'whatsapp': a['whatsapp'],
                   'email': a['email'], 'site_url': site_url(a)},
        'agent': ({'name': u['name'], 'whatsapp': u['whatsapp'] or a['whatsapp'], 'email': u['email'],
                   'slug': u['slug'] if 'slug' in u.keys() else None,
                   'photo': u['photo_path'], 'id': u['id']} if u else None),
        'share_in_bolsa': bool(l['share_in_bolsa']), 'share_split_pct': l['share_split_pct'],
        'rentapoliza_offer': bool(l['rentapoliza_offer']), 'updated_at': l['updated_at'],
    }


def public_listing_ids(con, agency_id, include_shared=True):
    """Listings an agency site shows: its own public ones + active Bolsa shares."""
    q = "SELECT id FROM listings WHERE agency_id=? AND status IN ('activa','apartada') ORDER BY updated_at DESC"
    ids = [r['id'] for r in con.execute(q, (agency_id,))]
    if include_shared:
        q2 = ("SELECT l.id FROM shares s JOIN listings l ON l.id=s.listing_id WHERE s.sharing_agency_id=? "
              "AND s.status='activa' AND l.share_in_bolsa=1 AND l.status IN ('activa','apartada')")
        ids += [r['id'] for r in con.execute(q2, (agency_id,)) if r['id'] not in ids]
    return ids


def audit(con, actor, action, detail=''):
    con.execute('INSERT INTO audit(actor, action, detail) VALUES (?,?,?)', (actor, action, detail))


def qualified_referrals(con, agency_id):
    """Agencies this one invited that already have at least one public listing."""
    return con.execute("SELECT COUNT(DISTINCT a.id) FROM agencies a JOIN listings l ON l.agency_id=a.id "
                       "WHERE a.referred_by=? AND l.status IN ('activa','apartada')", (agency_id,)).fetchone()[0]


def plan_of(agency, plan=None):
    p = plan or dict(agency).get('plan') or 'gratis'
    return LEGACY_PLANS.get(p, p)


def plan_has(agency, feature):
    return plan_of(agency) in PLAN_FEATURES.get(feature, ())


def plan_days_left(agency, today=None):
    """Days until a free pilot plan ends (None = no end date). 0 = ends today, negative = already ended."""
    until = dict(agency).get('plan_until')
    if not until:
        return None
    today = today or datetime.date.today()
    return (datetime.date.fromisoformat(until[:10]) - today).days


def listing_limit(con, agency, plan=None):
    """Plan limit + referral bonus."""
    a = dict(agency)
    base = PLAN_LIMITS.get(plan_of(a, plan), PLAN_LIMITS['gratis'])
    extra = 0
    try:
        from . import eco
        extra = eco.extra_listing_slots(con, a['id'])
    except Exception:
        extra = 0
    return base + REFERRAL_BONUS_LISTINGS * qualified_referrals(con, a['id']) + extra
