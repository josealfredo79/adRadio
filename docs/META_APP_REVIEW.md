# Meta App Review — AdRadio (app 1346405667651723)

Material para la solicitud de acceso avanzado. Los textos van en inglés porque
son para los revisores de Meta; copiar y pegar tal cual.

Estado (2026-10-06): verificación de negocio aprobada 2026-09-22. El login de
producción volvió el 1-oct, así que ya se pueden grabar los videos. Solicitud
**sin enviar**.

**Dónde se hace ahora.** En el panel nuevo de Meta, la solicitud va dentro de
Casos de uso → "Conectarte con los clientes a través de WhatsApp" →
Personalizar → **Conviértete en socio → Conviértete en proveedor de
tecnología**. Ese flujo junta el acceso avanzado (esta revisión), la
verificación del negocio (✅) y publicar la app. Empezar por ahí, no pedir los
permisos por separado.

**La app está "Sin publicar".** Hay que publicarla (modo Live) antes de que
Meta dé acceso avanzado. Requiere los URLs de "Antes de enviar" (ya responden
200).

## Antes de enviar — Configuración → Básica

https://developers.facebook.com/apps/1346405667651723/settings/basic/

- Privacy Policy URL: `https://www.iaradio.online/privacy`
- Terms of Service URL: `https://www.iaradio.online/terms`
- User data deletion → "Data deletion instructions URL":
  `https://www.iaradio.online/data-deletion`
- Ícono de la app 1024×1024, categoría "Business and pages", correo de contacto
  `iaradio@iaradio.online`.

## Las llamadas a la API ya salen de NUESTRA app

Meta revisa que la app 1346405667651723 haya hecho llamadas reales a la API con
cada permiso. En el flujo manual cada anunciante usa el token de **su propia**
app, y esas llamadas no cuentan para la nuestra.

Esto ya está cubierto (verificado 2026-10-06): el número central de IaRadio usa
el token del usuario del sistema **adradio-api**, cuya única app asignada es
**IARadio**, con el WABA "IaRadio". Con ese token:

- `whatsapp_business_messaging`: los avisos al dueño y los códigos de `/mi`
  salen todos los días.
- `whatsapp_business_management`: `poll_meta_quality_ratings` (Celery Beat)
  lee calidad y límite del número periódicamente; al conectar se leen número y
  nombre verificado y se llama a `subscribed_apps`.

Si el contador de un permiso sale en 0 en el panel: con la cuenta IaRadio,
volver a guardar la conexión de WhatsApp en Configuración (repite las llamadas
de management) y esperar hasta 24 h.

Para los videos se puede usar el número central de IaRadio (ya conectado y en
producción) en vez de montar un WABA de prueba.

## Cuenta de prueba para los revisores

Crear en producción (cuando vuelva el login) una cuenta dedicada, p. ej.
`meta-review@iaradio.online`, con el WhatsApp de prueba ya conectado, y ponerla
en el campo de instrucciones de prueba. No usar la cuenta personal.

---

## whatsapp_business_messaging

**How will your app use this permission?**

> AdRadio (iaradio.online) is a conversational marketing platform for small
> businesses in Mexico. Each business connects its own WhatsApp Business
> Account and phone number to AdRadio. We use whatsapp_business_messaging to
> send and receive messages on behalf of that business through the WhatsApp
> Cloud API:
>
> - Reply to customers who write to the business, using an AI assistant that
>   answers from the business's own catalog, prices and opening hours. Replies
>   include text, product images, audio, and interactive reply buttons.
> - Handle appointments and orders requested by customers inside the chat.
> - Send approved message templates to contacts who opted in, for example to
>   resume a conversation after the 24-hour customer service window closes.
> - Receive incoming messages and media through our webhook and show a typing
>   indicator while the reply is generated.
>
> Messages are only sent from the business's own number, to its own customers.
> Marketing templates are only sent to contacts who opted in, and the business
> can see every conversation in the AdRadio dashboard.

**Video (1–2 min) — guion:**
1. Abrir `https://www.iaradio.online/login` e iniciar sesión con la cuenta de prueba.
2. Ir a la sección de WhatsApp y mostrar que el número está conectado.
3. Desde otro teléfono, escribirle al número del negocio ("Hola, ¿qué precios tienen?").
4. Mostrar en el teléfono la respuesta del bot (idealmente con imagen o botones).
5. Mostrar esa misma conversación dentro del dashboard de AdRadio.
6. (Opcional) Enviar una campaña/plantilla a un contacto de prueba y mostrar que llega al teléfono.

## whatsapp_business_management

**How will your app use this permission?**

> We use whatsapp_business_management to set up and monitor the WhatsApp
> Business Account that each business connects to AdRadio:
>
> - When a business connects its account, we read the phone number's display
>   number and verified name to confirm the connection is correct, and show
>   them to the business.
> - We subscribe our app to the business's WhatsApp Business Account webhooks
>   (subscribed_apps), so incoming customer messages and delivery statuses
>   reach AdRadio. This saves the business from configuring webhooks manually.
> - We periodically read the phone number's quality rating and messaging limit
>   tier and show them in a health panel, so the business can slow down
>   campaigns before its number is restricted.
> - The business creates its message templates from AdRadio (Settings >
>   WhatsApp): we submit them with POST /{waba_id}/message_templates and list
>   them with their live review status (approved, in review, rejected with
>   reason), so the owner never has to leave AdRadio.
> - We use the business's approved message templates to send reminders and
>   to resume conversations when the 24-hour window is closed.
>
> We only access the WhatsApp Business Accounts that businesses explicitly
> connect to AdRadio.

**Video (1–2 min) — guion.** Meta pide explícitamente "un único video que
muestre la creación de una plantilla de mensaje". Desde a3ff8c8 se crea en
AdRadio (Configuración → WhatsApp → "Tus plantillas de WhatsApp"):
1. Iniciar sesión en `https://www.iaradio.online/login` con la cuenta IaRadio
   (la del número central).
2. Configuración → WhatsApp: mostrar el número conectado y la lista de
   plantillas con su estado traído de Meta.
3. "Nueva plantilla": nombre `aviso_cita_demo`, tipo Utilidad, mensaje
   `Hola {{1}}, te recordamos tu cita del {{2}}. Responde si necesitas
   cambiarla.`, ejemplos `Ana` y `lunes 10:00 am` → "Enviar a revisión de Meta".
4. Mostrar que aparece "En revisión" en la lista.
5. Abrir WhatsApp Manager (business.facebook.com → Plantillas de mensajes) y
   mostrar la misma plantilla ahí, creada por la app.
6. (Si ya se aprobó) volver a AdRadio, "Actualizar" → "Aprobada", y elegirla
   en "¿Qué plantilla usar para cada aviso?".

**Video de messaging:** mostrar en pantalla dividida (o cortando entre las
dos) el Inbox de AdRadio respondiendo a una conversación y el celular o
WhatsApp Web recibiéndolo. Meta pide que se vean ambos lados.

## public_profile

Normalmente Meta lo concede por defecto y no pide video. Si pide descripción:

> Used only by Facebook Login for Business during the WhatsApp Embedded Signup
> flow, to identify the person who connects their business's WhatsApp account
> to AdRadio. We do not store or use any other profile data.

---

## Después de la aprobación (Tech Provider)

1. Poner `META_EMBEDDED_SIGNUP_ENABLED=true` en Railway y probar el botón
   "Conectar con Meta" de punta a punta con un número real. El formulario
   manual se queda como alternativa.
2. Qué hace ya el código tras el popup (2026-10-06):
   - cambia el `code` por el token del negocio;
   - si Meta no mandó el WABA o el número (sin sessionInfo, o
     `FINISH_ONLY_WABA`), los lee del token (`debug_token` → `granular_scopes`,
     luego `/{waba}/phone_numbers`); si hay cero o varios, pide repetir;
   - **registra el número en la Cloud API** (`POST /{phone}/register` con PIN
     de 6 dígitos guardado cifrado en `meta_pin_*`). Sin esto el número
     conecta pero no puede enviar. Si el número ya tenía PIN del dueño
     (error 133005) se toma como registrado. Si falla, la conexión se guarda
     con `verification_status = register_failed` y el asistente muestra el
     aviso;
   - suscribe el WABA a los webhooks.
3. Cada negocio paga a Meta directo: debe agregar su método de pago en su WABA.
   El panel de salud ya avisa cuando hay errores 131042 (pago).
4. Versión de la API: todo usa `v21.0`, que Meta mantiene hasta el
   21-ene-2027 (después sube las llamadas sola a la siguiente). Subirla antes
   de esa fecha, probándola en todas las llamadas, no solo en el signup.
5. Después: coexistencia (mismo número que el negocio ya usa en la app de
   WhatsApp Business) — otra variante del signup más los webhooks de eco; no
   construida.
