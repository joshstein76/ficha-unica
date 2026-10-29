"""Portal registry: what LLAVE can feed, and how. UI shows `name` and `notes` (Spanish)."""
from collections import OrderedDict

NEEDS = 'Requiere convenio con el portal; lo pedimos con tu OK.'
# 'partner_only' = aggregators that take feeds from portals only (help.trovit.com, 2026-10-29), not from an agent's site.
# Feed format stays built for when Ficha Única applies as a portal; agents can't switch them on.
AGGREGATOR = 'Buscador de anuncios: solo recibe anuncios de portales, no de asesores. Estará aquí cuando Ficha Única sea portal aliado.'
PORTALS = OrderedDict([
    ('trovit', {'name': 'Trovit', 'status': 'partner_only', 'format': 'trovit_xml', 'notes': AGGREGATOR}),
    ('mitula', {'name': 'Mitula', 'status': 'partner_only', 'format': 'mitula_xml', 'notes': AGGREGATOR}),
    ('nestoria', {'name': 'Nestoria', 'status': 'partner_only', 'format': 'trovit_xml', 'notes': AGGREGATOR}),
    ('nuroa', {'name': 'Nuroa', 'status': 'partner_only', 'format': 'trovit_xml', 'notes': AGGREGATOR}),
    ('llave_open', {'name': 'Feed abierto Ficha Única', 'status': 'open', 'format': 'llave_xml',
                    'notes': 'Nuestro feed XML/JSON documentado para cualquier socio. Incluye todas tus propiedades públicas.'}),
    ('mercadolibre', {'name': 'Mercado Libre Inmuebles', 'status': 'api', 'format': 'mercadolibre_api',
                      'notes': 'API pública. Conectas tu propia cuenta (OAuth); por ahora solo vista previa.'}),
] + [(k, {'name': n, 'status': 'needs_agreement', 'format': 'stub', 'notes': NEEDS}) for k, n in (
    ('propiedades', 'Propiedades.com'), ('proppit', 'Proppit'), ('lamudi', 'Lamudi'),
    ('inmuebles24', 'Inmuebles24'), ('vivanuncios', 'Vivanuncios'), ('casasyterrenos', 'Casas y Terrenos'))])

# Alias handled by build_feed only (not a toggle in the UI)
JSON_ALIAS = 'llave_open_json'
