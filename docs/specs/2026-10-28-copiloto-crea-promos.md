# El Copiloto crea y manda promos (Fase 2 de campañas simples)

Fecha: 2026-10-28 · Estado: construida · Actualizado 2026-10-29: por WhatsApp **escrito** ahora
se arma con la plática de `docs/specs/2026-10-29-campana-que-pregunta-whatsapp.md`; la promo
rápida de este documento queda para las **notas de voz**.

## Qué y para quién
El dueño le dice al Copiloto (en el panel o por WhatsApp al número de IaRadio) "manda una promo
de 2x1 en fundas" y el Copiloto la arma con el catálogo real, le enseña el mensaje y a quién le
llega, y la manda cuando el dueño toca "Sí". Hoy el Copiloto solo puede lanzar campañas que ya
existen. Ver `docs/PLAN-CAMPANAS-SIMPLES.md` y `docs/specs/2026-10-28-campana-3-toques.md`.

## Decisiones del dueño
- Canal → **gratis por web**, salvo que el dueño diga "por WhatsApp" con palabras (y tenga chip);
  entonces se le dice el costo aproximado antes.
- Descuento → **solo si lo pide** ("con 15%"); el Copiloto no lo sugiere.

## Casos (cada uno lleva su prueba)
1. Si el dueño pide "manda una promo de 2x1 en fundas", entonces el Copiloto le enseña el mensaje
   armado con los precios del catálogo, a cuántos les llega y por dónde, y botones para confirmar.
   Por nota de voz: "✅ Sí, mándala" / "✏️ Cambiar" / "❌ Cancelar". — ✅ `test_caso1_*` (4), OwnerAssistant.test "a new promo shows…"
2. Si toca "Sí", entonces se crea la campaña, sale gratis por web (aviso a quien lo tiene, en el
   chat a los demás) y aparece en Campañas; no sale ningún WhatsApp. — ✅ `test_caso2_si_crea_la_campana_y_sale_gratis_por_web`, `test_caso2_el_envio_real_no_toca_whatsapp…`
3. Si pide "por WhatsApp" y NO tiene chip conectado, entonces le avisa que va solo por web y que
   conecte su chip; no sale WhatsApp. — ✅ `test_caso3_pide_whatsapp_sin_chip_va_solo_por_web`
4. Si pide "por WhatsApp" y SÍ tiene chip, entonces el resumen dice "y N por WhatsApp (Meta te
   cobra aprox $X)"; al "Sí" sale también por WhatsApp con las reglas anti-baneo de siempre. — ✅ `test_caso4_*` (5) + `TestWhatsAppGuard`
5. Si dice "con 15%", entonces cada cliente recibe su cupón de 15%; si no menciona descuento, no
   hay cupón. — ✅ `test_caso5_*` (5), incluye "2x1 no es descuento"
6. Si dice "a los que compraron", entonces va solo a quien compró en los últimos 90 días; si dice
   "a Doña Lupe", va solo a ella; si ese nombre no existe o hay varios, se lo dice y no manda nada. — ✅ `test_caso6_*` (2)
7. Si toca "Cambiar" o escribe "hazla más corta", entonces le enseña una versión nueva con
   botones otra vez; nada se manda. — ✅ `test_caso7_*` (3) + OwnerAssistant.test
8. Si toca "Cancelar" o no contesta en 5 minutos, entonces no se crea ni se manda nada. — ✅ `test_caso8_*` (3), incluye confirmar dos veces
9. Si no hay nadie a quién mandarla, entonces se lo dice con el motivo y no pone botones. — ✅ `test_caso9_nadie_a_quien_dice_por_que`
10. Si le pide lanzar una campaña que ya existe y no tiene chip, entonces la manda solo por web
    (antes intentaba WhatsApp y no salía). — ✅ `test_caso10_*` (4)
11. Si no tiene plan activo, entonces no crea nada y le dice por qué (misma regla que la web). — ✅ `test_caso11_*` (2), misma regla que REST

## Fuera de alcance
- Imagen, banner, cuña de radio, programar para otro día (siguen en la web, "Más opciones").
- Que el Copiloto sugiera descuentos o el mejor horario.
- Resultados de la campaña por el Copiloto (Fase 3).

## Riesgos y costos
- Toca dinero: WhatsApp solo si el dueño lo pide con palabras y tiene chip; pasa por la misma
  revisión de saldo, pausa de 7 días y tope de Meta. `revisor-dinero` antes de subir.
- Cada vista previa gasta una llamada de IA (cadena gratis) para armar el mensaje.
- El texto exacto que vio el dueño es el que se manda (va firmado en la confirmación).

## Plan técnico
- `backend/app/domain/campaign_actions.py`: `validate_new_campaign` (plan activo, nombre, mensaje,
  tipo, estado, segmento) compartida por REST `create_campaign` y el Copiloto.
- `backend/app/services/copilot_service.py`: herramienta `send_promo` (confirmación): vista previa
  arma mensaje con `generate_campaign_variants` + catálogo (o usa el texto que dé el dueño),
  resuelve a quién (todos / compraron / uno por nombre), alcance con `campaign_reach`; al confirmar
  crea la campaña y la lanza (web_only salvo WhatsApp pedido y conectado). `launch_campaign`
  manda solo por web sin chip y cuenta con `campaign_reach`. El resumen de `send_promo` siempre se
  muestra completo (mensaje incluido).
- `backend/app/services/copilot_whatsapp_service.py`: botón "✏️ Cambiar" para `send_promo`.
- `frontend/src/components/OwnerAssistant.tsx` y `pages/CopilotPage.tsx`: botón "Cambiar" en la
  tarjeta de `send_promo` (cierra la tarjeta y pide qué cambiar).

## Prueba real (la hace el dueño)
Ver al cerrar.

## Resultado (2026-10-28)
- Backend 1849 OK (1 saltada); frontend 260 OK; tsc y eslint limpios.
- IA real (Gemini, guion y herramientas de verdad, 8 frases × panel/WhatsApp): 16/16 tras el candado.
  Antes del candado "promo de 2x1" salió con 2% de descuento → `keep_asked_discount`. Al acortar, la IA
  una vez cambió "este viernes" por "este fin de semana" (el dueño lo ve antes de mandar).
- revisor-dinero: sin hallazgos graves; arreglados: canal firmado en launch_campaign, respetar "solo web"
  previo, WhatsApp solo si el dueño lo nombró + costo antes del mensaje, una sola campaña por vista previa.
- Pendiente (ya existía): los cupones de campaña se guardan con discount_value=0 y el agente del cliente
  puede decir "0% de descuento" (el % solo va en la descripción).
