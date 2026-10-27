#!/usr/bin/env python3
"""ONE-OFF: geocode demo listings (lat NULL) in data/llave.db via Nominatim. Max 20 requests, 1.5 s apart."""
import json, os, sys, time, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, geo  # noqa: E402

UA = 'FichaUnica-local-demo/1.0 (contacto@vivepolanco.test)'
MAX_REQ = 20


def main():
    con = db.connect(db.DB_PATH)  # LLAVE_DB on the server
    rows = con.execute('SELECT id, ref, street, ext_number, colonia, municipio, estado FROM listings WHERE lat IS NULL').fetchall()
    cache, reqs = {}, 0
    for r in rows:
        q = '%s %s, %s, %s, %s, México' % (r['street'] or '', r['ext_number'] or '', r['colonia'] or '',
                                         r['municipio'] or '', r['estado'] or '')
        q = ' '.join(q.split())
        if q not in cache:
            if reqs >= MAX_REQ:
                print('%s: skipped (request cap)' % r['ref'])
                continue
            if reqs:
                time.sleep(1.5)
            url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
                {'format': 'json', 'limit': 1, 'countrycodes': 'mx', 'q': q})
            reqs += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=20) as f:
                    cache[q] = json.load(f)
            except Exception as e:
                print('%s: error %s' % (r['ref'], e))
                cache[q] = []
        res = cache[q]
        pt = geo.parse_maps_link('%s,%s' % (res[0]['lat'], res[0]['lon'])) if res else None
        if not pt:
            print('%s: no result / outside Mexico  (%s)' % (r['ref'], q))
            continue
        con.execute('UPDATE listings SET lat=?, lng=? WHERE id=?', (pt[0], pt[1], r['id']))
        con.commit()
        print('%s: %.5f, %.5f  (%s)' % (r['ref'], pt[0], pt[1], q))
    print('requests: %d' % reqs)


if __name__ == '__main__':
    main()
