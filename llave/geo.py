"""Map helpers. No network here."""
import re
from urllib.parse import unquote

LAT_RANGE = (14.3, 32.8)
LNG_RANGE = (-118.6, -86.6)
_N = r'(-?\d{1,3}(?:\.\d+)?)'
_PATTERNS = [
    re.compile(r'!3d' + _N + r'!4d' + _N),
    re.compile(r'@' + _N + r',\s*' + _N),
    re.compile(r'(?:[?&](?:q|query|ll|center|destination)=)\s*' + _N + r'\s*,\s*' + _N),
    re.compile(r'^\s*' + _N + r'\s*,\s*' + _N + r'\s*$'),
]


def _in_mexico(lat, lng):
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


def parse_maps_link(text):
    if not text or not isinstance(text, str):
        return None
    t = unquote(text.strip())
    for p in _PATTERNS:
        m = p.search(t)
        if m:
            try:
                lat, lng = float(m.group(1)), float(m.group(2))
            except ValueError:
                continue
            if _in_mexico(lat, lng):
                return (lat, lng)
            return None
    return None


def approx(lat, lng, exact=False):
    if exact:
        return (lat, lng)
    g = 0.0025
    return (round(round(lat / g) * g, 4), round(round(lng / g) * g, 4))
