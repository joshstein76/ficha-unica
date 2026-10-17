"""WhatsApp helpers: phone normalisation (Mexico-first), wa.me links, prefilled listing text."""
import re
from urllib.parse import quote


def norm_phone(raw):
    """-> E.164 string, or '' when it cannot be a phone number."""
    s = str(raw or '').strip()
    if not s:
        return ''
    plus = s.startswith('+') or s.startswith('00')
    d = re.sub(r'\D', '', s)
    if s.startswith('00'):
        d = d[2:]
    if not d:
        return ''
    if plus:
        if d.startswith('521') and len(d) == 13:  # old Mexican mobile prefix
            d = '52' + d[3:]
        return '+' + d if 8 <= len(d) <= 15 else ''
    for pre in ('045', '044'):  # old local-dialing prefixes
        if d.startswith(pre) and len(d) == 13:
            d = d[3:]
    if len(d) == 10:
        return '+52' + d
    if len(d) == 12 and d.startswith('52'):
        return '+' + d
    if len(d) == 13 and d.startswith('521'):
        return '+52' + d[3:]
    return ''


def wa_link(phone, text=''):
    digits = re.sub(r'\D', '', phone or '')
    url = 'https://wa.me/' + digits
    if text:
        url += '?text=' + quote(text, safe='')
    return url


def listing_message(canonical):
    return 'Hola, me interesa %s (folio %s). ¿Sigue disponible?' % (canonical['title'], canonical['ref'])
