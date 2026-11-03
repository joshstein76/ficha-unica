"""Names the product must never say in public, for the test guards only. This repo is public, so they stay out of plain text (rot13)."""
import codecs
import re


def _rx(*coded):
    names = [codecs.decode(x, 'rot13') for x in coded]
    return re.compile('|'.join(r'\s*'.join(map(re.escape, n.split())) for n in names), re.I)


_RIVALS = ('rnfl oebxre', 'vqkobbfg', 'jvttbg', 'gbxxb', 'ybxngvba', 'cynprfgre')
RIVALS = _rx(*_RIVALS)
RIVALS_AND_PORTALS = _rx(*_RIVALS, 'vazhroyrf24', 'ynzhqv')
