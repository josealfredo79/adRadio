---
name: revisar-prod
description: Revisar qué está pasando en producción de IaRadio leyendo los registros de Railway (solo lectura) — errores, chats lentos o cortados, fallas de servicios externos (Groq, Voyage, Meta, Anthropic), base de datos. Úsalo siempre que el usuario reporte algo raro en vivo ("no me llegó tu mensaje", "el bot no contesta", "tardó mucho", "salió un error", "no aparece en el Inbox"), después de un despliegue para confirmar que no hay errores nuevos, o antes de culpar al código de algo que podría ser un servicio externo.
---

# Revisar producción (IaRadio)

Producción tiene clientes reales y no hay staging, así que los registros son la única forma de ver qué pasó de verdad. La base de datos de producción **no se toca desde aquí** (el modo automático lo bloquea y es correcto): todo sale de los registros de Railway, que son de solo lectura.

## 1. Resumen del periodo

```bash
python3 .claude/skills/revisar-prod/scripts/prod_logs.py --since 3h      # o 30m, 24h, 2d
```

Recorre todos los despliegues del periodo (Railway guarda los registros por despliegue: con `railway logs` a secas solo ves el último y parece que no pasó nada). Agrega `--raw <carpeta del scratchpad>` para guardar los registros crudos y buscar con grep.

## 2. Cómo leerlo

- **499 en `/widget/chat`** = el cliente se cansó de esperar (el chat web se rinde a los 45 s y dice "Uy, no me llegó tu mensaje"). Busca qué estaba lento en esa misma hora.
- **`/conversations/events` de 900 s** es normal: es la conexión en vivo del Inbox.
- **Servicios externos con ⚠️**: algún código distinto de 2xx.
  - `api.groq.com 429` = Groq al límite; la cadena pasa al siguiente modelo (normal si es poco).
  - Voyage 429 = plan sin tarjeta (3 búsquedas/min en total). Desde 0bd30b1 ya no cuelga el chat, pero esas respuestas salen sin base de conocimiento.
  - `graph.facebook.com` con 4xx = Meta rechazó algo; 131047 = fuera de la ventana de 24 h (normal si el dueño contesta tarde).
- **"Conexión a la base de datos cerrada"**: Neon cerró conexiones inactivas. Si coincide con 5xx o 499, es un problema real.

## 3. Para un caso concreto

Si el usuario manda una captura con hora, busca esa ventana exacta (hora de México = UTC−6):
```bash
railway logs -s adRadio --http --since <ISO> --until <ISO> --lines 400 | grep -E "widget/chat|/reply|/learn| 5[0-9][0-9] | 499 "
railway logs -s adRadio --since <ISO> --until <ISO> --lines 1500    # registros de la app
```
Cruza la hora de la petición lenta con lo que hacían los servicios externos en ese mismo minuto.

## 4. Reporte

En español sencillo: qué pasó, a cuántos clientes afectó, si es código nuestro o un servicio externo, y qué se hace (arreglo nuestro o algo que le toca al usuario, como poner tarjeta en un servicio). No adivines la causa: si los registros no la muestran, dilo.
