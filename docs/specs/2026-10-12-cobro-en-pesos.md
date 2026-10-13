# Cobrar en pesos (MXN) en vez de dólares

Fecha: 2026-10-12 · Estado: construida (falta prueba real con tarjeta)

## Qué y para quién
Para los negocios que pagan su plan: hoy la página dice "$449" (pesos) pero Stripe cobra US$26 (~$481 al tipo de cambio), con posible comisión de su banco por compra en el extranjero y comisión de conversión para IaRadio. Se cobra exactamente el precio anunciado, en pesos. La cuenta de Stripe ya es de México y su moneda es MXN (revisado en vivo, solo lectura, 2026-10-12).

## Decisiones del dueño
- Cobrar en pesos los mismos precios que se muestran (aprobado en el chat, 2026-10-12).

## Casos (cada uno lleva su prueba)
1. Si un negocio compra un plan al mes, Stripe le cobra exactamente el precio en pesos del plan (Arranque $449.00 MXN, Negocio $899, Crecimiento $1,799, Empresa $4,999). — prueba: `TestChargedInPesos::test_caso1_monthly_plan_is_the_advertised_price_in_pesos` (4 planes) ✅
2. Si paga al año, se le cobran 10 meses en pesos (2 meses gratis). — prueba: `test_caso2_annual_is_ten_months_in_pesos` ✅
3. Si entra como Fundador, se le cobra el precio de Fundador en pesos ($319 / $629). — prueba: `test_caso3_founder_price_in_pesos` ✅
4. Los paquetes extra se cobran en pesos ($149 / $99). — prueba: `test_caso4_addons_in_pesos` ✅
5. El premio por referido se abona en la misma moneda en que pagó el cliente (si no, Stripe lo rechaza por mezclar monedas). — prueba: `test_caso5_referral_credit_uses_the_payment_currency` ✅

## Fuera de alcance
- Cambiar precios.
- Suscripciones existentes en dólares: no hay ninguna (0 en Stripe al 2026-10-12).
- El "≈ US$" informativo de la página de inicio.

## Riesgos y costos
- Toca cobros reales: sin migraciones; la prueba real es con la tarjeta del dueño en CityCell y reembolso después.

## Plan técnico
- `backend/app/api/v1/payments.py`: `currency: "mxn"`, `unit_amount = price_mxn * 100` en plan, anual, Fundador y paquetes.
- `backend/app/api/v1/webhooks_pkg/stripe.py`: el abono por referido usa la moneda del pago.
- `backend/app/core/plans.py`: comentario de qué se cobra.

## Prueba real (la hace el dueño)
1. Cuenta CityCell → Planes → Arranque al mes → pagar con su tarjeta.
2. La página de Stripe debe decir **$449.00 MXN**.
3. Al volver, CityCell debe estar en plan Arranque, activo.
4. En Stripe: cancelar la suscripción y reembolsar el pago.
