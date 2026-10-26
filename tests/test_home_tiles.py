import datetime
import unittest

from llave.web import panel


class HomeTiles(unittest.TestCase):
    def test_greeting_by_hour(self):
        d = datetime.datetime
        self.assertEqual(panel.greeting(d(2026, 10, 26, 9)), 'Buenos días')
        self.assertEqual(panel.greeting(d(2026, 10, 26, 15)), 'Buenas tardes')
        self.assertEqual(panel.greeting(d(2026, 10, 26, 21)), 'Buenas noches')

    def test_tiles_are_honest_about_portals(self):
        h = panel.home_tiles()
        self.assertIn('en camino', h)
        self.assertEqual(h.count('class="tile"'), 8)

    def test_first_week_progress(self):
        h = panel.first_week(2, 5, [(True, 'a', '/a'), (True, 'b', '/b'), (False, 'c', '/c'), (False, 'd', '/d'), (False, 'e', '/e')])
        self.assertIn('2/5', h)
        self.assertIn('width:40%', h)


if __name__ == '__main__':
    unittest.main()
