"""Novedades: short updates from us, newest first. Only things that already work in the app.
Add an entry at the TOP: (YYYY-MM-DD, title, one-line body, internal link or '')."""
NOVEDADES = [
    ('2026-10-26', 'Tu panel, más fácil', 'Ahora tu inicio tiene tus herramientas a un toque y una lista para tu primera semana.', '/'),
    ('2026-10-23', 'Confirma tus precios con un toque', 'Si un precio lleva 30 días sin confirmarse, te avisamos en tu inicio.', '/precios'),
    ('2026-10-19', 'Invita a un colega', 'Por cada colega que publique con tu enlace, tú ganas propiedades extra.', '/invitar'),
]


def latest(n=3):
    return NOVEDADES[:n]


def unread(seen):
    """How many entries are newer than the date the user last opened Novedades (None = never)."""
    return sum(1 for d, *_ in NOVEDADES if not seen or d > seen)
