"""Academia: short text lessons in Mexican Spanish ("tú"). Videos come later and need Josh's OK on script and cut.
Each lesson: (slug, title, summary, minutes, [(step title, step text)], closing tip).
Only describe things the app already does. No promises of leads, rankings or income."""
LESSONS = [
    ('primera-propiedad', 'Tu primera propiedad en 10 minutos', 'Del celular a tu sitio y a Google.', 10, [
        ('Ten a la mano', 'Al menos cinco fotos, el precio, la colonia y las medidas.'),
        ('Paso 1: fotos, operación y tipo', 'En Nueva propiedad elige tus fotos, si es venta o renta y el tipo. Con eso se crea tu borrador; si sales, no se pierde.'),
        ('Paso 2: dónde y cuánto', 'Precio, colonia, alcaldía o municipio, metros, recámaras y baños. Guardamos el precio con la fecha de hoy y cada mes te preguntamos si sigue igual.'),
        ('Paso 3: título y descripción', 'El título ya viene sugerido: ajústalo, corto y claro. Describe la propiedad como se la dirías a un cliente por teléfono.'),
        ('Publica y comparte', 'Toca Publicar y luego Compartir por WhatsApp. En Mi sitio puedes cambiar el diseño, tu color y tu logo.'),
    ], 'Cuando alguien deje sus datos en tu sitio te llega a tu WhatsApp y aparece en Clientes.'),
    ('fotos-que-venden', 'Fotos que venden con tu celular', 'Luz, ángulos y orden: lo que más cambia una ficha.', 6, [
        ('Luz de día', 'Abre cortinas y prende todas las luces. Evita el flash.'),
        ('Horizontal y a la altura del pecho', 'Fotos horizontales, celular recto, desde una esquina para que se vea todo el cuarto.'),
        ('Limpia antes de fotografiar', 'Quita objetos personales, cables y ropa. Un cuarto despejado se ve más grande.'),
        ('El orden importa', 'La portada es la más luminosa: sala o vista. Sigue con cocina, recámaras, baños y áreas comunes.'),
        ('Lo que la app hace por ti', 'Ajustamos el tamaño y quitamos la ubicación del celular. Si una foto es muy chica o es un logo, te avisamos y no la usamos.'),
    ], 'Mejor ocho fotos buenas que veinte regulares.'),
    ('google-y-chatgpt', 'Aparecer en Google y en ChatGPT', 'Qué lee un buscador en tu ficha y cómo ayudarle.', 7, [
        ('Dato claro y completo', 'Colonia, alcaldía o municipio, metros, recámaras y baños. Es lo que más se busca y se filtra.'),
        ('Título corto con lo importante', 'Tipo, operación y zona. Sin mayúsculas ni signos de más.'),
        ('Descripción real', 'Escribe lo que realmente tiene la propiedad. Los buscadores y los asistentes de IA leen texto claro y específico.'),
        ('Precio al día', 'Confirma tus precios cuando te lo pedimos: un precio reciente da confianza a quien lo ve.'),
        ('Tu perfil de asesor', 'En Mi perfil puedes mostrar tu foto, zonas y WhatsApp en tu página pública.'),
    ], 'Nadie puede garantizar un lugar en Google: lo que sí controlas es que tu ficha sea clara y completa.'),
    ('responder-en-5-minutos', 'Responder en 5 minutos por WhatsApp', 'El primer mensaje y cómo agendar la visita.', 5, [
        ('Cuando llega un cliente', 'Te avisamos por WhatsApp y aparece en Clientes con su mensaje.'),
        ('Responde rápido', 'La respuesta en pocos minutos es lo que más ayuda a avanzar. Si se te pasa, te recordamos.'),
        ('Primer mensaje', 'Salúdalo por su nombre, menciona la propiedad que vio y pregunta cuándo le gustaría visitarla. Tu mensaje base ya viene listo y lo cambias en Mi sitio.'),
        ('Agenda la visita', 'Ofrece dos horarios concretos en lugar de preguntar "¿cuándo puedes?".'),
        ('Seguimiento hoy', 'Si hoy no puede, marca Mañana, 3 días o 1 semana en el cliente y te lo recordamos.'),
    ], 'Cada cliente debería terminar en visita, en seguimiento programado o en "no contactar".'),
    ('compartir-en-la-bolsa', 'Compartir en la Bolsa sin perder comisión', 'Cómo funciona la división y qué acordar por escrito.', 6, [
        ('Qué es la Bolsa', 'Si activas "Compartir en la Bolsa" en una propiedad, otros asesores de Ficha Única pueden mostrarla en su sitio con su contacto. Es una herramienta del plan Pro.'),
        ('La división', 'Tú fijas el porcentaje de la propiedad. La Bolsa 50/50 es la referencia habitual.'),
        ('Una sola casa oficial', 'La propiedad sigue teniendo una página principal tuya; las copias apuntan a ella.'),
        ('Acuerda por escrito', 'Antes de cerrar con un colega, deja en un mensaje o documento el porcentaje, quién cobra y cuándo.'),
        ('Revisa con tu asesor legal', 'Los acuerdos de comisión dependen de tu caso. Consulta a un abogado si tienes dudas.'),
    ], 'Compartir te da más ojos sobre tu propiedad; el acuerdo claro cuida la relación.'),
    ('rentas-seguras', 'Rentas seguras', 'Contrato, póliza jurídica y entrega del inmueble.', 6, [
        ('Conoce a tu inquilino', 'Pide identificación, comprobante de ingresos y referencias antes de apartar.'),
        ('Contrato por escrito', 'Renta, depósito, fechas, mascotas, mantenimiento y quién paga qué. Cada punto escrito evita discusiones.'),
        ('Póliza jurídica', 'Protege a tus propietarios en la renta. El servicio con RentaPóliza llegará a Ficha Única; hoy aparece como Próximamente en Servicios.'),
        ('Entrega con inventario', 'Fotos con fecha y una lista de lo que se entrega, firmada por ambas partes.'),
        ('Formatos', 'Los formatos de contrato de Ficha Única se activarán cuando un abogado los revise. Mientras tanto, usa los de tu despacho o notaría.'),
    ], 'Esto es orientación general, no asesoría legal.'),
]
BY_SLUG = {l[0]: l for l in LESSONS}


def lesson(slug):
    return BY_SLUG.get(slug)


def neighbors(slug):
    keys = [l[0] for l in LESSONS]
    i = keys.index(slug)
    return (LESSONS[i - 1] if i else None, LESSONS[i + 1] if i + 1 < len(LESSONS) else None)
