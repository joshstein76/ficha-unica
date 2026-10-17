"""Email subjects by type, per josh-command-center/functions/content/EMAIL-SUBJECT-PLAYBOOK.md (Josh 10-17):
- outreach / invite (cold, B2B): "<Our brand> / <Their company>"            e.g. "Ficha Única / Casas Roma"
- lead (first reply, follow-up, nurture): "<first name>, <2–5 words>"       e.g. "Ana, 3 fotos de Roma 12"
- transactional (visit, receipt, password): plain and clear                 e.g. "Su visita: martes 10:30"
Rules: ≤ 40 characters, no emoji, no ALL CAPS, no "urgente/gratis/oferta"; sender name = the brand. No sends happen here."""
import re

from . import db
from .replies import first_name

MAX_LEN = 40
BANNED = ('urgente', 'gratis', 'oferta')


def _clean(s):
    s = re.sub(r'\s+', ' ', (s or '').strip())
    return s if len(s) <= MAX_LEN else s[:MAX_LEN - 1].rstrip(' ,·/-') + '…'


def outreach_subject(our_brand, their_company):
    """Cold / B2B first contact (agent invites, partner outreach)."""
    them = (their_company or '').strip()
    return _clean('%s / %s' % (our_brand.strip(), them) if them else our_brand.strip())


def lead_subject(lead_name, topic):
    """Someone who already wrote to us: first name + 2–5 words (a question if natural). No name → just the topic."""
    words = (topic or '').split()
    if not 2 <= len(words) <= 5:
        raise ValueError('El asunto para clientes lleva 2 a 5 palabras.')
    name = first_name(lead_name)
    return _clean('%s, %s' % (name, ' '.join(words)) if name else ' '.join(words)[:1].upper() + ' '.join(words)[1:])


def transactional_subject(text):
    return _clean(text)


def check(subject):
    """'' if the subject follows the playbook rules, else a Spanish reason."""
    if len(subject) > MAX_LEN:
        return 'Máximo %d caracteres.' % MAX_LEN
    if any(w in subject.lower() for w in BANNED):
        return 'Evita "urgente", "gratis" u "oferta".'
    if re.search(r'[\U0001F300-\U0001FAFF☀-➿]', subject):
        return 'Sin emojis.'
    if re.search(r'\b[A-ZÁÉÍÓÚÑ]{4,}\b', subject):
        return 'Sin MAYÚSCULAS.'
    return ''


def agent_invite(agency_name, body_es):
    """Platform → an agency we're inviting (outreach): slash pattern."""
    return {'subject': outreach_subject(db.BRAND, agency_name), 'from_name': db.BRAND, 'body': body_es}


def to_agent_transactional(agency, text, body_es):
    """Platform → an existing agency (price check, reminders, receipts): plain."""
    return {'subject': transactional_subject(text), 'to': dict(agency).get('email'), 'from_name': db.BRAND, 'body': body_es}


def to_lead(agency, lead_name, lead_email, topic, body_es):
    """Agency → its client (first reply / follow-up when there's no WhatsApp): first name + 2–5 words."""
    return {'subject': lead_subject(lead_name, topic), 'to': lead_email, 'from_name': dict(agency)['name'], 'body': body_es}
