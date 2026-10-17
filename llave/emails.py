"""Email subjects + templates. Josh's permanent rule (10-17): every subject is exactly "<Our brand> / <Their company or first name>".
Platform -> agent: "Ficha Única / <agency name>". Agency -> lead: "<agency name> / <lead first name>". No sends happen here."""
from . import db
from .replies import first_name


def subject(our_brand, their_company='', their_name=''):
    them = (their_company or '').strip() or first_name(their_name) or ''
    return ('%s / %s' % (our_brand.strip(), them)) if them else our_brand.strip()


def to_agent(agency, body_es):
    """Platform email to an agency (welcome, price check, reminders)."""
    a = dict(agency)
    return {'subject': subject(db.BRAND, a.get('name')), 'to': a.get('email'), 'body': body_es}


def to_lead(agency, lead_name, lead_email, body_es):
    """Agency email to its client (first reply by email when there is no WhatsApp)."""
    return {'subject': subject(dict(agency)['name'], their_name=lead_name), 'to': lead_email, 'body': body_es}
