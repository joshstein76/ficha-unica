"""Agency dashboard numbers + listing page-view counter. Times are SQLite UTC strings."""
import datetime
import re
import statistics

from . import lead_watch

BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|curl|python', re.I)


def is_bot(user_agent):
    return bool(BOT_RE.search(user_agent or ''))


def record_view(con, listing_id, day=None):
    lead_watch.ensure_columns(con)
    day = day or datetime.datetime.utcnow().strftime('%Y-%m-%d')
    con.execute('INSERT INTO listing_views(listing_id, day, views) VALUES (?,?,1) '
                'ON CONFLICT(listing_id, day) DO UPDATE SET views=views+1', (listing_id, day))
    con.commit()


def _p(s):
    return datetime.datetime.strptime(s, lead_watch.FMT)


def agency_stats(con, agency_id, days=30, now=None):
    lead_watch.ensure_columns(con)
    n = lead_watch._now(now)
    since = n - datetime.timedelta(days=days)
    since_s, since_d = since.strftime(lead_watch.FMT), since.strftime('%Y-%m-%d')
    views = {r['listing_id']: r['v'] for r in con.execute(
        'SELECT v.listing_id, SUM(v.views) AS v FROM listing_views v JOIN listings l ON l.id=v.listing_id '
        'WHERE l.agency_id=? AND v.day>=? GROUP BY v.listing_id', (agency_id, since_d))}
    leads = con.execute(
        'SELECT l.*, li.ref AS listing_ref, li.colonia AS colonia FROM leads l '
        'LEFT JOIN listings li ON li.id=l.listing_id WHERE l.agency_id=? AND l.created_at>=?',
        (agency_id, since_s)).fetchall()
    per_listing_leads = {}
    by_source, by_col, by_week = {}, {}, {}
    for l in leads:
        if l['listing_id'] is not None:
            per_listing_leads[l['listing_id']] = per_listing_leads.get(l['listing_id'], 0) + 1
        by_source[l['source']] = by_source.get(l['source'], 0) + 1
        if l['colonia']:
            by_col[l['colonia']] = by_col.get(l['colonia'], 0) + 1
        y, w, _ = _p(l['created_at']).isocalendar()
        k = '%d-W%02d' % (y, w)
        by_week[k] = by_week.get(k, 0) + 1
    weeks = []
    for i in range(7, -1, -1):
        y, w, _ = (n - datetime.timedelta(weeks=i)).isocalendar()
        weeks.append('%d-W%02d' % (y, w))
    ids = set(views) | set(per_listing_leads)
    info = {r['id']: r for r in con.execute(
        'SELECT id, ref, title FROM listings WHERE agency_id=?', (agency_id,))}
    top = sorted((i for i in ids if i in info), key=lambda i: (-views.get(i, 0), -per_listing_leads.get(i, 0), i))[:10]
    mins = []
    for l in leads:
        if l['first_response_at']:
            mins.append(max((_p(l['first_response_at']) - _p(l['created_at'])).total_seconds() / 60.0, 0))
    unanswered = con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo' "
                             "AND first_response_at IS NULL", (agency_id,)).fetchone()[0]
    return {
        'views_total': sum(views.values()),
        'views_by_listing': [{'ref': info[i]['ref'], 'title': info[i]['title'], 'views': views.get(i, 0),
                              'leads': per_listing_leads.get(i, 0)} for i in top],
        'leads_total': len(leads),
        'leads_by_source': by_source,
        'leads_by_week': [{'week': w, 'leads': by_week.get(w, 0)} for w in weeks],
        'median_first_response_min': round(statistics.median(mins), 1) if mins else None,
        'pct_answered_5min': round(100.0 * sum(1 for m in mins if m <= 5) / len(leads), 1) if leads else None,
        'unanswered_now': unanswered,
        'top_colonias': sorted(by_col.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
    }
