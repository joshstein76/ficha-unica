import unittest
from llave import geo


class T(unittest.TestCase):
    def test_patterns(self):
        cases = ['https://www.google.com/maps/place/X/@19.4326,-99.1332,17z/data=abc',
                 'https://maps.google.com/?q=19.4326,-99.1332',
                 'https://www.google.com/maps?query=19.4326%2C-99.1332',
                 'https://x/data=!3d19.4326!4d-99.1332',
                 'https://maps.google.com/?ll=19.4326,-99.1332&z=15',
                 '19.4326, -99.1332']
        for c in cases:
            self.assertEqual(geo.parse_maps_link(c), (19.4326, -99.1332), c)

    def test_invalid(self):
        for c in (None, '', 'hola', '95.0, -99.1', '40.7128, -74.0060', '19.4, -200',
                  'https://maps.app.goo.gl/AbCdEf123', 'https://www.google.com/maps/place/Polanco'):
            self.assertIsNone(geo.parse_maps_link(c), c)

    def test_approx(self):
        self.assertEqual(geo.approx(19.4326, -99.1332, exact=True), (19.4326, -99.1332))
        a = geo.approx(19.4326, -99.1332)
        self.assertEqual(a, (19.4325, -99.1325))
        self.assertEqual(geo.approx(19.4326, -99.1332), geo.approx(19.4331, -99.1336))
        self.assertLess(abs(a[0] - 19.4326), 0.0013)


if __name__ == '__main__':
    unittest.main()
