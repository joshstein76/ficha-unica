"""GoHighLevel plan + DRY-RUN outbox. MVP: no network, no writes, nothing is ever sent to a lead."""
import json
import os
import sys

from . import db, whatsapp

_GUARD = '/Users/joshstein/Desktop/Claude Ledger/josh-command-center/clients/vive-polanco/ops'
FALLBACK_TERMS = ('alara', 'global luxury', 'glicka', 'paulina sierra', 'gabriella orozco', 'sheila')
_blocked = None
try:
    sys.path.insert(0, _GUARD)
    from blocklist_guard import blocked as _blocked  # noqa: E402
except Exception:
    _blocked = None


def is_blocked(name='', email='', company=''):
    parts = (name or '').split(None, 1)
    c = {'firstName': parts[0] if parts else '', 'lastName': parts[1] if len(parts) > 1 else '',
         'name': name or '', 'email': email or '', 'companyName': company or ''}
    if _blocked:
        try:
            if _blocked(c):
                return True
        except Exception:
            pass
    hay = ' '.join([name or '', email or '', company or '']).lower()
    return any(t in hay for t in FALLBACK_TERMS)


def _money(c):
    if not c or c.get('price') is None:
        return 'precio a consultar'
    s = '$%s %s' % (format(c['price'], ','), c['currency'])
    return s + (' (precio al %s)' % c['price_date'] if c.get('price_date') else '')


def plan_for_lead(lead_row, canonical, agency_row, owner_agency_row=None, split_pct=None):
    lead, ag = dict(lead_row), dict(agency_row)
    c = canonical
    loc = ag.get('ghl_location_id') or 'DRY_RUN_NO_LOCATION'
    parts = (lead.get('name') or '').split(None, 1)
    first, last = (parts[0] if parts else ''), (parts[1] if len(parts) > 1 else '')
    ref = c['ref'] if c else ''
    title = c['title'] if c else 'información general'
    url = c['url'] if c else ''
    tags = ['llave', 'llave-' + ag['slug']]
    if c:
        tags += ['op-' + c['operation'], 'colonia-' + db.slugify(c['address'].get('colonia') or '')]
    ops = [{'kind': 'ghl.contact_upsert', 'method': 'POST', 'path': '/contacts/upsert', 'body': {
        'locationId': loc, 'firstName': first, 'lastName': last, 'phone': lead.get('phone') or '',
        'email': lead.get('email') or '', 'source': 'LLAVE ' + (lead.get('source') or 'sitio'), 'tags': tags,
        'customFields': [{'key': 'llave_listing_ref', 'field_value': ref},
                         {'key': 'llave_listing_url', 'field_value': url},
                         {'key': 'llave_lead_source', 'field_value': lead.get('source') or 'sitio'}]}}]
    note = 'Lead de LLAVE (%s). ' % (lead.get('source') or 'sitio')
    if lead.get('message'):
        note += 'Pidió: "%s". ' % lead['message']
    if c:
        note += 'Propiedad: %s, folio %s, %s. Link: %s' % (title, ref, _money(c), url)
    ops.append({'kind': 'ghl.note', 'method': 'POST', 'path': '/contacts/{contactId}/notes',
                'body': {'locationId': loc, 'body': note}})
    ops.append({'kind': 'ghl.opportunity', 'method': 'POST', 'path': '/opportunities/', 'body': {
        'locationId': loc, 'pipeline_name': 'LLAVE Leads', 'stage': 'Nuevo',
        'name': '%s · %s' % (lead.get('name') or 'Sin nombre', ref),
        'monetaryValue': c['price'] if c and c.get('currency') == 'MXN' and c.get('price') is not None else None}})
    wa = whatsapp.wa_link(lead.get('phone') or '') if lead.get('phone') else ''
    who = lead.get('name') or 'Sin nombre'
    text = 'Nuevo cliente: %s pregunta por %s (%s).' % (who, title, ref)
    if wa:
        text += ' WhatsApp: ' + wa
    elif lead.get('email'):
        text += ' Correo: ' + lead['email']
    recipients = [('receiving', ag)]
    if owner_agency_row is not None and dict(owner_agency_row)['id'] != ag['id']:
        recipients.append(('owner', dict(owner_agency_row)))
        s = split_pct if split_pct is not None else 50
        text += ' Bolsa %d/%d.' % (s, 100 - s)
    for role, r in recipients:
        ops.append({'kind': 'ghl.agent_alert', 'method': None, 'path': None, 'channel': 'whatsapp',
                    'audience': 'agency', 'role': role, 'agency_slug': r['slug'],
                    'to_whatsapp': r.get('whatsapp'), 'body': {'text': text}})
    ops.append({'kind': 'ghl.lead_first_reply', 'status': 'needs_template', 'audience': 'lead',
                'todo': 'Primer mensaje al lead: requiere plantilla aprobada por un humano.', 'body': {}})
    return ops


def queue_for_lead(con, lead_id):
    lead = con.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead or lead['status'] == 'descartado' or is_blocked(lead['name'] or '', lead['email'] or ''):
        return []
    ag = con.execute('SELECT * FROM agencies WHERE id=?', (lead['agency_id'],)).fetchone()
    if os.environ.get('LLAVE_GHL_LIVE') == '1' and ag['ghl_location_id']:
        raise NotImplementedError('Live GHL off in MVP')
    owner = split = canon = None
    if lead['listing_id']:
        canon = db.canonical(con, lead['listing_id'])
        if lead['owner_agency_id'] and lead['owner_agency_id'] != lead['agency_id']:
            owner = con.execute('SELECT * FROM agencies WHERE id=?', (lead['owner_agency_id'],)).fetchone()
            sh = con.execute('SELECT split_pct FROM shares WHERE listing_id=? AND sharing_agency_id=?',
                             (lead['listing_id'], lead['agency_id'])).fetchone()
            split = sh['split_pct'] if sh else canon['share_split_pct']
    ops = plan_for_lead(lead, canon, ag, owner, split)
    for op in ops:
        op['mode'] = 'dry_run'
        con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES (?,?,?, 'dry_run')",
                    (op['kind'], 'lead:%d' % lead_id, json.dumps(op, ensure_ascii=False)))
    con.execute("UPDATE leads SET ghl_status='dry_run' WHERE id=?", (lead_id,))
    con.commit()
    return ops
