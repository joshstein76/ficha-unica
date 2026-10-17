# Mercado Libre México: registrar la app (para Josh / Phil, más adelante)

Estado 2026-10-17: **nada registrado**. El MVP corre en modo prueba (`connect_demo` + outbox `dry_run`). Cada agente conectará después SU propia cuenta de Mercado Libre; la app es una sola.

## Quién registra
- La cuenta de Mercado Libre de **Ficha Única**, propiedad de **Ciao Bella Marketing** (no una cuenta personal). Confirmar quién tiene el acceso (Josh o Phil).
- Portal de desarrolladores: developers.mercadolibre.com.mx (confirmar URL y flujo actual).

## Pasos
1. Entrar a developers.mercadolibre.com.mx con la cuenta de Ficha Única y crear una aplicación nueva.
2. **Redirect URI**: la URL pública exacta del callback, `https://app.<dominio-de-marca>/oauth/mercadolibre/callback` (confirmar si exige HTTPS y coincidencia exacta). En local el valor por defecto es `http://app.fichaunica.localhost:8640/oauth/mercadolibre/callback`; confirmar si ML acepta localhost para pruebas.
3. **Permisos / scopes**: `offline_access` (para refresh token) + lectura y escritura (confirmar los nombres exactos en el panel).
4. Activar PKCE si la app lo ofrece como opción (confirmar).
5. Copiar Client ID y Client Secret. Guardarlos solo como variables de entorno en el servidor (`ML_CLIENT_ID`, `ML_CLIENT_SECRET`, opcional `ML_REDIRECT_URI`). Nunca en el repo, chat ni logs.
6. Crear **usuarios de prueba** (test users) desde la API/panel de ML (confirmar) y probar con ellos antes de cualquier cuenta real.
7. Verificar endpoints en la documentación vigente (constantes en `llave/ml_oauth.py`): autorización `https://auth.mercadolibre.com.mx/authorization`, token `https://api.mercadolibre.com/oauth/token` (confirmar ambos).

## Qué revisar antes de publicar de verdad
- **Costos de publicación de inmuebles** por categoría y plan (venta / renta); confirmar si hay tarifa por anuncio, por comisión o paquetes para inmobiliarias.
- **listing_type_id**: hoy el código usa `silver` como placeholder. Elegir el correcto según la cuenta del agente (confirmar valores permitidos para inmuebles).
- **Categorías hoja** bajo `MLM1459` (Inmuebles): el código solo conoce departamento, casa y bodega; el resto cae en la categoría padre y ML lo rechazará. Consultar `/categories/MLM1459` y mapear terreno, oficina, local, y renta vs venta (confirmar).
- Atributos obligatorios por categoría, límites de fotos y reglas de título (confirmar).
- Dónde guardar tokens en producción: vault (Supabase Vault), no columnas planas como en el MVP.

## Encender el modo real
**No activar `LLAVE_ML_LIVE=1` sin el sí explícito de Josh.** Con la variable apagada, aunque existan las credenciales, el código no hace ninguna llamada de red: el conectar muestra "Conexión real desactivada" y publicar escribe al outbox como prueba.
