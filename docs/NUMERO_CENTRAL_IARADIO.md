# Número central de IaRadio (canal con los dueños)

Lo usa "Déjame preguntarle al dueño": cuando el bot no sabe algo, le pregunta
al dueño por este número; el dueño contesta (texto o nota de voz), el bot le
responde al cliente y se lo aprende. También saca por aquí los avisos de
pedidos, citas y errores del bot, que antes salían del número del negocio y
solo llegaban si el dueño le había escrito en las últimas 24h.

Por el mismo número el dueño usa el **Copiloto por WhatsApp**: le escribe
("¿cuántas citas tengo mañana?", "lanza la promo 2x1 a todos", "crea un cupón
de 10% para Ana") y el Copiloto lo hace con las mismas herramientas y reglas
que en el panel. Lanzar campañas, crear cupones y agendar citas siempre piden
confirmación con botones **Sí, hazlo / Cancelar**; si el dueño escribe otra
cosa en vez de confirmar, la acción se descarta.

Cómo se decide qué es cada mensaje del dueño:
1. Cita el aviso de una pregunta → es la respuesta a ese cliente.
2. "Sí"/"No" con una acción del Copiloto esperando → confirma o cancela.
3. Hay una pregunta pendiente y el mensaje la contesta (lo decide la IA) → respuesta.
4. Todo lo demás → Copiloto.

Mientras las variables de abajo estén vacías, todo funciona como antes.

## Activarlo

1. **Un número exclusivo para IaRadio** (chip nuevo o línea fija que reciba
   SMS o llamada). No puede estar en WhatsApp normal.
2. En WhatsApp Manager del portfolio "Jose Alfredo Roman Cruz", agrégalo al
   WABA de IaRadio con nombre visible **IaRadio**.
3. Crea la plantilla (Categoría **Utilidad**, idioma **Español (MEX)**):
   - Nombre: `aviso_dueno`
   - Cuerpo:
     ```
     Tienes un aviso de tu asistente de IaRadio:

     {{1}}

     Responde a este mensaje para contestar.
     ```
   - Ejemplo de {{1}}: `Un cliente de Taquería Don Pepe pregunta: ¿tienen servicio a domicilio?`
4. Token: el del usuario del sistema con la app IARadio y ese WABA asignados
   (`whatsapp_business_messaging`).
5. Suscribe la app IARadio a los webhooks de ese WABA (campo `messages`).
6. En Railway, servicio adRadio:
   - `IARADIO_WA_PHONE_NUMBER_ID` = Phone Number ID del número central
   - `IARADIO_WA_TOKEN` = el token del paso 4
   - (opcional) `IARADIO_OWNER_TEMPLATE_NAME` / `IARADIO_OWNER_TEMPLATE_LANG`
     si la plantilla no se llama `aviso_dueno` / `es_MX`.
7. Cada dueño pone su celular en **Configuración → Tu WhatsApp personal**.

## Requisito de despliegue

La tabla `owner_questions` llega con la migración `0060`. Desplegar solo
cuando Neon tenga cuota y **sin** `SKIP_MIGRATIONS` en Railway, para que la
migración corra al arrancar.

## Probarlo de punta a punta

1. Desde un celular cualquiera, pregúntale al bot de un negocio algo que no
   esté en su base de conocimiento.
2. El cliente recibe "Déjame confirmarlo…"; al celular del dueño le llega la
   pregunta desde el número de IaRadio.
3. El dueño responde (mejor citando el mensaje: mantener presionado → Responder).
4. El cliente recibe la respuesta; en Base de conocimiento aparece
   `respuestas-del-dueño`. Repetir la pregunta: ahora el bot contesta solo.
5. Copiloto: escribir "¿cuántos contactos tengo?" (responde directo) y
   "lanza la campaña X" (debe llegar con botones; "Cancelar" no lanza nada,
   "Sí, hazlo" la lanza).

## Cuenta del cliente (/mi): entrar con número + código

En iaradio.online/mi el cliente escribe su número y le llega un código por
WhatsApp desde este número central. Con el código ve todos los negocios
IaRadio donde es cliente: sellos, próxima cita y cupones, y entra al portal
de cada uno. El código solo se manda si el número es cliente de algún
negocio. Hay un límite: uno por minuto y 5 al día por número, porque Meta
cobra cada uno.

1. Crea en WhatsApp Manager la plantilla de **Autenticación**:
   - Nombre: `codigo_acceso`, idioma **Español (MEX)**.
   - Entrega del código: **Copiar código**. Marca "Agregar recomendación de
     seguridad" y vencimiento de **10 minutos**.
2. Cuando Meta la apruebe, en Railway (servicio adRadio):
   `CUSTOMER_ACCOUNT_ENABLED=true`. Mientras esté apagado, /mi dice "Muy
   pronto" y el portal no muestra el link "Todos tus negocios en un lugar".
3. (opcional) `IARADIO_OTP_TEMPLATE_NAME` / `IARADIO_OTP_TEMPLATE_LANG` si la
   plantilla se llama distinto.

## QR de mostrador (/q/{link-del-negocio})

En Configuración → **QR de mostrador**, el dueño imprime un cartel con QR.
El cliente lo escanea, escribe nombre y WhatsApp, confirma con el mismo
código de arriba (`codigo_acceso`) y entra directo a su tarjeta con el
sello de bienvenida. Queda en Contactos con origen `qr` y consentimiento
confirmado. Si ya era cliente, recupera SU tarjeta. Si se había dado de
baja de WhatsApp, sigue dado de baja.

El código es lo que impide que alguien registre el número de otra persona y
se quede con el link de su portal. Hay un tope de 200 códigos al día por
negocio, porque el cartel es público y Meta cobra cada código. Se enciende
con el mismo `CUSTOMER_ACCOUNT_ENABLED`; apagado, el QR muestra "Muy pronto".

## Descubre negocios (pestaña de /mi)

Dentro de /mi, el cliente ve otros negocios IaRadio, primero los de su
ciudad, y puede buscar. Con **"Unirme y escribir"** queda como cliente de
ese negocio (origen `directory`, con el número que ya verificó) y se le
abre el chat, gratis y sin WhatsApp. Siempre es el cliente quien da el
paso; ningún negocio le escribe a quien no se unió.

Para aparecer, el negocio necesita tener el link de su página (Widget de
chat) y no estar `churned` ni `suspended`. Cada negocio puede salirse en
Configuración → **Directorio de IaRadio**; viene encendido. Funciona con el
mismo `CUSTOMER_ACCOUNT_ENABLED` de /mi.

## Avisos al dueño de lo que llega por la web

Por este número, el dueño recibe aviso cuando un cliente le escribe por la
web con el bot pausado, y cuando llega un cliente nuevo por el QR o el
directorio. Necesita su celular en Configuración → **Tu WhatsApp
personal**. Para no saturarlo (`app/services/owner_alerts.py`):

- Un aviso por cliente cada 30 minutos; si sigue escribiendo, ese aviso lo cubre.
- Máximo 4 avisos por hora por negocio; lo que sobre se junta en el siguiente.
- Clientes nuevos agrupados: un aviso cada 2 horas como máximo, con los nombres.
- Silencio de 9 pm a 8 am (hora de México). A las 8 am llega un solo
  resumen (tarea `send_owner_morning_digests` de Celery Beat).
- Con el bot activo no hay aviso: el bot ya contestó.
