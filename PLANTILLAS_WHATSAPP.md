# Plantillas WhatsApp Aprobadas - Twilio

## UTILITY — notificacion_audio_v2 ✅ Aprobada
- **SID:** `HXd5f54a4479517e056e3dc216f95d1067`
- **Categoría:** Utility
- **Estado:** Approved
- **Body:** `Hola {{1}}, tienes un mensaje de audio de {{2}} en espera. Escúchalo presionando {{3}} cuando puedas.`
- **Variables:** `{{1}}` = nombre contacto, `{{2}}` = negocio, `{{3}}` = "aquí"
- **Uso:** Reabrir ventana 24h antes de campañas (puede enviarse fuera de ventana)

## MARKETING — notificacion_informativa ⏳ Under Review
- **SID:** `HX5dc3c07019d22ed5b128df45d2ed1b15`
- **Categoría:** Marketing
- **Estado:** Under Review (al 7/6/2026)
- **Body:** `Hola {{1}}, {{2}} tiene novedades para ti. ¿En qué podemos ayudarte el día de hoy?`
- **Variables:** `{{1}}` = nombre contacto, `{{2}}` = negocio
- **Uso:** Fallback para reabrir ventana 24h cuando la UTILITY falla (solo funciona si ventana ya está abierta)
