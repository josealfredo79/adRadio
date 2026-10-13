# Encender "Conectar con Meta" (Embedded Signup)

Fecha: 2026-10-12 · Estado: construida (falta encender en Railway y prueba real)

## Qué y para quién
Meta aprobó la App Review (2026-10-11: whatsapp_business_messaging, whatsapp_business_management, public_profile). Ahora un negocio puede conectar su número de WhatsApp con un botón, sin copiar tokens ni IDs. El código ya existe (a775345) y está apagado; esto lo enciende con cuidado: primero solo admins, prueba real, y luego todos.

## Decisiones del dueño
- Alcance → solo números nuevos (que no estén en la app de WhatsApp Business). Coexistencia va en su propia especificación.
- Quién lo ve primero → solo admins; cuando la prueba real salga bien, todos.
- Cobro de Meta → aviso claro antes del botón.
- Número para la prueba → el que consiga el dueño; si no hay, se prueba hasta donde se pueda.

## Casos (cada uno lleva su prueba)
1. Si el interruptor está apagado, nadie ve el botón "Conectar con Meta" (ni admins). — prueba: `TestEmbeddedRollout::test_caso1_switch_off_hides_it_even_from_admins`, `WhatsappWizard.embedded` «casos 1 y 2» ✅
2. Si está encendido en modo "solo admins", un admin ve el botón y un negocio normal no (sigue viendo el formulario manual). — prueba: `test_caso2_admins_only_mode` ✅
3. Si está encendido para todos, cualquier negocio ve el botón. — prueba: `test_caso3_everyone_mode` ✅
4. Aunque alguien llame directo al servidor, un negocio que no debe ver el botón no puede conectar por ahí. — prueba: `test_caso4_server_refuses_connection_when_not_enabled_for_user` ✅
5. Antes del botón el negocio lee: Meta puede pedirle una tarjeta en su cuenta; contestar a sus clientes es gratis y los mensajes de promoción los cobra Meta. — prueba: `WhatsappWizard.embedded` «caso 5» ✅ (también avisa que el número no debe estar en la app de WhatsApp)
6. Si el negocio vuelve a conectar el MISMO número, no se reinicia su rampa de envíos (anti-baneo); si conecta un número distinto, sí. Igual que el formulario manual. — prueba: `test_caso6_same_number_keeps_the_anti_ban_ramp`, `test_caso6_new_number_restarts_the_ramp` ✅
7. Si el negocio tenía conectada su propia app de Meta (formulario manual) y ahora conecta con el botón, se olvidan los datos de su app vieja para que no se mezclen. — prueba: `test_caso7_old_own_app_is_forgotten` ✅
8. Conectar con éxito deja el número registrado, el token cifrado y el webhook suscrito; si Meta falla o el negocio cancela, ve un mensaje claro y el formulario manual sigue ahí. — pruebas existentes: `TestEmbeddedSignup` ✅

Pruebas: backend 1555 ✅ (`tests/test_meta_whatsapp_endpoints.py`), frontend 195 ✅. De paso: arreglada una carrera en LearnCard (campos vacíos en el primer pintado).

## Fuera de alcance
- Coexistencia (mismo número de la app de WhatsApp Business).
- Números comprados por IaRadio para los negocios.
- Cambiar el formulario manual.

## Riesgos y costos
- Producción sin staging: por eso "solo admins" primero.
- Cambio de configuración en Railway (variables), no de base de datos. Sin migraciones ni cambios en workers.
- La App de Meta debe estar publicada (modo Live) para que negocios de afuera puedan usar el botón.

## Plan técnico
- `backend/app/config.py`: `META_EMBEDDED_SIGNUP_ADMINS_ONLY: bool = True` (seguro por defecto).
- `backend/app/api/v1/meta_whatsapp.py`: `_embedded_enabled_for(user)` usado por `/me/whatsapp-embedded-config` y como candado en `/me/whatsapp-connection/embedded` (403 si no aplica); `meta_connected_at` solo si cambia el número; limpiar `meta_app_id` y su App Secret al conectar por el botón.
- `frontend/src/components/WhatsappWizard.tsx`: aviso de cobro de Meta arriba del botón.
- Railway (adRadio): `META_EMBEDDED_SIGNUP_ENABLED=true` (con ADMINS_ONLY por defecto). Tras la prueba real: `META_EMBEDDED_SIGNUP_ADMINS_ONLY=false`.

## Pendientes fuera del código (dueño)
- Confirmar que la App esté publicada (Live) y revisar "Acciones requeridas" en Meta.
- Cambiar la contraseña de iaradio@iaradio.online (salió en una captura; ya terminó la revisión).

## Prueba real (la hace el dueño)
1. Panel (eres admin) → Configuración → WhatsApp: debe salir "Conectar con Meta" con el aviso de cobro.
2. Con una cuenta de prueba que NO sea admin (o en otra ventana), no debe salir el botón.
3. Con un número nuevo: tocar el botón, seguir la ventana de Meta (elegir o crear la cuenta de WhatsApp Business, agregar el número, poner el código que llega por SMS).
4. Al terminar, la tarjeta debe decir "Conectado" con el número.
5. Desde otro teléfono escribirle a ese número: el bot debe contestar y la plática salir en el Inbox.
