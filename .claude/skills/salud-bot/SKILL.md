---
name: salud-bot
description: Chequeo de salud de todo lo que necesita el bot de IaRadio para contestar bien en producción — cadena de modelos de IA (Groq, Cloudflare, Gemini, Mistral, OpenRouter, Anthropic), Voyage (búsqueda en la base de conocimiento), Meta/WhatsApp, base de datos y que el sitio responda. Úsalo cuando el usuario pregunte "¿cómo está el bot?", "¿está todo bien?", "revisa los servicios", "¿por qué contesta raro?", en una revisión semanal, o cuando se sospeche que un servicio externo se cayó o cambió (modelos que dejan de existir, planes gratis que cambian).
---

# Salud del bot (IaRadio)

El bot depende de varios servicios de afuera que cambian sin avisar: un modelo gratis deja de serlo, un proveedor borra un modelo, un plan gratis tiene límite. Ninguno truena el sitio: el bot cae al siguiente proveedor o contesta sin buscar, y nadie se entera. Este chequeo existe para enterarse antes que los clientes.

Mide **producción**, no la configuración local: `backend/.env` puede estar viejo (el 2026-10-12 decía que Groq y OpenRouter daban 404 y en producción Groq contestaba 200). Nunca concluyas de pruebas locales que producción está mal.

## 1. ¿Responde el sitio?

```bash
curl -s -m 20 -w ' %{http_code}\n' https://www.iaradio.online/health/ready
```
200 = base de datos y Redis bien.

## 1b. ¿Le queda saldo a Anthropic?

Claude es el último respaldo del bot, del agente del cliente y del Copiloto. Anthropic no avisa ni tiene API de saldo: cuando se acaba, cada llamada da 400 "credit balance is too low" y nadie se entera hasta que fallan los gratis.

```bash
python3 .claude/skills/salud-bot/scripts/anthropic_saldo.py
```
Hace una llamada de 1 token con la llave de producción (menos de un centavo). ✅ = con saldo; 🔴 = recargar en console.anthropic.com → Settings → Billing (lo hace el usuario). El clasificador bloquea leer la llave de Railway: pídele al usuario que lo corra con `! python3 .claude/skills/salud-bot/scripts/anthropic_saldo.py`. En los registros, `prod_logs.py` también cuenta "Anthropic SIN SALDO".

## 2. Lo que pasó en producción (últimas 24 h)

```bash
python3 .claude/skills/revisar-prod/scripts/prod_logs.py --since 24h
```

Llena esta tabla con lo que salga en "Servicios externos" y "Patrones conocidos":

| Servicio | Para qué | Bien | Atención |
|---|---|---|---|
| api.groq.com | 1er modelo del bot (gratis) | casi todo 200 | muchos 429 o 404 → modelo borrado o al límite |
| api.cloudflare.com / gemini / mistral / openrouter | respaldos gratis | 200 cuando aparecen | 404 = modelo que ya no existe o dejó de ser gratis |
| api.anthropic.com | respaldo de pago (Claude) | pocas llamadas, 200 | muchas = los gratis están fallando y se está pagando; 400 + "Anthropic SIN SALDO" = recargar |
| Voyage (embeddings) | buscar en la base de conocimiento | sin 429 | 429 = plan sin tarjeta (3/min); el bot contesta sin lo que el dueño le enseñó |
| graph.facebook.com | WhatsApp | 200 | 4xx frecuentes (no cuenta 131047, que es normal) |
| Base de datos | todo | sin "conexión cerrada" con 5xx/499 | conexiones cerradas junto con errores = problema real |

Señal clave: **cuántas veces "Proveedor de IA falló y se pasó al siguiente"** y **cuántas llamadas a Anthropic**. Si suben, algo de la cadena gratis se rompió aunque el bot siga contestando.

## 3. Si un proveedor falla

Busca el mensaje exacto (dice qué modelo y por qué):
```bash
railway logs -s adRadio --since 24h --lines 3000 | grep "\[LLM\]"
railway logs -s worker  --since 24h --lines 3000 | grep "\[LLM\]"
```
Los modelos se configuran con variables en Railway (`GROQ_CHAT_MODEL`, `OPENROUTER_MODEL`, …). Cambiarlas es cambiar producción: proponle al usuario el modelo nuevo y que él confirme antes de tocar nada.

## 4. Reporte

Una tabla corta con ✅/⚠️ por servicio y, abajo, solo lo que requiere acción, diciendo quién la hace (tú en código, o el usuario en el panel de un proveedor). Si todo está bien, dilo en una línea.
