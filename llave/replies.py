"""First reply to a new lead. Default wording approved by Josh 2026-10-17 (tap "Approve"); every agency starts
with it and can edit it in Mi sitio. Placeholders: {nombre} {propiedad} {asesor} {inmobiliaria}."""
import re

DEFAULT_FIRST_REPLY = ('Hola {nombre}, gracias por escribir sobre {propiedad}. Soy {asesor} de {inmobiliaria}. '
                       '¿Le comparto más fotos y detalles por aquí o prefiere agendar una visita?')
DEFAULT_FIRST_REPLY_NONAME = ('Hola, gracias por escribir sobre {propiedad}. Soy {asesor} de {inmobiliaria}. '
                              '¿Le comparto más fotos y detalles por aquí o prefiere agendar una visita?')
PLACEHOLDERS = ('nombre', 'propiedad', 'asesor', 'inmobiliaria')
GENERIC_ACCOUNT = {'equipo', 'team', 'ventas', 'admin', 'contacto', 'oficina', 'info'}


def first_name(raw):
    """A usable first name, or '' (never a handle, email, number or emoji as {nombre})."""
    w = (raw or '').strip().split()
    if not w:
        return ''
    n = w[0]
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'\-]{2,30}", n):
        return ''
    return n[0].upper() + n[1:].lower() if n.isupper() or n.islower() else n


def check(template, need_name=True):
    """Spanish error string or ''. Only our placeholders allowed; {nombre} only in the named version."""
    t = (template or '').strip()
    if not t:
        return ''
    if len(t) > 500:
        return 'El mensaje es muy largo (máximo 500 caracteres).'
    used = set(re.findall(r'\{([^{}]*)\}', t))
    bad = used - set(PLACEHOLDERS)
    if bad:
        return 'No reconocemos {%s}. Usa solo {nombre}, {propiedad}, {asesor} o {inmobiliaria}.' % sorted(bad)[0]
    if not need_name and 'nombre' in used:
        return 'El mensaje sin nombre no puede usar {nombre}.'
    return ''


def render(agency, lead_name, listing_title, agent_name):
    a = dict(agency)
    name = first_name(lead_name)
    if name:
        tpl = (a.get('first_reply') or '').strip() or DEFAULT_FIRST_REPLY
    else:
        tpl = (a.get('first_reply_noname') or '').strip() or DEFAULT_FIRST_REPLY_NONAME
    asesor = (agent_name or '').split(' ')[0]
    if not asesor or asesor.lower() in GENERIC_ACCOUNT:
        # team logins ("Equipo VIVE") have no person to name: the default line becomes "Somos <inmobiliaria>."
        tpl = tpl.replace('Soy {asesor} de {inmobiliaria}.', 'Somos {inmobiliaria}.')
        asesor = a.get('name', '')
    values = {'nombre': name, 'propiedad': listing_title or 'nuestras propiedades', 'asesor': asesor,
              'inmobiliaria': a.get('name', '')}
    return re.sub(r'\{(%s)\}' % '|'.join(PLACEHOLDERS), lambda m: values[m.group(1)], tpl)
