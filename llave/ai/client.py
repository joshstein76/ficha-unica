"""Claude Messages API over urllib (no SDK on this Mac). Never logs the key. Tests inject `transport`."""
import json
import os
import time
import urllib.error
import urllib.request

URL = 'https://api.anthropic.com/v1/messages'
MODEL = 'claude-opus-5-5'
MAX_TOKENS = 16000
VERSION = '2023-06-01'
BETA_FALLBACK = 'server-side-fallback-2026-07-01'
BETA_OAUTH = 'oauth-2025-04-20'
RETRIES = 2
BACKOFF = 1.5  # seconds, doubled per retry (tests patch to 0)
EFFORTS = ('low', 'medium', 'high')


class AIError(Exception):
    pass


class AIRefused(AIError):
    pass


class AIIncomplete(AIError):
    pass


class AIUnavailable(AIError):
    pass


def _creds():
    key = os.environ.get('ANTHROPIC_API_KEY')
    tok = os.environ.get('ANTHROPIC_AUTH_TOKEN')
    return key, tok


def enabled():
    key, tok = _creds()
    return os.environ.get('LLAVE_AI_LIVE') == '1' and bool(key or tok)


def build_request(system, user, schema, effort='medium'):
    """-> (headers, body_dict). Raises AIUnavailable when no credential is set."""
    if effort not in EFFORTS:
        raise ValueError('effort must be one of %s' % (EFFORTS,))
    key, tok = _creds()
    betas = [BETA_FALLBACK]
    headers = {'content-type': 'application/json', 'anthropic-version': VERSION}
    if key:
        headers['x-api-key'] = key
    elif tok:
        headers['Authorization'] = 'Bearer ' + tok
        betas.insert(0, BETA_OAUTH)
    else:
        raise AIUnavailable('No hay credencial de IA configurada')
    headers['anthropic-beta'] = ','.join(betas)
    body = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'system': system,
        'messages': [{'role': 'user', 'content': user}],
        'output_config': {'effort': effort, 'format': {'type': 'json_schema', 'schema': schema}},
        'fallbacks': 'default',
    }
    return headers, body


def _urllib_transport(url, headers, body):
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read()


def parse_response(raw):
    data = json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
    stop = data.get('stop_reason')
    if stop == 'refusal':
        raise AIRefused('El modelo rechazó la solicitud')
    if stop == 'max_tokens':
        raise AIIncomplete('La respuesta se cortó (max_tokens)')
    text = ''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text')
    if not text.strip():
        raise AIError('Respuesta vacía')
    try:
        return json.loads(text)
    except ValueError:
        raise AIError('La respuesta no es JSON válido')


def complete_json(system, user, schema, effort='medium', transport=None):
    headers, body = build_request(system, user, schema, effort)
    payload = json.dumps(body).encode('utf-8')
    send = transport or _urllib_transport
    last = None
    for attempt in range(RETRIES + 1):
        try:
            status, raw = send(URL, headers, payload)
        except (urllib.error.URLError, OSError) as ex:
            last = AIError('Error de red: %s' % type(ex).__name__)
        else:
            if status == 200:
                return parse_response(raw)
            if status in (400, 401, 403, 404):
                raise AIError('La API respondió HTTP %d' % status)
            if status == 429 or status >= 500:
                last = AIError('La API respondió HTTP %d' % status)
            else:
                raise AIError('La API respondió HTTP %d' % status)
        if attempt < RETRIES:
            time.sleep(BACKOFF * (2 ** attempt))
    raise last
