# Meta App Review — AdRadio (app 1346405667651723)

Material para la solicitud de acceso avanzado. Los textos van en inglés porque
son para los revisores de Meta; copiar y pegar tal cual.

Estado (2026-09-24): verificación de negocio aprobada 2026-09-22. Solicitud
armada con `whatsapp_business_messaging`, `whatsapp_business_management` y
`public_profile`, **sin enviar** — falta grabar los videos, bloqueados porque el
login de producción está caído por la cuota de Neon (se reinicia ~1-oct).

## Antes de enviar — Configuración → Básica

https://developers.facebook.com/apps/1346405667651723/settings/basic/

- Privacy Policy URL: `https://www.iaradio.online/privacy`
- Terms of Service URL: `https://www.iaradio.online/terms`
- User data deletion → "Data deletion instructions URL":
  `https://www.iaradio.online/data-deletion`
- Ícono de la app 1024×1024, categoría "Business and pages", correo de contacto
  `iaradio@iaradio.online`.

## Importante: el token tiene que salir de NUESTRA app

Meta revisa que la app 1346405667651723 haya hecho llamadas reales a la API con
cada permiso. En el flujo manual cada anunciante usa el token de **su propia**
app de Meta, y esas llamadas no cuentan para la nuestra. Para la demo y los
videos:

1. En business.facebook.com → Usuarios del sistema, crear (o usar) un usuario
   del sistema del portfolio "Jose Alfredo Roman Cruz" y asignarle la app
   **1346405667651723** y el WABA de prueba.
2. Generar el token **con esa app seleccionada**, con los permisos
   `whatsapp_business_messaging` y `whatsapp_business_management`. El acceso
   estándar alcanza porque el WABA es del mismo portfolio.
3. Conectar ese WABA en la cuenta de prueba de AdRadio usando ese token, y
   mandar y recibir algunos mensajes antes de enviar la solicitud.

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
> - We use the names of the business's approved message templates to send
>   them when the 24-hour window is closed.
>
> We only access the WhatsApp Business Accounts that businesses explicitly
> connect to AdRadio.

**Video (1–2 min) — guion:**
1. Iniciar sesión con la cuenta de prueba.
2. Abrir el asistente de conexión de WhatsApp, llenar WABA ID, Phone Number ID y token, y guardar.
3. Mostrar que AdRadio confirma el número y el nombre verificado, y que los webhooks quedan configurados solos.
4. Mostrar el panel de salud del número (calidad y límite de mensajes).
5. Mostrar dónde se eligen las plantillas aprobadas.

> Ojo: antes de grabar, abrir el link **"Normas de uso"** de cada permiso en la
> solicitud — ahí Meta dice exactamente qué debe verse en el video. Si para
> `whatsapp_business_management` pide mostrar la *creación* de una plantilla,
> AdRadio hoy no crea plantillas (solo usa las ya aprobadas): avisarme antes de
> grabar para decidir si se agrega o se muestra el flujo actual.

## public_profile

Normalmente Meta lo concede por defecto y no pide video. Si pide descripción:

> Used only by Facebook Login for Business during the WhatsApp Embedded Signup
> flow, to identify the person who connects their business's WhatsApp account
> to AdRadio. We do not store or use any other profile data.

---

## Después de la aprobación

1. Completar el alta como Tech Provider:
   https://developers.facebook.com/docs/whatsapp/solution-providers/get-started-for-tech-providers
2. Poner `META_EMBEDDED_SIGNUP_ENABLED=true` en Railway y probar el botón
   "Conectar con Meta" de punta a punta con un número real. El formulario
   manual se queda como alternativa.
