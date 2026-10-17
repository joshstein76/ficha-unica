"""Portal registry: what LLAVE can feed, and how. UI shows `name` and `notes` (Spanish)."""
from collections import OrderedDict

NEEDS = 'Requiere convenio con el portal; lo pedimos con tu OK.'
PORTALS = OrderedDict([
    ('trovit', {'name': 'Trovit', 'status': 'open', 'format': 'trovit_xml',
                'notes': 'Agregador: lee el feed XML de tu sitio. Activación y costo por confirmar con Lifull Connect.'}),
    ('mitula', {'name': 'Mitula', 'status': 'open', 'format': 'mitula_xml',
                'notes': 'Agregador: lee el feed XML de tu sitio. Activación y costo por confirmar con Lifull Connect.'}),
    ('nestoria', {'name': 'Nestoria', 'status': 'open', 'format': 'trovit_xml',
                  'notes': 'Mismo grupo que Trovit (Lifull Connect); usa el mismo feed.'}),
    ('nuroa', {'name': 'Nuroa', 'status': 'open', 'format': 'trovit_xml',
               'notes': 'Mismo grupo que Trovit (Lifull Connect); usa el mismo feed.'}),
    ('llave_open', {'name': 'Feed abierto LLAVE', 'status': 'open', 'format': 'llave_xml',
                    'notes': 'Nuestro feed XML/JSON documentado para cualquier socio. Incluye todas tus propiedades públicas.'}),
    ('mercadolibre', {'name': 'Mercado Libre Inmuebles', 'status': 'api', 'format': 'mercadolibre_api',
                      'notes': 'API pública. Conectas tu propia cuenta (OAuth); por ahora solo vista previa.'}),
] + [(k, {'name': n, 'status': 'needs_agreement', 'format': 'stub', 'notes': NEEDS}) for k, n in (
    ('propiedades', 'Propiedades.com'), ('proppit', 'Proppit'), ('lamudi', 'Lamudi'),
    ('inmuebles24', 'Inmuebles24'), ('vivanuncios', 'Vivanuncios'), ('casasyterrenos', 'Casas y Terrenos'))])

# Alias handled by build_feed only (not a toggle in the UI)
JSON_ALIAS = 'llave_open_json'
