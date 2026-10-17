"""Adapters for portals with no public spec (needs_agreement). They emit an empty, clearly-inactive feed."""
from xml.sax.saxutils import escape

from .registry import PORTALS


def to_ad(c):
    """Mapping sketch for when a convenio gives us a spec. Fields most MX portals ask for (unverified)."""
    a = c['address']
    return {'codigo': c['ref'], 'titulo': c['title'], 'descripcion': c['description'],
            'operacion': c['operation'], 'tipo': c['property_type'], 'precio': c['price'], 'moneda': c['currency'],
            'colonia': a['colonia'], 'municipio': a['municipio'], 'estado': a['estado'], 'cp': a['cp'],
            'recamaras': c['bedrooms'], 'banos': c['bathrooms'], 'estacionamientos': c['parking'],
            'm2_construidos': c['m2_built'], 'm2_terreno': c['m2_land'], 'fotos': [p['url'] for p in c['photos']]}


def stub_feed(portal):
    name = escape(PORTALS[portal]['name'])
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!-- %s: feed NO activo. No hay especificación pública ni convenio; 0 anuncios. -->\n'
           '<ads portal="%s" active="false"></ads>\n') % (name, portal)
    return 'application/xml; charset=utf-8', xml.encode('utf-8')
