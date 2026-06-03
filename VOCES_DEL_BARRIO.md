# Voces del Barrio — Análisis de Factibilidad

## Concepto

Convertir IaRadio en una plataforma de **pertenencia local**, no solo de campañas.

> "Convierte las historias de tus clientes en campañas que venden sin sentirse como publicidad."

Los negocios recolectan audios reales de clientes por WhatsApp. IaRadio los transcribe, genera una cápsula narrativa con IA y la convierte en audio tipo radio que se envía de vuelta a la comunidad.

---

## Infraestructura existente que aplica directamente

| Componente necesario | Estado | Archivo |
|---|---|---|
| Recibir audios de clientes por WhatsApp | ✅ Funcional | `backend/app/api/v1/webhooks.py` L99–109 |
| Transcribir audios con Whisper | ✅ Funcional | `backend/app/services/whisper_service.py` |
| Generar guión narrativo con Claude | ✅ Funcional | `backend/app/services/claude_service.py` |
| Convertir guión a audio .ogg | ✅ Funcional | `backend/app/services/radio_service.py` |
| Mezclar con jingle de categoría | ✅ Funcional | radio_service.py — 10 categorías |
| Subir audio a R2 + URL pública | ✅ Funcional | `backend/app/services/storage_service.py` |
| Enviar audio por WhatsApp | ✅ Funcional | tarea `send_whatsapp_voice_note` |
| Cupones ligados a campaña | ✅ Funcional | `backend/app/models/coupon.py` |
| Tags en contactos | ✅ Funcional | `contact.tags: ARRAY(String)` |
| Engagement score por contacto | ✅ Funcional | `contact.engagement_score` 0–100 |
| Sentimiento de conversación | ✅ Funcional | `conversation.lead_score`: hot/warm/cold |

**El 80% del pipeline ya existe y está en producción.**

---

## Dependencias externas: sin riesgo nuevo

| Servicio | Estado |
|---|---|
| OpenAI API (Whisper) | Ya activa — `OPENAI_API_KEY` en uso |
| Anthropic Claude | Ya activa — `ANTHROPIC_API_KEY` en uso |
| TTS (edge-tts / Google / Fish Audio) | Ya activa con fallback automático |
| Cloudflare R2 | Ya activa — storage funcionando |
| Twilio WhatsApp | Ya activa — webhook en producción |

---

## Piezas nuevas a construir

### Pieza 1 — Modelo `CustomerStory` + migración `0016`
**Esfuerzo: ~2h | Riesgo: nulo**

Nueva tabla `customer_stories`:

```python
class CustomerStory(Base):
    id: UUID
    advertiser_id: UUID (FK → users)
    contact_id: UUID | None (FK → contacts)
    campaign_id: UUID | None (FK → campaigns)   # campaña de recolección
    media_url: str                               # URL del audio original en Twilio
    transcription: str                           # texto transcrito por Whisper
    sentiment: str                               # positivo / neutro / negativo
    approved: bool (default=False)               # el dueño aprueba antes de usar
    created_at: datetime
```

---

### Pieza 2 — Nuevo prompt en `claude_service.py`
**Esfuerzo: ~1h | Riesgo: nulo**

```python
async def generate_voces_capsule(
    business_name: str,
    stories: list[dict],       # [{"name": "Ana", "text": "vengo cada viernes..."}]
    campaign_intent: str,      # ej: "postre gratis quien diga familia"
) -> str:
    ...
```

Reutiliza el cliente Anthropic ya configurado. Solo requiere un nuevo `system_prompt` narrativo que genere texto estilo locutor de radio comunitaria con historias reales.

---

### Pieza 3 — Webhook: detectar audios de campañas de recolección
**Esfuerzo: ~2h | Riesgo: bajo**

En el webhook `POST /webhooks/twilio/incoming`, cuando llega un audio de un contacto:
- Verificar si existe una campaña activa de tipo `voces` para ese advertiser.
- Si sí → guardar como `CustomerStory` (además del flujo de conversación normal).
- Reutiliza la sesión de DB y la transcripción Whisper que ya ocurren.

---

### Pieza 4 — Endpoint `POST /campaigns/{id}/generate-capsule`
**Esfuerzo: ~2h | Riesgo: nulo**

Flujo:
1. Toma todas las `CustomerStory` con `approved=True` de la campaña.
2. Llama a `generate_voces_capsule()`.
3. Pasa el guión a `generate_radio_ad()` (pipeline existente).
4. Devuelve `{ audio_url, script }` — mismo formato que el endpoint de cuñas actual.

---

### Pieza 5 — Modo `voces` en `CampaignsPage.tsx`
**Esfuerzo: ~4h | Riesgo: bajo**

Agregar `'voces'` a `AUDIO_MODES` y `CAMPAIGN_MODES`. UI multi-paso:

- **Paso 1**: Escribir la solicitud que se enviará a clientes (`"Mándanos un audio de 10 segundos diciendo cuál es tu platillo favorito"`)
- **Paso 2**: Ver historias recibidas, transcripciones y aprobar/rechazar cada una
- **Paso 3**: Generar cápsula → reproducir audio → enviar a segmento

---

### Pieza 6 — Triggers de retención en `AutomationFlow` *(baja prioridad)*
**Esfuerzo: ~4h | Riesgo: bajo**

Triggers nuevos necesarios para campañas de agradecimiento:
- `days_inactive` — X días sin interacción
- `visit_count` — alcanzó N visitas en el mes
- `return_after_absence` — volvió después de inactividad

Requiere: ampliar CHECK constraint en migración + Celery beat task periódico.  
Independiente de Voces del Barrio, puede venir después.

---

## Resumen por función

| Función | Factible | Esfuerzo | Riesgo |
|---|---|---|---|
| Recolectar audios de clientes | ✅ Sí | Bajo (2h) | Nulo |
| Generar cápsula narrativa con Claude | ✅ Sí | Bajo (1h) | Nulo |
| Convertir cápsula a audio y enviar | ✅ Sí | Bajo (2h) | Nulo |
| UI multi-paso en campañas | ✅ Sí | Medio (4h) | Bajo |
| Cupones emocionales | ✅ Sí | Nulo (0h) | Nulo — modelo Coupon ya existe |
| Triggers de retención automáticos | ✅ Sí | Medio (4h) | Bajo |
| Panel Pulso Emocional en Dashboard | ✅ Sí | Medio (3h) | Nulo |

**Total para núcleo funcional (Piezas 1–5): ~11h de desarrollo.**

---

## Orden de implementación recomendado

```
1. Migración 0016 + modelo CustomerStory          (~2h)
2. Prompt generate_voces_capsule en claude_service (~1h)
3. Lógica de recolección en webhook               (~2h)
4. Endpoint generate-capsule en campaigns.py      (~2h)
5. Modo "voces" en CampaignsPage.tsx              (~4h)
─────────────────────────────────────────────────────
   Núcleo funcional completo                      ~11h
─────────────────────────────────────────────────────
6. Triggers days_inactive / visit_count           (~4h)  — retención
7. Panel Pulso Emocional en DashboardPage         (~3h)  — analytics
```

---

## Ejemplos de uso

### Campaña tipo "Voces del Barrio"

**El negocio envía:**
> "Hoy queremos contar historias de nuestros clientes. Mándanos un audio de 10 segundos diciendo cuál es tu platillo favorito o un recuerdo que tengas aquí."

**Los clientes responden con audios. IaRadio genera:**
> "Hoy en El Fogón, Doña Carmen nos contó que cada viernes viene por enchiladas con su nieto. También Luis dice que aquí celebró su primer trabajo. Gracias por ser parte de nuestra historia. Este viernes, quienes mencionen 'familia' reciben un postre gratis."

### Campañas de agradecimiento automáticas

| Trigger | Mensaje |
|---|---|
| 3 visitas en el mes | "Hola Ana, no es promo. Solo queríamos agradecerte porque este mes volviste tres veces." |
| 30 días inactivo | "Hace un mes que no te vemos. Te extrañamos." |
| Primera compra | "Gracias por apoyar este negocio local. Tú haces posible esto." |

### Cupones emocionales (vs. cupones genéricos)

| Genérico | Emocional |
|---|---|
| "20% de descuento hoy" | "Cupón Viernes de Familia" |
| "Promo fin de semana" | "Cupón Después del Trabajo" |
| "Oferta especial" | "Cupón Cliente de Toda la Vida" |
