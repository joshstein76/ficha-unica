"""Lead intake. Nothing here messages anyone: it stores the lead and queues DRY-RUN ghl ops."""
import re

from . import db, ghl, whatsapp
from .ghl import is_blocked


def rentapoliza_offer(canonical):
    if canonical and canonical.get('operation') == 'renta' and canonical.get('rentapoliza_offer'):
        return 'Renta con póliza jurídica RentaPóliza: protección legal para el propietario.'
    return None


def create_lead(con, agency_id, listing_id=None, name='', phone='', email='', message='',
                source='sitio', consent=False):
    name, email, message = (name or '').strip(), (email or '').strip().lower(), (message or '').strip()
    phone_n = whatsapp.norm_phone(phone)
    if not phone_n and not email:
        raise ValueError('Necesitamos un teléfono o un correo para contactarte.')
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        raise ValueError('El correo no parece válido.')
    if phone and not phone_n and not email:
        raise ValueError('El teléfono no parece válido.')
    if source == 'sitio' and not consent:
        raise ValueError('Debes aceptar el aviso de privacidad para enviar tu solicitud.')
    owner_id = agency_id
    if listing_id is not None:
        l = con.execute('SELECT agency_id FROM listings WHERE id=?', (listing_id,)).fetchone()
        if not l:
            raise ValueError('La propiedad no existe.')
        if l['agency_id'] != agency_id:
            owner_id, source = l['agency_id'], 'bolsa'
    wa = whatsapp.wa_link(phone_n) if phone_n else ''
    if is_blocked(name, email):
        cur = con.execute(
            "INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, source, consent,"
            " status, ghl_status) VALUES (?,?,?,?,?,?,?,?,?, 'descartado', 'pendiente')",
            (agency_id, owner_id, listing_id, name, phone_n, email, message, source, int(bool(consent))))
        db.audit(con, 'leads', 'lead_blocked', 'lead:%d' % cur.lastrowid)
        con.commit()
        return {'id': cur.lastrowid, 'duplicate': False, 'blocked': True, 'wa_link_for_agent': ''}
    dup = con.execute(
        "SELECT id FROM leads WHERE agency_id=? AND listing_id IS ? AND created_at >= datetime('now','-10 minutes')"
        " AND ((?<>'' AND phone=?) OR (?<>'' AND email=?)) ORDER BY id LIMIT 1",
        (agency_id, listing_id, phone_n, phone_n, email, email)).fetchone()
    if dup:
        return {'id': dup['id'], 'duplicate': True, 'blocked': False, 'wa_link_for_agent': wa}
    cur = con.execute(
        "INSERT INTO leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, source, consent)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (agency_id, owner_id, listing_id, name, phone_n, email, message, source, int(bool(consent))))
    lead_id = cur.lastrowid
    con.commit()
    ghl.queue_for_lead(con, lead_id)
    return {'id': lead_id, 'duplicate': False, 'blocked': False, 'wa_link_for_agent': wa}
