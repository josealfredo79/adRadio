# Meta sin fricción (WhatsApp como mejora, no requisito)

Fecha: 2026-10-17 · Estado: construida

## Qué y para quién
Conectar con Meta tiene pasos y requisitos (Facebook, número libre, tarjeta) que no podemos quitar. Para el dueño
del negocio dejamos de presentarlo como obligatorio: su bot atiende desde el día 1 en su página y su QR, y Meta se
ofrece como mejora cuando ya vio clientes reales. La guía técnica (Meta for Developers, tokens, IDs) deja de verla
quien no es admin.

## Decisiones del dueño
- Sin botón de Meta (mientras siga solo para admins) → aviso + "Pide ayuda", que te llega al Inbox de IaRadio.
- Cuándo ofrecer la mejora en el panel → con 5 clientes por la web en el mes.
- Pregunta frecuente de la landing → ajustarla.

## Casos (cada uno lleva su prueba)
1. Si un dueño normal sin botón de Meta abre Configuración → WhatsApp, entonces ve "tu bot ya atiende en tu página y
   tu QR" y un botón "Quiero conectar mi WhatsApp", y NO ve la guía manual ni los campos de token/IDs. — prueba: `caso 1: an owner without the button…` (WhatsappWizard.embedded.test.tsx) ✅
2. Si toca "Quiero conectar mi WhatsApp", entonces en el Inbox de la cuenta IaRadio aparece una plática con su
   negocio (nombre y teléfono), con el bot pausado, y él ve "Listo, te escribimos pronto". — prueba: `test_caso2_help_request_lands_in_iaradio_inbox_with_bot_paused`, `test_caso2_help_endpoint_saves_the_request`, `caso 2: tapping help…` ✅
3. Si lo toca otra vez el mismo día, entonces no se duplica la plática ni el mensaje. — prueba: `test_caso3_second_tap_same_day_does_not_duplicate` ✅
4. Si es admin, entonces sigue viendo el botón de Meta y la guía manual (escondida en "Conectar a mano (avanzado)"). — prueba: `caso 4: an admin keeps the manual connection…` ✅
5. Si el dueño sí tiene el botón de Meta, entonces antes del botón ve "Ten a la mano: tu Facebook, tu celular con el
   número y una tarjeta", y el aviso de cobro dice la verdad: las primeras 1,000 respuestas del mes son gratis, después
   Meta cobra unos $0.16 por respuesta y las promociones aparte (las cifras salen del servidor). — prueba: `sin fricción caso 5…`, `caso 5: an owner with the button…`, `test_caso5_config_tells_the_real_meta_pricing` ✅
6. Si un negocio sin WhatsApp conectado tiene 5 o más clientes por la web este mes, entonces el panel principal le
   muestra "Ya atendiste N clientes por tu página. ¿Quieres que el bot conteste también en tu WhatsApp?", que lleva a
   Configuración → WhatsApp; puede cerrarla. — prueba: `caso 6: …` (WhatsappUpgradeCard.test.tsx, 2 pruebas) ✅
7. Si ya tiene WhatsApp conectado, o tiene menos de 5 clientes por la web, o es la cuenta del número central,
   entonces no ve esa tarjeta. — prueba: `caso 7: …` (2 pruebas) ✅
8. La pregunta frecuente de la landing dice que arrancas sin conectar nada y que conectas tu número cuando quieras. — prueba: `caso 8: says you start without connecting anything` ✅

## Fuera de alcance
- Encender el botón para todos (META_EMBEDDED_SIGNUP_ADMINS_ONLY=false): va después de la prueba con chip nuevo.
- Coexistencia como camino por defecto (falta suscribir webhooks y probar).
- Pagarle a Meta por el cliente (requiere ser Solution Partner).

## Riesgos y costos
- Ningún mensaje de Meta nuevo: el aviso de ayuda solo se guarda en el Inbox de IaRadio, no se manda por WhatsApp.
- Solo web (no toca workers).

## Plan técnico
- `backend/app/api/v1/meta_whatsapp.py`: embedded-config agrega precios (gratis/mes y precio MXN);
  `POST /me/whatsapp-connection/help` guarda la petición en el Inbox de la cuenta del número central.
- `backend/app/services/meta_help_request.py`: contacto + plática pausada + mensaje, sin duplicar en el día.
- `frontend/src/components/WhatsappWizard.tsx`: aviso + ayuda para no-admins sin botón; "ten a la mano"; texto de cobro;
  guía manual solo admins.
- `frontend/src/pages/DashboardPage.tsx`: tarjeta de mejora con 5+ clientes por web.
- `frontend/src/pages/landing/components/FaqSection.tsx`: texto.

## Prueba real (la hace el dueño)
1. Necesitas una cuenta que NO sea admin ni esté en META_EMBEDDED_SIGNUP_TEST_EMAILS (CityCell sí está, así que
   ve el botón de Meta). Por ejemplo la cuenta de prueba "Movimiento" o un alta nueva desde la landing.
2. En esa cuenta: Configuración → "Tu WhatsApp". Debe decir que tu bot ya atiende en tu página y tu QR, y mostrar
   "Quiero conectar mi WhatsApp" — sin guía de Meta for Developers ni campos de token.
3. Tócalo: debe decir "Listo, te escribimos pronto". (Si dice que falta tu WhatsApp personal, llénalo arriba en Datos
   del negocio.)
4. Entra con la cuenta IaRadio (tecnologicotlaxiaco@) → Inbox: aparece ese negocio con "Quiero conectar mi WhatsApp
   (pedido desde el panel)" y el bot pausado.
5. Con CityCell (que sí tiene botón): Configuración → "Tu WhatsApp" muestra "Antes de empezar ten a la mano" y el
   aviso de 1,000 respuestas gratis.
