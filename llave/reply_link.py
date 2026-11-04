"""The "Responder por WhatsApp" button in an agent email (2026-11-03).

The button used to be a plain wa.me link, so a lead the agent answered from the email still looked unanswered and the 5-minute
reminder fired anyway. The panel route (/clientes/<id>/whatsapp) records the reply, but it needs a login and agents open email on
their phones, often logged out. So the email now carries /w/<token> on the app host:

  GET  /w/<token>  a one-tap page. Changes nothing. Mail scanners, link previews and prefetchers only ever GET.
  POST /w/<token>  records the first reply and moves the status (lead_watch.whatsapp_reply, the same code the panel uses),
                   then 303s to the wa.me link with the agency's approved wording.

The token is `lead.agency.user.expiry.signature` (HMAC-SHA256 with the app secret, 128 bits kept): bound to one lead, to the agency
the email went to and to the account holder who got it (so the first reply is signed with that person's first name, exactly as the
old link was), and it expires after 30 days. Nothing is stored. A forged, expired or orphaned token gets one plain page that shows
no name and no phone number. Nothing here messages anyone: the agent's own WhatsApp does that."""
import datetime
import hashlib
import hmac

from . import db
from .web import common

TTL_DAYS = 30
MAX_LEN = 140


def _epoch(now=None):
    n = now or datetime.datetime.utcnow()
    return int((n - datetime.datetime(1970, 1, 1)).total_seconds())


def _sig(payload):
    return hmac.new(common.SECRET.encode(), b'wa|' + payload.encode(), hashlib.sha256).hexdigest()[:32]


def make(lead_id, agency_id, user_id=0, now=None):
    payload = '%d.%d.%d.%d' % (lead_id, agency_id, user_id or 0, _epoch(now) + TTL_DAYS * 86400)
    return payload + '.' + _sig(payload)


def read(token, now=None):
    """-> (lead_id, agency_id, user_id), or None for a missing, forged or expired token."""
    token = str(token or '')
    parts = token.split('.')
    if len(token) > MAX_LEN or len(parts) != 5:
        return None
    try:
        lead_id, agency_id, user_id, exp = (int(p) for p in parts[:4])
    except ValueError:
        return None
    if min(lead_id, agency_id, exp) < 1 or user_id < 0:
        return None
    payload = '%d.%d.%d.%d' % (lead_id, agency_id, user_id, exp)
    if not hmac.compare_digest(_sig(payload).encode(), parts[4].encode('utf-8', 'replace')):  # bytes: a non-ASCII forgery must not raise
        return None
    if exp < _epoch(now):
        return None
    return lead_id, agency_id, user_id


def url(lead_id, agency_id, user_id=0, now=None):
    return '%s/w/%s' % (db.origin('app'), make(lead_id, agency_id, user_id, now))


def resolve(con, token, now=None):
    """-> {'lead', 'agency', 'agent_name', 'listing_title'} for a good token whose lead still exists, still has a phone and still belongs to that agency
    (as the receiving agency or, for a Bolsa lead, as the owner of the property). Anything else -> None."""
    got = read(token, now)
    if not got:
        return None
    lead_id, agency_id, user_id = got
    lead = con.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    agency = con.execute('SELECT * FROM agencies WHERE id=?', (agency_id,)).fetchone()
    if not lead or not agency or not lead['phone'] or agency_id not in (lead['agency_id'], lead['owner_agency_id']):
        return None
    user = con.execute('SELECT name FROM users WHERE id=? AND agency_id=?', (user_id, agency_id)).fetchone() if user_id else None
    lst = con.execute('SELECT title FROM listings WHERE id=?', (lead['listing_id'],)).fetchone() if lead['listing_id'] else None
    return {'lead': lead, 'agency': agency, 'agent_name': (user['name'] if user else '') or '', 'listing_title': lst['title'] if lst else ''}
