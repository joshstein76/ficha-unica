"""Emails to AGENTS about their clients: a new lead, the 5-minute "sigue sin respuesta" reminder, the daily "Seguimiento hoy" digest
and a buyer-alert match. Until now every one of those was only a dry-run outbox row, so no alert ever reached an agent.

⛔ Never to a client. The only addresses used are the agency's own account holders (owners / admins, else the agency email).
The big "Responder por WhatsApp" button is a signed one-tap page on the app host (llave/reply_link.py, /w/<token>): the agent taps
it, taps again, and WhatsApp opens with the agency's approved first reply (replies.render) while the lead is marked contactado, so
the 5-minute reminder does not fire for a lead already answered. Nothing here messages, emails or calls the client.
Short, big text, only the facts that matter (who, which property, what they said), that one button and a link to Clientes.
(The buyer-alert email keeps a plain wa.me "Reenviar" link: there is no lead to mark.) Spanish, tú. Delivery is llave/mailer.py:
without SMTP these become dry-run outbox rows; the WhatsApp dry-run rows stay exactly as they were (no WhatsApp sender yet).
Called from the places that already dedupe (leads.create_lead, lead_watch.remind, lead_watch.follow_up_digest, alerts_buyers.run):
the email goes out once, exactly when their row is queued."""
import re
import sys

from . import db, emails, mail_html as h, mailer, replies, reply_link

NOTE_MAX = 300


# ---------- who gets it ----------
def holders(con, agency_id):
    """[(email, name, user id)] — the agency's account holders (owners / admins); the agency email only if there are none (user id 0)."""
    rows = con.execute("SELECT id, email, name FROM users WHERE agency_id=? AND role IN ('owner','admin') AND email<>'' ORDER BY id",
                       (agency_id,)).fetchall()
    out, seen = [], set()
    for r in rows:
        if r['email'].lower() not in seen:
            seen.add(r['email'].lower())
            out.append((r['email'], r['name'] or '', r['id']))
    if not out:
        ag = con.execute('SELECT email FROM agencies WHERE id=?', (agency_id,)).fetchone()
        if ag and ag['email']:
            out.append((ag['email'], '', 0))
    return out


def recipients(con, agency_id):
    """[(email, name)] — the same people as holders()."""
    return [(email, name) for email, name, _uid in holders(con, agency_id)]


# ---------- small helpers ----------
def fmt_phone(p):
    d = re.sub(r'\D', '', p or '')
    if d.startswith('52') and len(d) == 12:
        return '+52 %s %s %s' % (d[2:4], d[4:8], d[8:])
    return p or ''


def _short(s, n=NOTE_MAX):
    s = re.sub(r'\s+', ' ', (s or '').strip())
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def _clientes(path=''):
    return '%s/clientes%s' % (db.origin('app'), path)


def _subject(text):
    return emails.transactional_subject(text)


def _wa_reply(agency, lead, user_id):
    """The button's link: a signed one-tap page on the app host (llave/reply_link.py) that records the reply and then opens
    wa.me/<client> with the agency's approved wording. Never a bare wa.me link: that would leave the lead "sin respuesta".
    None when the client left no phone."""
    if not lead['phone']:
        return None
    return reply_link.url(lead['id'], agency['id'], user_id)


def _facts(lead, listing_title, listing_ref):
    """[(label, value)] in the order an agent reads them."""
    out = [('Teléfono', fmt_phone(lead['phone']))] if lead['phone'] else []
    if lead['email']:
        out.append(('Correo', lead['email']))
    if listing_title:
        out.append(('Pregunta por', '%s (folio %s)' % (listing_title, listing_ref) if listing_ref else listing_title))
    if (lead['message'] or '').strip():
        out.append(('Dijo', '“%s”' % _short(lead['message'])))
    return out


def _facts_html(rows):
    return ''.join(h.para('<span style="color:%s">%s</span><br><b>%s</b>' % (h.SOFT, h.esc(k), h.esc(v)), 18, bottom=12) for k, v in rows)


def _compose(title, headline, lead_name, facts, button_href, button_label, bolsa, footer_link, intro=''):
    """-> (text, html) for the three lead-shaped emails."""
    text = ['%s\n' % headline]
    if intro:
        text.append('%s\n' % intro)
    text.append(lead_name)
    text += ['%s: %s' % (k, v) for k, v in facts]
    if bolsa:
        text.append(bolsa)
    if button_href:
        text.append('\n%s:\n%s' % (button_label, button_href))
    text.append('\nTus clientes: %s\n' % footer_link)
    html_body = (h.para(h.esc(headline), 15, h.SOFT, bottom=4) + (h.para(h.esc(intro), 17, bottom=10) if intro else '') +
                 h.para(h.esc(lead_name), 30, bold=True, bottom=12) + _facts_html(facts) +
                 (h.para(h.esc(bolsa), 15, h.SOFT, bottom=6) if bolsa else '') +
                 (h.button(button_href, button_label) if button_href else '') +
                 h.para(h.text_link(footer_link, 'Abrir mis clientes'), 16, top=10, bottom=0))
    return '\n'.join(text), h.shell(title, html_body)


def _bolsa_note(con, lead, role):
    """'' unless the lead came through a Bolsa share. Splits are the recipient's share first."""
    if not lead['owner_agency_id'] or lead['owner_agency_id'] == lead['agency_id'] or not lead['listing_id']:
        return ''
    mine = db.share_split(con, lead['listing_id'], lead['agency_id'])
    if role == 'owner':
        return 'Llegó por la Bolsa: otro asesor muestra tu propiedad. Reparto %d/%d.' % (100 - mine, mine)
    return 'Es una propiedad de la Bolsa de otra inmobiliaria. Reparto %d/%d.' % (mine, 100 - mine)


def _listing(con, lead):
    if not lead['listing_id']:
        return None, None
    r = con.execute('SELECT title, ref FROM listings WHERE id=?', (lead['listing_id'],)).fetchone()
    return (r['title'], r['ref']) if r else (None, None)


def _name_for_subject(lead):
    return replies.first_name(lead['name'])


# ---------- the four emails ----------
def new_lead_messages(con, lead_id):
    """-> list of mailer.send kwargs: one per account holder of the receiving agency, and of the owning agency for a Bolsa lead."""
    lead = con.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead or lead['status'] == 'descartado':
        return []
    from . import ghl  # late: ghl imports replies/whatsapp too
    if ghl.is_blocked(lead['name'] or '', lead['email'] or ''):
        return []
    title, ref = _listing(con, lead)
    who = (lead['name'] or '').strip() or 'Alguien'
    first = _name_for_subject(lead)
    subject = _subject('Nuevo cliente: %s' % first if first else 'Nuevo cliente en tu sitio')
    targets = [('receiving', lead['agency_id'])]
    if lead['owner_agency_id'] and lead['owner_agency_id'] != lead['agency_id']:
        targets.append(('owner', lead['owner_agency_id']))
    out = []
    for role, agency_id in targets:
        agency = con.execute('SELECT * FROM agencies WHERE id=?', (agency_id,)).fetchone()
        for email, _name, user_id in holders(con, agency_id):
            wa = _wa_reply(agency, lead, user_id)
            facts = _facts(lead, title, ref)
            text, html = _compose(subject, 'Nuevo cliente en Ficha Única', who, facts, wa, 'Responder por WhatsApp',
                                  _bolsa_note(con, lead, role), _clientes())
            out.append({'to': email, 'subject': subject, 'text': text, 'html': html, 'kind': 'lead_nuevo',
                        'ref': 'email:lead:%d:%d' % (lead_id, agency_id)})
    return out


def reminder_messages(con, lead, minutes):
    """`lead` = a row from lead_watch.overdue(). Goes to the receiving agency only, like the WhatsApp reminder."""
    agency = con.execute('SELECT * FROM agencies WHERE id=?', (lead['agency_id'],)).fetchone()
    first = _name_for_subject(lead)
    subject = _subject('Sin respuesta: %s, %d min' % (first, minutes) if first else 'Cliente sin respuesta, %d min' % minutes)
    who = (lead['name'] or '').strip() or 'Un cliente'
    title, ref = lead.get('listing_title'), lead.get('listing_ref')
    out = []
    for email, _name, user_id in holders(con, lead['agency_id']):
        wa = _wa_reply(agency, lead, user_id)
        text, html = _compose(subject, 'Sigue sin respuesta', who, _facts(lead, title, ref), wa, 'Responder por WhatsApp', '', _clientes(),
                              intro='Te escribió hace %d min%s y nadie le ha contestado.' % (minutes, ' por %s' % title if title else ''))
        out.append({'to': email, 'subject': subject, 'text': text, 'html': html, 'kind': 'lead_sin_respuesta',
                    'ref': 'email:lead_reminder:%d' % lead['id']})
    return out


def digest_messages(con, agency_id, leads, day):
    """`leads` = rows due today (name, phone, listing_title). One email per account holder; the dedupe is the caller's (agency + day)."""
    n = len(leads)
    subject = _subject('Seguimiento hoy: %d cliente%s' % (n, '' if n == 1 else 's'))
    lines_t, lines_h = [], []
    for r in leads[:8]:
        who = (r['name'] or '').strip() or 'Un cliente'
        extra = ' · '.join(x for x in (fmt_phone(r['phone']) if r['phone'] else '', r['listing_title'] or '') if x)
        lines_t.append('- %s%s' % (who, ' (%s)' % extra if extra else ''))
        lines_h.append(h.para('<b>%s</b>%s' % (h.esc(who), '<br><span style="color:%s">%s</span>' % (h.SOFT, h.esc(extra)) if extra else ''), 18, bottom=10))
    if n > 8:
        lines_t.append('y %d más' % (n - 8))
        lines_h.append(h.para('y %d más' % (n - 8), 16, h.SOFT, bottom=10))
    link = _clientes('?estado=hoy')
    head = 'Hoy toca dar seguimiento a %d cliente%s.' % (n, '' if n == 1 else 's')
    text = '%s\n\n%s\n\nVelos aquí:\n%s\n' % (head, '\n'.join(lines_t), link)
    html = h.shell(subject, h.para(h.esc(head), 24, bold=True, bottom=14) + ''.join(lines_h) + h.button(link, 'Ver Seguimiento hoy', h.CEMPA))
    return [{'to': email, 'subject': subject, 'text': text, 'html': html, 'kind': 'seguimiento_hoy',
             'ref': 'email:follow_up_digest:%d:%s' % (agency_id, day)} for email, _name in recipients(con, agency_id)]


def buyer_match_messages(con, agency, search, canonical, forward_link):
    """A saved search (a buyer who asked for alerts on the agent's site) matches one of the agent's listings. The AGENT forwards it."""
    first = replies.first_name(search['name'])
    subject = _subject('Coincidencia para %s' % first if first else 'Una búsqueda guardada coincide')
    price = '$%s %s' % (format(canonical['price'], ','), canonical['currency']) if canonical.get('price') is not None else 'precio a consultar'
    who = (search['name'] or '').strip() or 'Un cliente'
    facts = [('Propiedad', '%s (folio %s)' % (canonical['title'], canonical['ref'])), ('Precio', price)]
    intro = 'Una búsqueda guardada de %s coincide con una propiedad tuya. Tú decides si se la mandas.' % who
    out = []
    for email, _name in recipients(con, agency['id']):
        text, html = _compose(subject, 'Nueva coincidencia', who, facts, forward_link, 'Reenviar por WhatsApp', '', _clientes(), intro=intro)
        out.append({'to': email, 'subject': subject, 'text': text, 'html': html, 'kind': 'coincidencia',
                    'ref': 'email:saved_search:%d:%d' % (search['id'], canonical['id'])})
    return out


# ---------- called by the code that already dedupes ----------
def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as ex:  # an email problem must never break saving a lead or a cron run
        sys.stderr.write('[llave] agent_mail: %s: %s\n' % (type(ex).__name__, str(ex)[:200]))
        return []


def notify_new_lead(con, lead_id):
    """From a web request: real SMTP goes out on a worker thread so the visitor never waits for the mail server."""
    msgs = _safe(new_lead_messages, con, lead_id)
    _safe(mailer.dispatch, con, msgs)
    return len(msgs)


def notify_reminder(con, lead, minutes):
    msgs = _safe(reminder_messages, con, lead, minutes)
    _safe(mailer.dispatch, con, msgs, background=False)   # cron: the process may end right after, so send inline
    return len(msgs)


def notify_digest(con, agency_id, leads, day):
    msgs = _safe(digest_messages, con, agency_id, leads, day)
    _safe(mailer.dispatch, con, msgs, background=False)
    return len(msgs)


def notify_buyer_match(con, agency, search, canonical, forward_link):
    msgs = _safe(buyer_match_messages, con, agency, search, canonical, forward_link)
    _safe(mailer.dispatch, con, msgs, background=False)
    return len(msgs)
