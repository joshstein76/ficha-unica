"""Live GoHighLevel sync into ONE platform sub-account ("Ficha Única"): agents are our customers, site leads are copied too.
Only contacts, opportunities, notes, custom fields and tags. NEVER messaging: ghl.agent_alert / ghl.lead_first_reply stay dry-run.
Env (app.env only, never logged or stored): LLAVE_GHL_LIVE=1, FU_GHL_TOKEN, FU_GHL_LOCATION_ID.
Flow: enqueue() writes a 'pending' outbox row; tools/ghl_sync_run.py calls drain() every minute."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import db, ghl

BASE = 'https://services.leadconnectorhq.com'
TIMEOUT = 20
MAX_ATTEMPTS = 5
AGENT_PIPELINE, LEAD_PIPELINE = 'Agentes', 'Leads de sitios'
# plan_change stage per plan; 'gratis' is not a stage (the agent stays where they were)
PLAN_STAGE = {'pro': 'Pro', 'ia': 'Pro + IA'}
EVENT_STAGE = {'signup': 'Registrado', 'first_publish': 'Primera propiedad publicada'}
STAGE_RANK = {'Registrado': 0, 'Primera propiedad publicada': 1, 'Pro': 2, 'Pro + IA': 3}
PLAN_TAGS = ['fu-plan-gratis', 'fu-plan-pro', 'fu-plan-ia']

_pipelines = {}  # per process: location id -> {pipeline name: {'id':..., 'stages': {stage name: id}}}
_fields = {}  # per process: location id -> {'fu_plan': {'id':..., 'fieldKey':...}}


class GhlError(Exception):
    pass


def enabled():
    return (os.environ.get('LLAVE_GHL_LIVE') == '1' and bool(os.environ.get('FU_GHL_TOKEN'))
            and bool(os.environ.get('FU_GHL_LOCATION_ID')))


def enqueue(con, kind, ref, payload):
    """Queue one sync job. No-op (returns None) unless live sync is switched on."""
    if not enabled():
        return None
    cur = con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES (?,?,?, 'pending')",
                      (kind, ref, json.dumps(payload, ensure_ascii=False)))
    con.commit()
    return cur.lastrowid


def enqueue_agent(con, agency_id, event):
    return enqueue(con, 'fu.agent', 'agency:%d' % agency_id, {'event': event, 'agency_id': agency_id})


def plan_changed(con, agency_id):
    return enqueue_agent(con, agency_id, 'plan_change')


def first_publish(con, agency_id):
    """Once per agency: the first time it has a public listing. The audit row is the guard."""
    if not enabled():
        return None
    mark = 'agency:%d' % agency_id
    if con.execute("SELECT 1 FROM audit WHERE action='ghl_first_publish' AND detail=?", (mark,)).fetchone():
        return None
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    if not con.execute('SELECT 1 FROM listings WHERE agency_id=? AND status IN (%s) LIMIT 1' % ph,
                       (agency_id,) + tuple(db.PUBLIC_STATUSES)).fetchone():
        return None
    db.audit(con, 'ghl', 'ghl_first_publish', mark)
    return enqueue_agent(con, agency_id, 'first_publish')


def sweep_first_publish(con):
    """Catches every path that publishes (wizard, form, importer, bulk): run by the cron before drain()."""
    n = 0
    for r in con.execute('SELECT id FROM agencies ORDER BY id').fetchall():
        n += 1 if first_publish(con, r['id']) else 0
    return n


# ---------------------------------------------------------------- HTTP
def _call(method, path, body=None, query=None):
    tok, url = os.environ.get('FU_GHL_TOKEN', ''), BASE + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers={
        'Authorization': 'Bearer ' + tok, 'Version': '2021-07-28', 'Content-Type': 'application/json',
        'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode('utf-8', 'replace')[:200] if hasattr(ex, 'read') else ''
        raise GhlError('%s %s -> HTTP %s %s' % (method, path, ex.code, detail.replace(tok, '***') if tok else detail))
    except Exception as ex:  # URLError, timeout, reset
        raise GhlError('%s %s -> %s' % (method, path, type(ex).__name__))
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def _pipeline_ids(loc):
    if loc not in _pipelines:
        res = _call('GET', '/opportunities/pipelines', query={'locationId': loc})
        _pipelines[loc] = {p.get('name'): {'id': p.get('id'), 'stages': {s.get('name'): s.get('id') for s in p.get('stages') or []}}
                           for p in res.get('pipelines') or []}
    return _pipelines[loc]


def _field_ids(loc):
    # GHL may store our fieldKey as 'contact.contactfu_plan' (it did on 2026-10-27), so match on the 'fu_' suffix
    if loc not in _fields:
        res = _call('GET', '/locations/%s/customFields' % loc)
        out = {}
        for f in res.get('customFields') or []:
            k = f.get('fieldKey') or ''
            if 'fu_' in k:
                out['fu_' + k.split('fu_', 1)[1]] = f
        _fields[loc] = out
    return _fields[loc]


def _cf(loc, pairs):
    """[(fu_name, value)] -> customFields by id when GHL knows the field, else by our key."""
    have = _field_ids(loc)
    return [{'id': have[k]['id'], 'key': have[k].get('fieldKey'), 'field_value': v} if k in have
            else {'key': 'contact.' + k, 'field_value': v} for k, v in pairs]


def _contact_id(res):
    return ((res or {}).get('contact') or {}).get('id') or (res or {}).get('id')


def _upsert(loc, body):
    body = dict(body, locationId=loc)
    cid = _contact_id(_call('POST', '/contacts/upsert', body))
    if not cid:
        raise GhlError('contacts/upsert returned no contact id')
    return cid


def _put_in_stage(loc, cid, pipeline_name, stage_name, opp_name, only_forward=False):
    """Create the contact's opportunity or move the existing one. Returns 'ok' or 'no pipeline'."""
    pl = _pipeline_ids(loc).get(pipeline_name)
    stage_id = (pl or {}).get('stages', {}).get(stage_name)
    if not pl or not stage_id:
        return 'no pipeline'
    found = _call('GET', '/opportunities/search', query={'location_id': loc, 'contact_id': cid, 'pipeline_id': pl['id']})
    opps = found.get('opportunities') or []
    if pipeline_name == LEAD_PIPELINE:  # one opportunity per lead + listing, not per contact
        opps = [o for o in opps if o.get('name') == opp_name]
    if opps:
        cur = opps[0]
        if cur.get('pipelineStageId') == stage_id:
            return 'ok'
        if only_forward:
            rank = {sid: STAGE_RANK.get(n, -1) for n, sid in pl['stages'].items()}
            if rank.get(cur.get('pipelineStageId'), -1) >= rank.get(stage_id, 0):
                return 'ok'
        _call('PUT', '/opportunities/%s' % cur['id'], {'pipelineStageId': stage_id, 'status': 'open'})
        return 'ok'
    _call('POST', '/opportunities/', {'pipelineId': pl['id'], 'locationId': loc, 'name': opp_name,
                                       'pipelineStageId': stage_id, 'status': 'open', 'contactId': cid})
    return 'ok'


# ---------------------------------------------------------------- jobs
def _send_agent(con, loc, p):
    ag = con.execute('SELECT * FROM agencies WHERE id=?', (p['agency_id'],)).fetchone()
    if not ag:
        return 'skipped (agency gone)'
    u = con.execute('SELECT * FROM users WHERE agency_id=? ORDER BY id LIMIT 1', (ag['id'],)).fetchone()
    parts = ((u['name'] if u else '') or ag['name'] or '').split(None, 1)
    plan = db.plan_of(ag)
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    n = con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=? AND status IN (%s)' % ph,
                    (ag['id'],) + tuple(db.PUBLIC_STATUSES)).fetchone()[0]
    body = {'firstName': parts[0] if parts else '', 'lastName': parts[1] if len(parts) > 1 else '',
            'email': (u['email'] if u else None) or ag['email'] or '', 'phone': ag['whatsapp'] or '',
            'companyName': ag['name'], 'source': 'Ficha Única app', 'tags': ['fu-agente', 'fu-plan-' + plan],
            'customFields': _cf(loc, [('fu_agency_slug', ag['slug']), ('fu_plan', plan),
                                      ('fu_site_url', db.site_url(ag)), ('fu_listings_published', n)])}
    cid = _upsert(loc, body)
    if p['event'] == 'plan_change':
        _call('DELETE', '/contacts/%s/tags' % cid, {'tags': [t for t in PLAN_TAGS if t != 'fu-plan-' + plan]})
    stage = PLAN_STAGE.get(plan) if p['event'] == 'plan_change' else EVENT_STAGE.get(p['event'])
    if not stage:  # back to gratis: the opportunity stays where it was
        return 'sent'
    r = _put_in_stage(loc, cid, AGENT_PIPELINE, stage, '%s · %s' % (ag['name'], ag['slug']), only_forward=p['event'] != 'plan_change')
    return 'sent' if r == 'ok' else 'sent (no pipeline)'


def _send_lead(con, loc, p):
    lead = con.execute('SELECT * FROM leads WHERE id=?', (p['lead_id'],)).fetchone()
    if not lead or lead['status'] == 'descartado' or ghl.is_blocked(lead['name'] or '', lead['email'] or ''):
        return 'skipped'
    ag = con.execute('SELECT * FROM agencies WHERE id=?', (lead['agency_id'],)).fetchone()
    c = db.canonical(con, lead['listing_id']) if lead['listing_id'] else None
    ref, url = (c['ref'], c['url']) if c else ('', '')
    parts = (lead['name'] or '').split(None, 1)
    tags = ['fu-lead', 'fu-agencia-' + ag['slug']]
    if c and c['operation'] in ('venta', 'renta'):
        tags.append('fu-' + c['operation'])
    cid = _upsert(loc, {
        'firstName': parts[0] if parts else '', 'lastName': parts[1] if len(parts) > 1 else '',
        'email': lead['email'] or '', 'phone': lead['phone'] or '', 'source': 'Sitio de ' + ag['name'], 'tags': tags,
        'customFields': _cf(loc, [('fu_listing_ref', ref), ('fu_listing_url', url), ('fu_agent', ag['slug'])])})
    note = 'Lead de %s (%s).' % (ag['name'], lead['source'] or 'sitio')
    if lead['message']:
        note += ' Pidió: "%s".' % lead['message']
    if c:
        note += ' Propiedad: %s, folio %s. Link: %s' % (c['title'], ref, url)
    _call('POST', '/contacts/%s/notes' % cid, {'body': note})
    r = _put_in_stage(loc, cid, LEAD_PIPELINE, 'Nuevo', '%s · %s' % (lead['name'] or 'Sin nombre', ref))
    return 'sent' if r == 'ok' else 'sent (no pipeline)'


SENDERS = {'fu.agent': _send_agent, 'fu.lead': _send_lead}


def drain(con, limit=50):
    """Send pending fu.* rows, oldest first. Errors keep the row pending; the 5th failure marks it 'failed'.
    Returns {'sent': n, 'retry': n, 'failed': n}."""
    out = {'sent': 0, 'retry': 0, 'failed': 0}
    if not enabled():
        return out
    loc = os.environ['FU_GHL_LOCATION_ID']
    rows = con.execute("SELECT * FROM outbox WHERE status='pending' AND kind IN ('fu.agent','fu.lead') ORDER BY id LIMIT ?",
                       (limit,)).fetchall()
    for r in rows:
        try:
            res = SENDERS[r['kind']](con, loc, json.loads(r['payload']))
            con.execute("UPDATE outbox SET status='sent', response=? WHERE id=?", (res, r['id']))
            out['sent'] += 1
        except Exception as ex:
            tries = (r['attempts'] or 0) + 1
            failed = tries >= MAX_ATTEMPTS
            con.execute('UPDATE outbox SET status=?, attempts=?, response=? WHERE id=?',
                        ('failed' if failed else 'pending', tries, str(ex)[:300], r['id']))
            out['failed' if failed else 'retry'] += 1
        con.commit()
    return out
