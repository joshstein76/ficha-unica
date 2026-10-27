"""Calculadoras for agents: what the seller takes home (hoja neta) and estimated buying costs.
Pure functions, integer centavos, nothing stored. ⛔ No tax rate is hardcoded except the editable 16% IVA default:
ISAI and notary fees vary by state, so the agent types them. Every result carries NOTE."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

NOTE = 'Estimación con los datos que tú pusiste; confirma montos con tu notario.'
IVA_DEFAULT = '16'  # form default only, always editable


def parse_money(raw, label, required=False):
    """'4,500,000.50' -> centavos. Blank = None (or error when required). Negative / non-numeric -> ValueError."""
    raw = (raw or '').replace(',', '').replace('$', '').strip()
    if not raw:
        if required:
            raise ValueError('Falta: %s.' % label)
        return None
    try:
        d = Decimal(raw)
    except InvalidOperation:
        raise ValueError('%s debe ser un número, por ejemplo 4500000.' % label)
    if not d.is_finite() or d < 0:
        raise ValueError('%s no puede ser negativo.' % label)
    return int((d * 100).quantize(Decimal(1), ROUND_HALF_UP))


def parse_pct(raw, label):
    """'3.5' -> Decimal('3.5'); must be 0-100. Required: percentages have no silent default."""
    raw = (raw or '').replace('%', '').replace(',', '.').strip()
    if not raw:
        raise ValueError('Falta: %s.' % label)
    try:
        d = Decimal(raw)
    except InvalidOperation:
        raise ValueError('%s debe ser un número, por ejemplo 3.5.' % label)
    if not d.is_finite() or d < 0 or d > 100:
        raise ValueError('%s debe estar entre 0 y 100.' % label)
    return d


def pct_of(cents, pct):
    return int((Decimal(cents) * pct / 100).quantize(Decimal(1), ROUND_HALF_UP))


def fmt(cents):
    sign = '-' if cents < 0 else ''
    c = abs(cents)
    return '%s$%s.%02d MXN' % (sign, '{:,}'.format(c // 100), c % 100)


def neta(precio, comision, iva, hipoteca='', adeudos='', otros=''):
    """Seller's net sheet. Returns {'rows': [(label, cents)], 'neto': cents}; raises ValueError on bad input."""
    p = parse_money(precio, 'el precio de venta', True)
    if p <= 0:
        raise ValueError('El precio de venta debe ser mayor a cero.')
    com = pct_of(p, parse_pct(comision, 'la comisión (%)'))
    iva_c = pct_of(com, parse_pct(iva, 'el IVA sobre la comisión (%)'))
    hip = parse_money(hipoteca, 'el saldo de hipoteca') or 0
    deu = parse_money(adeudos, 'los adeudos') or 0
    otr = parse_money(otros, 'otros gastos') or 0
    rows = [('Precio de venta', p), ('Comisión', -com), ('IVA sobre la comisión', -iva_c),
            ('Saldo de hipoteca', -hip), ('Adeudos (predial, agua, mantenimiento)', -deu), ('Otros gastos', -otr)]
    return {'rows': rows, 'neto': p - com - iva_c - hip - deu - otr}


def compra(precio, isai, honorarios='', avaluo='', otros=''):
    """Estimated buying costs. ISAI % has no default (varies by state). Returns {'rows', 'total', 'con_precio'}."""
    p = parse_money(precio, 'el precio', True)
    if p <= 0:
        raise ValueError('El precio debe ser mayor a cero.')
    imp = pct_of(p, parse_pct(isai, 'el % de impuesto de adquisición (ISAI)'))
    hon = parse_money(honorarios, 'los honorarios notariales y derechos') or 0
    ava = parse_money(avaluo, 'el avalúo') or 0
    otr = parse_money(otros, 'otros gastos') or 0
    rows = [('Impuesto de adquisición (ISAI)', imp), ('Honorarios notariales y derechos', hon), ('Avalúo', ava), ('Otros gastos', otr)]
    total = imp + hon + ava + otr
    return {'rows': rows, 'total': total, 'con_precio': p + total}
