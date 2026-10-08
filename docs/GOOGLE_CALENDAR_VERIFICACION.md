# Verificación de Google Calendar (pasar de "Prueba" a "En producción")

**Por qué:** mientras la app de Google esté en modo **Prueba**, solo pueden conectar
su calendario los correos agregados como "usuarios de prueba", y su conexión
**caduca a los 7 días**. Para que cualquier negocio conecte Google Calendar y no se
desconecte, la app debe estar **En producción** y **verificada** por Google, porque
pedimos un permiso "sensible": `https://www.googleapis.com/auth/calendar.events`.

Qué hace IaRadio con ese permiso: crea, actualiza y borra en el Google Calendar del
dueño las citas que sus clientes agendan, cambian o cancelan en IaRadio. No lee sus
otros eventos.

## Datos que Google te va a pedir

| Campo | Valor |
|---|---|
| Nombre de la app | IaRadio |
| Correo de soporte | iaradio@iaradio.online |
| Página principal | https://www.iaradio.online |
| Política de privacidad | https://www.iaradio.online/privacy (sección **4.1 Google Calendar**) |
| Términos | https://www.iaradio.online/terms |
| Dominio autorizado | iaradio.online |
| URI de redirección | https://www.iaradio.online/api/v1/appointments/google/callback |
| Permiso (scope) | `.../auth/calendar.events` |
| Logo | 120×120 px, el mismo de IaRadio |

## Pasos (Google Cloud Console)

1. Entra a **console.cloud.google.com** con la cuenta dueña del proyecto donde está el
   `GOOGLE_CALENDAR_CLIENT_ID` (el que está en Railway).
2. **Verifica el dominio** `iaradio.online` en **Google Search Console**
   (search.google.com/search-console), con la misma cuenta de Google. Si ya está, sigue.
3. En **APIs y servicios → Pantalla de consentimiento de OAuth** (en la consola nueva:
   **Google Auth Platform → Branding**):
   - Llena nombre, correo de soporte, logo, página principal, privacidad y términos
     con los datos de la tabla.
   - En **Dominios autorizados** pon `iaradio.online`.
4. En **Data Access / Permisos**: confirma que solo esté `calendar.events`.
5. En **Audience / Público**: tipo **Externo** → botón **Publicar app** (pasa a
   "En producción").
6. Google pedirá la **verificación** por el permiso sensible. Llena el formulario con
   los textos de abajo y sube el video.
7. Espera: de unos días a unas semanas. Google responde por correo; si piden
   cambios, contesta en el mismo hilo.

## Textos para el formulario (en inglés, como los revisa Google)

**Scope justification — calendar.events**

> IaRadio is a booking and customer-service assistant for small businesses in Mexico.
> When a business owner connects their Google Calendar, IaRadio uses the
> calendar.events scope only to create, update and delete events for the
> appointments their customers book, reschedule or cancel through IaRadio (web chat
> and WhatsApp). This keeps the owner's calendar in sync without manual work. We do
> not read, list or analyze the owner's other events, we do not share or sell
> calendar data, and we do not use it for advertising or to train AI models. A
> narrower scope is not enough because we need to write and later edit or delete
> the events we create.

**How will the scopes be used? (resumen corto)**

> Create/update/delete calendar events for appointments booked in IaRadio, in the
> connected owner's own calendar.

## Video de demostración (YouTube, "No listado")

Google pide un video que muestre la pantalla de consentimiento y el uso del permiso.
Guion de 1–2 minutos (con subtítulos en inglés, como los de Meta):

1. Muestra la barra de direcciones en **www.iaradio.online** e inicia sesión en el panel.
2. Ve a **Citas → Conectar Google Calendar**.
3. Se abre la pantalla de Google: que se vea el **nombre "IaRadio"** y el permiso
   pedido. Acepta.
4. De vuelta en IaRadio, muestra que dice **conectado**.
5. Desde el chat web del negocio (como cliente), **agenda una cita**.
6. Abre **Google Calendar** y muestra el **evento creado** con la cita.
7. Cancela la cita en IaRadio y muestra que **el evento desaparece** del calendario.
8. Muestra **Desconectar Google** en el panel.

## Al aprobarse

- Prueba con un negocio real que conecte su calendario y agende una cita.
- Los negocios que conectaron en modo Prueba quizá tengan que **volver a conectar**
  (sus permisos caducaron a los 7 días).

## Pendiente conocido (no bloquea la verificación)

Lo que el dueño anota **directo en Google Calendar** no bloquea horarios en IaRadio:
la sincronización va solo de IaRadio hacia Google. Leer su disponibilidad requeriría
otro permiso (`calendar.freebusy` o `calendar.readonly`) y una nueva revisión.
