"""Home on the shared agent dashboard kit, in the Lotería look (Josh 2026-11-03).
The kit files (agent-dash.css / agent-dash.js) are the master that IDX Bloom also uses and must stay byte-identical; everything that is
Ficha Única specific lives in ficha-unica-brand.json and ficha-loteria.css, which is scoped under .adk. No server needed."""
import hashlib
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llave.web import styles  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'llave', 'web', 'static')
KIT_MASTER = {  # sha256 of the master kit 1.2.1; update these two lines (and kit_home.KIT_VERSION) only when the master itself is upgraded
    'agent-dash.css': '5441051af774031eae958a07eed41a109c6ba940db8232c2020e8c7517c6f189',
    'agent-dash.js': 'a7d9bff10b3f2605ba95ef7b15ce67a8aa42e98c12d8318904b63997b6e94b59',
}


def read(name):
    with open(os.path.join(STATIC, name), encoding='utf-8') as fh:
        return fh.read()


def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def selectors(css):
    """Every selector of every style rule (descends into @media, skips @keyframes steps)."""
    out = []

    def walk(text):
        i = 0
        while i < len(text):
            j = text.find('{', i)
            if j < 0:
                break
            depth, k = 1, j + 1
            while depth and k < len(text):
                depth += (text[k] == '{') - (text[k] == '}')
                k += 1
            prelude, body = text[i:j].strip(), text[j + 1:k - 1]
            if prelude.startswith('@keyframes'):
                pass
            elif prelude.startswith('@'):
                walk(body)
            else:
                out.extend(x.strip() for x in prelude.split(','))
            i = k

    walk(strip_comments(css))
    return out


class LoteriaKit(unittest.TestCase):
    def test_master_kit_files_untouched(self):
        for name, sha in KIT_MASTER.items():
            with open(os.path.join(STATIC, name), 'rb') as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, name + ' must stay byte-identical to the IDX Bloom master')

    def test_skin_is_scoped_under_adk(self):
        css = read('ficha-loteria.css')
        sels = selectors(css)
        self.assertGreater(len(sels), 80)
        for sel in sels:
            self.assertTrue(sel.startswith('.adk'), sel)

    def test_skin_has_no_blur_no_gradient_only_hard_shadows(self):
        css = strip_comments(read('ficha-loteria.css'))
        self.assertNotIn('gradient', css)
        self.assertNotIn('blur', css)
        self.assertNotIn('rgba', css)
        for value in re.findall(r'box-shadow:\s*([^;}]+)', css):
            for shadow in re.split(r',\s*(?![^()]*\))', value):
                lengths = [t for t in shadow.split() if re.match(r'^-?[\d.]+(px)?$', t)]
                if len(lengths) >= 3:
                    self.assertEqual(float(lengths[2].replace('px', '')), 0, shadow)     # blur radius is always 0

    def test_skin_hides_the_kit_top_tabs_under_900(self):
        css = strip_comments(read('ficha-loteria.css'))
        m = re.search(r'@media \(max-width: 899\.98px\)\s*\{(.*?)\n\}', css, re.S)
        self.assertTrue(m)
        self.assertRegex(m.group(1), r'\.adk \.adk-tabs\s*\{\s*display:\s*none;')

    def test_skin_covers_the_home_parts(self):
        css = read('ficha-loteria.css')
        for cls in ('adk-top', 'adk-stat', 'adk-next', 'adk-tool', 'adk-svc', 'adk-check__item', 'adk-check__mark', 'adk-check__li--done',
                    'adk-alert', 'adk-refer', 'adk-btn', 'adk-tab'):
            self.assertIn(cls, css)
        done = re.search(r'\.adk \.adk-check__li--done \.adk-check__mark \{([^}]*)\}', css)
        self.assertTrue(done)
        for part in ('background: var(--lt-chile)', 'border-color: var(--lt-tinta)', 'inset 0 0 0 5px var(--lt-papel)'):   # the ficha token
            self.assertIn(part, done.group(1))
        self.assertIn('prefers-reduced-motion', css)

    def test_brand_json_tokens(self):
        b = json.loads(read('ficha-unica-brand.json'))
        t = b['tokens']
        self.assertEqual((t['bg'], t['ink'], t['accent'], t['onAccent'], t['accentText'], t['card']),
                         ('#FFF9EE', '#1B1236', '#FF4F1F', '#1B1236', '#5B2EE6', '#FFFFFF'))
        self.assertTrue(b['font'].startswith('Figtree'))
        self.assertNotIn('Onest', b['font'])
        self.assertEqual(b['logo'], '/_s/fu-mark.svg')
        for fg, bg in (('ink', 'bg'), ('ink', 'card'), ('muted', 'bg'), ('muted', 'card'), ('onAccent', 'accent'), ('accentText', 'bg'),
                       ('accentText', 'card'), ('ink', 'soft')):
            self.assertGreaterEqual(styles.contrast(t[fg], t[bg]), 4.5, (fg, bg))

    def test_logo_files(self):
        svg = read('fu-mark.svg')
        self.assertIn('<circle cx="88" cy="50" r="11"/>', svg)
        self.assertNotIn('Gradient', svg)
        self.assertIn('#FF4F1F', svg)
        self.assertEqual(styles.mark_svg('a'), styles.mark_svg('b'))      # no ids: copies never clash


if __name__ == '__main__':
    unittest.main()
