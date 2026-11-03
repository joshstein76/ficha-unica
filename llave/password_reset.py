"""Password reset by email (2026-11-03): a locked-out agent was lost forever.

request() makes a token for a known email; the emailed link carries the token, the database keeps only its SHA-256.
A token works once, for 60 minutes. complete() sets the new password and ends every session of that user.
The page answers the same whether or not the email has an account (the caller decides what to show); nothing here sends mail."""
import datetime
import hashlib
import secrets

from . import auth, db, mail_html as h

TTL_MINUTES = 60
MIN_PASSWORD = 8
FMT = '%Y-%m-%d %H:%M:%S'
EMAIL_KIND = 'reset'   # mailer.PRIVATE_KINDS: the outbox keeps no copy of the link


class InvalidToken(ValueError):
    """Unknown, used or expired: one answer for all three, so a link says nothing about why it fails."""


def hash_token(token):
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def _now(now):
    return now or datetime.datetime.utcnow().replace(microsecond=0)


def request(con, email, now=None):
    """-> (user row, plain token) for a known email, else None. Older unused links of that user stop working."""
    u = con.execute('SELECT * FROM users WHERE email=?', ((email or '').strip().lower(),)).fetchone()
    if not u:
        return None
    n = _now(now)
    token = secrets.token_urlsafe(32)
    con.execute('UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL', (n.strftime(FMT), u['id']))
    con.execute('INSERT INTO password_resets(token_hash, user_id, expires_at) VALUES (?,?,?)',
                (hash_token(token), u['id'], (n + datetime.timedelta(minutes=TTL_MINUTES)).strftime(FMT)))
    con.execute('DELETE FROM password_resets WHERE expires_at < ?', ((n - datetime.timedelta(days=2)).strftime(FMT),))
    db.audit(con, 'user:%d' % u['id'], 'password_reset_requested', '')
    con.commit()
    return u, token


def lookup(con, token, now=None):
    """The reset row when the token is unused and not expired, else None."""
    if not token or len(token) > 200:
        return None
    return con.execute('SELECT * FROM password_resets WHERE token_hash=? AND used_at IS NULL AND expires_at > ?',
                       (hash_token(token), _now(now).strftime(FMT))).fetchone()


def complete(con, token, password, now=None):
    """Set the new password with a valid token -> user id. Raises InvalidToken, or ValueError (Spanish) for a weak password.
    Single use even under two parallel requests; every session of the user ends (the caller then opens a fresh one)."""
    if len(password or '') < MIN_PASSWORD:
        raise ValueError('La contraseña debe tener al menos %d caracteres.' % MIN_PASSWORD)
    new_hash = auth.hash_password(password)  # slow on purpose: done before taking the write lock
    n = _now(now).strftime(FMT)
    try:
        if not con.in_transaction:
            con.execute('BEGIN IMMEDIATE')
        won = con.execute('UPDATE password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at > ?',
                          (n, hash_token(token), n)).rowcount
        if won != 1:
            con.rollback()
            raise InvalidToken('Este enlace ya se usó o venció.')
        uid = con.execute('SELECT user_id FROM password_resets WHERE token_hash=?', (hash_token(token),)).fetchone()['user_id']
        con.execute('UPDATE users SET password_hash=? WHERE id=?', (new_hash, uid))
        con.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        con.execute('UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL', (n, uid))
        db.audit(con, 'user:%d' % uid, 'password_reset_done', 'sessions ended')
        con.commit()
        return uid
    except Exception:
        con.rollback()
        raise


def reset_url(token):
    return '%s/restablecer?t=%s' % (db.origin('app'), token)


def email_for(user, token):
    """-> mailer.send kwargs (without the connection). Spanish, tú, one big button."""
    link = reset_url(token)
    name = (user['name'] or '').split(' ')[0] if 'name' in user.keys() else ''
    hello = 'Hola %s,' % name if name else 'Hola,'
    subject = 'Restablece tu contraseña'
    text = ('%s\n\nPediste cambiar tu contraseña de Ficha Única. Abre este enlace para elegir una nueva '
            '(vale %d minutos y se usa una sola vez):\n\n%s\n\nSi no fuiste tú, ignora este correo: tu contraseña sigue igual.\n'
            % (hello, TTL_MINUTES, link))
    html = h.shell(subject,
                   h.para(h.esc(hello), 20, bold=True) +
                   h.para('Pediste cambiar tu contraseña de Ficha Única. Toca el botón para elegir una nueva. '
                          'Vale %d minutos y se usa una sola vez.' % TTL_MINUTES, 18) +
                   h.button(link, 'Elegir mi contraseña', h.CEMPA) +
                   h.para('Si el botón no abre, copia este enlace en tu navegador:<br>%s' % h.esc(link), 13, h.SOFT, top=8) +
                   h.para('Si no fuiste tú, ignora este correo: tu contraseña sigue igual.', 15, top=6, bottom=0))
    return {'to': user['email'], 'subject': subject, 'text': text, 'html': html, 'kind': EMAIL_KIND, 'ref': 'password_reset:%d' % user['id']}
