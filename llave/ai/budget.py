"""Hard monthly spend cap for live AI (Josh 10-18: US$50/month, alert at 80% to Samantha's WATCHDOG-ALERTS).
Every call is checked BEFORE it is sent against a worst-case cost, so the cap can't be overshot; real usage is recorded after."""
import datetime
import json
import os

from .. import db

# USD per 1M tokens (claude-api reference, cached 2026-10-06). Unknown models are priced as the most expensive known one.
PRICES = {'claude-opus-5-5': (4.00, 20.00), 'claude-sonnet-5-5': (2.00, 10.00), 'claude-haiku-5-5': (0.10, 0.50)}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_WATCHDOG = os.path.join(os.path.dirname(ROOT), 'josh-command-center', '_foundation', 'WATCHDOG-ALERTS.md')


def cap_usd():
    try:
        return float(os.environ.get('LLAVE_AI_MONTHLY_CAP_USD', '50'))
    except ValueError:
        return 50.0


def _month(now=None):
    return (now or datetime.datetime.utcnow()).strftime('%Y-%m')


def ensure_table(con):
    con.execute("CREATE TABLE IF NOT EXISTS ai_usage (month TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, "
                "input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, "
                "cost_usd REAL NOT NULL DEFAULT 0, alerted_80 INTEGER NOT NULL DEFAULT 0)")


def price(model):
    return PRICES.get(model) or max(PRICES.values())


def cost(model, input_tokens, output_tokens):
    pin, pout = price(model)
    return (input_tokens * pin + output_tokens * pout) / 1e6


def spent(con, now=None):
    ensure_table(con)
    r = con.execute('SELECT cost_usd FROM ai_usage WHERE month=?', (_month(now),)).fetchone()
    return r['cost_usd'] if r else 0.0


def allow(con, model, est_input_tokens, max_output_tokens, now=None):
    """True if even the worst case of this call keeps the month under the cap."""
    return spent(con, now) + cost(model, est_input_tokens, max_output_tokens) <= cap_usd()


def record(con, model, usage, now=None, watchdog_path=None):
    """Add a call's real usage; write the 80% alert once per month. Returns the new monthly total."""
    ensure_table(con)
    u = usage or {}
    inp = int(u.get('input_tokens') or 0) + int(u.get('cache_creation_input_tokens') or 0) + int(u.get('cache_read_input_tokens') or 0)
    out = int(u.get('output_tokens') or 0)
    c = cost(model, inp, out)
    m = _month(now)
    con.execute('INSERT INTO ai_usage(month, calls, input_tokens, output_tokens, cost_usd) VALUES (?,1,?,?,?) '
                'ON CONFLICT(month) DO UPDATE SET calls=calls+1, input_tokens=input_tokens+excluded.input_tokens, '
                'output_tokens=output_tokens+excluded.output_tokens, cost_usd=cost_usd+excluded.cost_usd', (m, inp, out, c))
    row = con.execute('SELECT * FROM ai_usage WHERE month=?', (m,)).fetchone()
    if row['cost_usd'] >= 0.8 * cap_usd() and not row['alerted_80']:
        line = ('- %s · Ficha Única · AI spend at %d%% of the monthly cap (US$%.2f of US$%.0f, %d calls). '
                'At 100%% the AI pauses and agents get the template texts. Raise LLAVE_AI_MONTHLY_CAP_USD only with Josh\'s OK.\n') % (
            (now or datetime.datetime.utcnow()).strftime('%Y-%m-%d %H:%M UTC'), int(100 * row['cost_usd'] / cap_usd()),
            row['cost_usd'], cap_usd(), row['calls'])
        path = watchdog_path or os.environ.get('LLAVE_WATCHDOG_FILE') or DEFAULT_WATCHDOG
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
        except OSError:
            pass
        con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('alert.ai_budget', ?, ?, 'dry_run')",
                    (m, json.dumps({'text': line.strip()}, ensure_ascii=False)))
        con.execute('UPDATE ai_usage SET alerted_80=1 WHERE month=?', (m,))
    con.commit()
    return row['cost_usd']
