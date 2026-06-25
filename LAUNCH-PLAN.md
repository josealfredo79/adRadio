# 🚀 Plan de Lanzamiento IaRadio

## Estado actual (16 Jun 2026)

### ✅ Terminado
- Stripe webhook configurado y funcionando
- Bug link "Ver planes" corregido y en producción
- "Multi-agente IA" eliminado del plan Business
- Sentry configurado + desplegado en Railway
- Links a Términos/Privacidad arreglados en registro
- Dominio `iaradio.online` apuntando a Railway (pendiente SSL)
- Número `+525599631448` activo en Twilio
- Número `+525671254039` pendiente de verificación Meta

### 🔴 Pendiente técnico (mañana)
- [x] Stripe live keys (`sk_live_...`, `pk_live_...`)
- [x] Stripe webhook en modo producción (Verificado: `STRIPE_WEBHOOK_SECRET` configurado)
- [ ] Meta verifica `+525671254039`
- [ ] Agregar `TWILIO_NUMBER_POOL=+525671254039,+525599631448` en Railway
- [x] SSL bare domain se activa solo (Verificado: HTTPS funcional)

---

## Estrategia: Dogfooding + Google Maps

### Día 1–2: Assets (ayuda del dev)
- [ ] Crear PDF FAQ IaRadio → subir como base de conocimiento
- [ ] Generar 3 cuñas de radio con la plataforma
- [ ] Generar 1 flyer promocional con IA

### Día 3–4: Pitching Google Maps
- [ ] Extraer 200+ negocios locales (Tlaxiaco, Oaxaca)
- [ ] Importar CSV a Contactos en IaRadio
- [ ] Etiquetar: `posible-cliente`, `tlaxiaco`
- [ ] Campaña secuencia (3 mensajes en 5 días):
  1. Cuña presentación + "Responde QUIERO"
  2. Caso de uso: restaurante +40% pedidos
  3. Cupón QR: 50% desc. primer mes

### Día 5–7: Onboarding presencial
- [ ] Leads calificados → Bot agenda cita o visita personal
- [ ] Configurar en 10 min
- [ ] Primer mes gratis → recurrente

### Alternativas futuras
- Nicho Oaxaca (venta directa a negocios locales)
- Agencias de marketing (white-label)
- TikTok (cuñas virales)
- Trueque con radios comunitarias

---

## KPIs primera semana
| Métrica | Meta |
|---------|------|
| Contactos extraídos | 200+ |
| Conversaciones iniciadas | 50+ |
| Registros | 10–15 |
| Pagos recurrentes | 3–5 ($87–$145 USD/mes) |

**Costo total:** ~$2 USD (Twilio) + 2.9% Stripe
