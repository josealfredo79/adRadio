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
