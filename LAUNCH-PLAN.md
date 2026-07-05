# Plan de Lanzamiento IaRadio

## Estado actual (4 Jul 2026)

### Listo para produccion
- Plataforma completa desplegada en Railway
- Dominio `www.iaradio.online` activo con SSL
- Bot WhatsApp (numero compartido + pool) funcionando
- Bot demo en landing page funcionando
- Pagos Stripe live keys activas
- Panel admin desplegado y verificado (admin@iaradio.app)
- Base de datos Neon PostgreSQL funcionando
- Sentry monitoreo de errores configurado
- Fallback para mensajes sin anunciante implementado
- Health check funcional

### Pendientes tecnicos
- [ ] Verificar numero `+525671254039` en Meta
- [ ] Configurar `TWILIO_NUMBER_POOL=+525671254039,+525599631448` en Railway
- [x] Respaldo automatico BD (Neon -> S3) - pg_dump diario (commit c594807)
- [ ] Monitoreo uptime (Better Uptime)
- [x] Reemplazar `og-image.png` con diseno real (1200x630px)
- [x] Documentar procedimiento de rollback (ROLLBACK.md creado)

---

## Semana 1: Dogfooding (dias 1-3)

### Dia 1: Assets internos
- [x] Crear PDF FAQ IaRadio -> subir como base de conocimiento del bot
- [ ] Generar 3 cuenas de radio con la plataforma
- [x] Crear flyer promocional

### Dia 2-3: Probar flujo completo
- [ ] Registrarse como anunciante trial
- [ ] Subir base de conocimiento
- [ ] Crear campana y enviarla
- [ ] Recibir respuesta del bot
- [ ] Canjear cupon
- [ ] Verificar panel admin con datos reales

---

## Semana 2: Primeros clientes (dias 4-10)

### Dia 4-5: Google Maps Tlaxiaco
- [x] Extraer 200+ negocios locales (CSV con 104 negocios creados)
- [x] Importar CSV a Contactos (listo para importar desde el panel)
- [x] Etiquetar: `posible-cliente`, `tlaxiaco` (etiquetas incluidas en CSV)
- [x] Campana secuencia (3 mensajes en 5 dias):
  1. Cuena presentacion + "Responde QUIERO"
  2. Caso de uso: restaurante +40% pedidos
  3. Cupon QR: 50% desc. primer mes

### Dia 6-7: Onboarding presencial
- [ ] Leads calificados -> Bot agenda cita o visita personal
- [ ] Configurar en 10 min
- [ ] Primer mes gratis -> recurrente

### Dia 8-10: Seguimiento
- [ ] Follow up a leads que no respondieron
- [ ] Recopilar feedback de primeros usuarios
- [ ] Ajustar pitch segun objeciones

---

## KPIs primera semana

| Metrica | Meta |
|---------|------|
| Negocios contactados | 200+ |
| Conversaciones iniciadas | 50+ |
| Registros nuevos | 10-15 |
| Pagos recurrentes | 3-5 ($87-$145 USD/mes) |

---

## Costos estimados

| Servicio | Costo |
|----------|-------|
| Twilio (200 mensajes) | ~$2 USD |
| Stripe fee | 2.9% |
| Railway | $5 USD/mes |
| Neon | Free tier |
| **Total primer mes** | **~$10 USD** |

---

## Estrategia futura

- Nicho Oaxaca (venta directa a negocios locales)
- Agencias de marketing (white-label)
- TikTok (cuenas virales)
- Trueque con radios comunitarias
