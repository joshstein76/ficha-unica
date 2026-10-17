import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import emails  # noqa: E402


class Subjects(unittest.TestCase):
    def test_pattern(self):
        self.assertEqual(emails.subject('Ficha Única', 'Casas Roma'), 'Ficha Única / Casas Roma')
        self.assertEqual(emails.subject('Ficha Única', their_name='laura pérez'), 'Ficha Única / Laura')
        self.assertEqual(emails.to_agent({'name': 'Casas Roma', 'email': 'x@y.mx'}, 'Hola')['subject'], 'Ficha Única / Casas Roma')
        self.assertEqual(emails.to_lead({'name': 'VIVE Polanco'}, 'Ana Ruiz', 'a@b.mx', 'Hola')['subject'], 'VIVE Polanco / Ana')
        self.assertEqual(emails.subject('VIVE Polanco', their_name='@ana_88'), 'VIVE Polanco')  # never a handle


if __name__ == '__main__':
    unittest.main()
