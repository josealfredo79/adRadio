# Planes de IaRadio (rediseño 2026-10-01)

Fuente de verdad en código: `backend/app/core/plans.py` (y su espejo `frontend/src/lib/plans.ts`).

## Por qué se rediseñaron

1. **Seis planes eran demasiados** para una pyme, y Micro/Starter casi no se distinguían.
2. **El "mensaje" que se vendía confundía:** solo contaba campañas; las respuestas del bot eran ilimitadas; y no se decía que **Meta cobra aparte** (desde el 1-oct-2026 también cada respuesta del bot).
3. **Costo sin tope para IaRadio:** cada respuesta del bot llama a la IA y la pagamos nosotros.
4. **El portal y las notificaciones web cuestan ~$0** y le ahorran dinero al negocio con Meta → deben ser ilimitados en todos los planes: es el argumento de venta.
5. **Precios "de referencia" tachados** ($1,500 → $499, "Ahorra 67%") eran descuentos que nunca existieron. Riesgo con PROFECO y con la confianza. Se quitaron.

Al momento del cambio había 5 cuentas en prueba y ningún cliente pagando, así que no hubo que migrar a nadie.

## Los planes

| | **Arranque** | **Negocio** ⭐ | **Crecimiento** | **Empresa** |
|---|---|---|---|---|
| Clave interna | `starter` | `growth` | `pro` | `enterprise` |
| Precio mensual | $449 MXN | $899 MXN | $1,799 MXN | desde $4,999 MXN (cotización) |
| Anual | 12 meses al precio de 10 | ← | ← | a medida |
| Conversaciones del bot / mes | 300 | 1,000 | 3,000 | a medida |
| Envíos de campaña por WhatsApp / mes | 150 | 500 | 1,500 | 5,000+ |
| Portal del cliente + notificaciones web | ilimitado | ilimitado | ilimitado | ilimitado |
| Citas, pedidos, cupones | ✓ | ✓ | ✓ | ✓ |
| Bot con catálogo e información (RAG) | — (instrucciones) | ✓ | ✓ | ✓ |
| Banners y flyers con IA | — | ✓ | ✓ | ✓ |
| Cuñas de radio con IA / mes | — | 4 | 15 | sin límite |
| Automatizaciones | — | ✓ | ✓ | ✓ |
| Secuencias, sagas, A/B, API | — | — | ✓ | ✓ |
| White-label | — | — | — | ✓ |
| Usuarios | 1 | 2 | 5 | sin límite |

`micro` y `business` se retiraron de la venta; siguen en el código para quien ya los tuviera.

**Prueba gratis:** 15 días (`TRIAL_DAYS`), con los límites de Arranque + 3 cuñas de radio. Antes eran 30 días en el backend y 15 en la landing; se dejó en 15 para no cargar 30 días de costo de IA sin ingreso.

**Fundadores:** 25 lugares, ~30% menos en Arranque ($319) y Negocio ($629), precio bloqueado 12 meses.

## Qué cuenta cada cuota

- **Conversación del bot:** un cliente atendido por la IA dentro de una ventana de 24 h (como Meta cuenta las suyas), sin importar cuántos mensajes. Solo cuenta cuando de verdad se llama a la IA; los flujos automáticos de citas, pedidos y catálogo no gastan IA y no cuentan. Canales: WhatsApp y chat web (portal/widget).
- **Envío de campaña:** lo que inicia el negocio por WhatsApp (campañas, parrilla, automatizaciones, plantillas de reapertura). Las campañas que salen por notificación web **no gastan envíos**.

## Al llegar al límite: nunca se apaga nada

- Aviso por correo al **80 %** y al **100 %** (una vez cada uno por mes).
- Pasado el límite, el bot **sigue contestando** con un modelo de IA más económico (OpenRouter primero, Groq de respaldo). Un bot que se apaga le cuesta una venta al negocio; uno que contesta un poco más simple, no.
- Las notificaciones web siguen funcionando, y las campañas a clientes con notificaciones salen aunque se acabe el saldo de WhatsApp.

## Paquetes extra (pago único)

| Paquete | Precio | Detalle |
|---|---|---|
| +500 conversaciones del bot | $149 MXN | No vencen; se usan cuando se acaba lo del plan |
| +500 envíos de campaña | $99 MXN | Se suman al saldo actual |

Se compran desde **Planes** en el dashboard (Stripe, pago único) y se acreditan en el webhook.

## Meta, dicho claro

"Los cargos de WhatsApp los cobra Meta directo en tu cuenta. IaRadio te ayuda a pagar menos: tus clientes reciben recordatorios y promociones gratis por la app de tu negocio." — aparece en la landing y en Planes.

## Sostenibilidad (estimado, uso al 100 %)

Supuestos: ~18.5 MXN/USD; ~$0.19 MXN por conversación del bot (≈4 respuestas); ~$0.13 MXN por envío de campaña con audio y banner; infraestructura ~$2,000–2,800 MXN/mes; Stripe ~3.6 % + $3.

| | Arranque | Negocio | Crecimiento |
|---|---|---|---|
| Ingreso | $449 | $899 | $1,799 |
| IA del bot | $56 | $185 | $555 |
| Campañas | $13 | $65 | $205 |
| Infra (parte) | $40 | $40 | $60 |
| Stripe | $19 | $35 | $68 |
| **Margen** | **~71 %** | **~64 %** | **~51 %** |

Con uso típico (30–50 % del límite) los márgenes suben a 75–85 %. Unos 4 clientes en Negocio cubren la infraestructura.

**Validar con datos reales:** costo real por conversación (tokens de Groq/OpenRouter), uso real por plan, y tipo de cambio al fijar `price_usd` en Stripe.
