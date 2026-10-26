"""Formatos: fill-in documents for Mexican agents (exclusiva, carta oferta, apartado, visita, referido, privacidad, cierre).
Modelled on the idea of a form library (search + tags + prefilled), written from scratch: no third-party text.
Documents are generated on the fly and printed / saved as PDF by the browser; nothing is stored.
⛔ Legal text is a REFERENCE MODEL until a Mexican lawyer signs off: the panel shows it only when LLAVE_FORMATOS=1."""
import os

DISCLAIMER = ('Modelo de referencia generado en Ficha Única. No sustituye asesoría legal: revísalo con un abogado o notario '
              'antes de firmar. Ficha Única no es parte de este documento.')

# field = (name, label, kind, prefill) ; kind: text | money | date | area ; prefill: '' | 'agent' | 'agency' | 'wa' | 'today'
A = ('asesor', 'Tu nombre (asesor)', 'text', 'agent')
AG = ('agencia', 'Inmobiliaria o nombre comercial', 'text', 'agency')
WA = ('asesor_wa', 'Tu WhatsApp', 'text', 'wa')
CIUDAD = ('ciudad', 'Ciudad', 'text', '')
FECHA = ('fecha', 'Fecha', 'date', 'today')
INMUEBLE = ('inmueble', 'Inmueble (dirección completa)', 'text', '')

FORMATOS = [
    {'key': 'exclusiva', 'title': 'Contrato de exclusiva (venta o renta)', 'tag': 'Captación',
     'about': 'El dueño te autoriza a promover su propiedad de forma exclusiva por un tiempo.',
     'fields': [('propietario', 'Nombre del propietario', 'text', ''), ('operacion', 'Operación (venta o renta)', 'text', ''),
                INMUEBLE, ('precio', 'Precio de lista (MXN)', 'money', ''), ('comision', 'Comisión (%)', 'text', ''),
                ('meses', 'Vigencia (meses)', 'text', '3'), A, AG, CIUDAD, FECHA],
     'body': ['AUTORIZACIÓN DE COMERCIALIZACIÓN EN EXCLUSIVA',
              'En {ciudad}, a {fecha}, {propietario} (el "Propietario") autoriza a {asesor}, de {agencia} (el "Asesor"), a promover en exclusiva la {operacion} del inmueble ubicado en {inmueble}.',
              '1. Precio de lista: {precio} MXN. Cualquier cambio de precio se acuerda por escrito.',
              '2. Vigencia: {meses} meses a partir de esta fecha.',
              '3. Comisión: {comision}% más IVA sobre el precio final de la operación, pagadera solo si la operación se concreta con un comprador o arrendatario presentado durante la vigencia.',
              '4. El Asesor promoverá el inmueble en sus medios, sitio y portales, y atenderá a los interesados. El Propietario dirigirá al Asesor a toda persona que pregunte por el inmueble.',
              '5. El Propietario declara ser titular o tener facultades para disponer del inmueble y que este se encuentra libre de gravámenes no declarados.',
              '6. Los datos personales se tratan conforme al aviso de privacidad del Asesor.',
              'Firmas: ______________________ Propietario        ______________________ Asesor']},
    {'key': 'carta-oferta', 'title': 'Carta oferta de compra', 'tag': 'Venta',
     'about': 'El comprador pone por escrito cuánto ofrece y bajo qué condiciones.',
     'fields': [('comprador', 'Nombre del comprador', 'text', ''), INMUEBLE, ('oferta', 'Monto ofrecido (MXN)', 'money', ''),
                ('forma_pago', 'Forma de pago (contado, crédito…)', 'text', ''), ('apartado', 'Apartado que entrega (MXN)', 'money', ''),
                ('vigencia', 'Esta oferta vence el', 'date', ''), ('condiciones', 'Condiciones', 'area', ''), A, AG, CIUDAD, FECHA],
     'body': ['CARTA OFERTA DE COMPRA',
              'En {ciudad}, a {fecha}, {comprador} (el "Comprador") presenta a través de {asesor}, de {agencia}, la siguiente oferta por el inmueble ubicado en {inmueble}.',
              '1. Monto ofrecido: {oferta} MXN.', '2. Forma de pago: {forma_pago}.', '3. Apartado que se entrega: {apartado} MXN.',
              '4. Condiciones: {condiciones}.', '5. Esta oferta vence el {vigencia}. Es una propuesta y no obliga al propietario a aceptarla.',
              'Firma del comprador: ______________________']},
    {'key': 'apartado', 'title': 'Recibo de apartado', 'tag': 'Venta',
     'about': 'Constancia del dinero que el comprador deja para apartar la propiedad.',
     'fields': [('comprador', 'Nombre de quien aparta', 'text', ''), INMUEBLE, ('monto', 'Monto del apartado (MXN)', 'money', ''),
                ('recibe', 'Quien recibe el dinero', 'text', ''), ('plazo', 'Plazo para firmar (días)', 'text', '15'),
                ('devolucion', 'Si no se concreta, el apartado…', 'text', 'se devuelve íntegro'), A, AG, CIUDAD, FECHA],
     'body': ['RECIBO DE APARTADO',
              'En {ciudad}, a {fecha}, {recibe} recibe de {comprador} la cantidad de {monto} MXN como apartado del inmueble ubicado en {inmueble}.',
              'El inmueble se retira de la oferta por {plazo} días para que las partes formalicen la operación. Si la operación no se concreta, el apartado {devolucion}.',
              'Intermediario: {asesor}, {agencia}.',
              'Firma de quien recibe: ______________________        Firma de quien aparta: ______________________']},
    {'key': 'visita', 'title': 'Hoja de visita', 'tag': 'Clientes',
     'about': 'Registro de que un cliente visitó la propiedad contigo.',
     'fields': [('cliente', 'Nombre del cliente', 'text', ''), ('telefono', 'Teléfono del cliente', 'text', ''), INMUEBLE,
                ('hora', 'Hora de la visita', 'text', ''), A, AG, FECHA],
     'body': ['HOJA DE VISITA',
              'Fecha: {fecha}   Hora: {hora}', 'Cliente: {cliente}   Teléfono: {telefono}', 'Inmueble visitado: {inmueble}',
              'El cliente confirma que {asesor}, de {agencia}, le mostró este inmueble en la fecha indicada.',
              'Firma del cliente: ______________________']},
    {'key': 'referido', 'title': 'Acuerdo de referido entre asesores', 'tag': 'Comisiones',
     'about': 'Cuando dos asesores comparten una operación y se reparten la comisión.',
     'fields': [('asesor_ref', 'Asesor que refiere', 'text', ''), ('cliente', 'Cliente o propiedad referida', 'text', ''),
                ('reparto', 'Reparto de comisión (ej. 50/50)', 'text', '50/50'), A, AG, CIUDAD, FECHA],
     'body': ['ACUERDO DE REFERIDO ENTRE ASESORES',
              'En {ciudad}, a {fecha}, {asesor_ref} refiere a {asesor}, de {agencia}, el siguiente cliente o propiedad: {cliente}.',
              'Si la operación se concreta, la comisión efectivamente cobrada se repartirá {reparto}, dentro de los 5 días hábiles posteriores a su cobro.',
              'Cada asesor responde por sus propios clientes y obligaciones. Este acuerdo no crea una sociedad.',
              'Firmas: ______________________        ______________________']},
    {'key': 'privacidad', 'title': 'Aviso de privacidad para clientes', 'tag': 'Cumplimiento',
     'about': 'El aviso corto que le das a quien te deja sus datos.',
     'fields': [A, AG, ('correo', 'Correo para ejercer derechos', 'text', ''), WA, FECHA],
     'body': ['AVISO DE PRIVACIDAD',
              '{asesor}, de {agencia}, es responsable del tratamiento de tus datos personales (nombre, teléfono, correo y preferencias de búsqueda).',
              'Los usamos para atender tu solicitud, enseñarte propiedades y darte seguimiento. No los vendemos.',
              'Puedes acceder, rectificar, cancelar u oponerte al uso de tus datos escribiendo a {correo} o por WhatsApp al {asesor_wa}.',
              'Última actualización: {fecha}.']},
    {'key': 'cierre', 'title': 'Lista de cierre (compraventa)', 'tag': 'Guías',
     'about': 'Los pasos para llegar a la firma, sin que se te pase nada.',
     'fields': [INMUEBLE, ('cliente', 'Cliente', 'text', ''), A, FECHA],
     'body': ['LISTA DE CIERRE', 'Inmueble: {inmueble}   Cliente: {cliente}   Asesor: {asesor}   Fecha: {fecha}',
              '☐ Identificación oficial de las partes', '☐ Escritura y boleta predial al corriente', '☐ Recibos de agua y luz al corriente',
              '☐ Cuota de mantenimiento al corriente (constancia de no adeudo)', '☐ Certificado de libertad de gravamen',
              '☐ Avalúo (si hay crédito)', '☐ Carta oferta firmada y apartado recibido', '☐ Notario elegido y fecha de firma acordada',
              '☐ Entrega de llaves y acta de entrega']},
]
BY_KEY = {f['key']: f for f in FORMATOS}


def enabled():
    return os.environ.get('LLAVE_FORMATOS') == '1'


def tags():
    return sorted({f['tag'] for f in FORMATOS})


def search(q='', tag=''):
    q = (q or '').strip().lower()
    return [f for f in FORMATOS if (not tag or f['tag'] == tag) and (not q or q in (f['title'] + ' ' + f['about']).lower())]


def prefill(f, user, agency, today):
    out = {}
    for name, _l, _k, pre in f['fields']:
        out[name] = {'agent': user['name'], 'agency': agency['name'], 'wa': user['whatsapp'] or '', 'today': today}.get(pre, pre)
    return out


def render_lines(f, values, esc):
    """Document lines with {field} filled (escaped); a blank field prints as a line to fill by hand."""
    class V(dict):
        def __missing__(self, k):
            return '{' + k + '}'
    vals = V({k: (esc(str(v).strip()) or '__________') for k, v in values.items()})
    return [line.format_map(vals) for line in f['body']]
