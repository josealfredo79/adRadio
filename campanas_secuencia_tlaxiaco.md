# Campana Secuencia Tlaxiaco - 3 mensajes en 5 dias

## Mensaje 1: Presentacion (Dia 1)

**Asunto:** Presentacion IaRadio - WhatsApp Inteligente

**Mensaje:**
```
Hola {name} 👋

Soy el equipo de IaRadio, una plataforma que usa Inteligencia Artificial para automatizar el WhatsApp de negocios como {business_name}.

Imagina que tus clientes te escriben por WhatsApp y un bot inteligente les responde 24/7, conoce tu negocio, toma pedidos y agenda citas. Todo automatico.

Responde *QUIERO* y te muestro como funciona en tu negocio.
```

**Notas:**
- Enviar entre 10am-12pm
- Segmento: todos los contactos de Tlaxiaco
- Seguimiento: si responde "QUIERO", marcar como lead caliente

---

## Mensaje 2: Caso de Uso (Dia 3)

**Asunto:** Restaurantes +40% pedidos con WhatsApp IA

**Mensaje:**
```
Hola {name} 👋

Un restaurante en Oaxaca aumento sus pedidos un 40% usando un bot de WhatsApp que:
- Responde el menu automaticamente
- Toma pedidos sin que nadie conteste
- Envia promociones a clientes frecuentes

Con IaRadio tu negocio puede tener lo mismo desde $499/mes.

Sin contratos. 15 dias gratis.

Responde *INFO* si te interesa saber mas.
```

**Notas:**
- Enviar 2 dias despues delMensaje 1
- Segmento: contactos que NO respondieron al Mensaje 1
- El caso de uso se adapta segun el giro del negocio

---

## Mensaje 3: Cupon QR (Dia 5)

**Asunto:** 50% descuento primer mes IaRadio

**Mensaje:**
```
Hola {name} 👋

Ultimo mensaje Promise 🙌

Te doy *50% OFF* en tu primer mes de IaRadio:

- Plan Starter: $499 → $249/mes
- Plan Growth: $999 → $499/mes

Cupones validos hasta el fin de semana.

Registrate en:
👉 www.iaradio.online/register

Responde *SI* si quieres que te guie en el proceso.
```

**Notas:**
- Enviar 2 dias despues del Mensaje 2
- Segmento: contactos que NO respondieron a los 2 mensajes anteriores
- El cupon se aplica manualmente via admin panel despues del registro

---

## Configuracion en la plataforma

1. Crear 3 campanas con schedule:
   - Campana 1: Dia 1, hora 10am CDMX
   - Campana 2: Dia 3, hora 11am CDMX
   - Campana 3: Dia 5, hora 10am CDMX

2. Segmentar:
   - Campana 1: Todos los contactos etiquetados `tlaxiaco`
   - Campana 2: Contactos que NO respondieron Campana 1
   - Campana 3: Contactos que NO respondieron Campana 1 ni 2

3. Monitorear:
   - Tasa de apertura
   - Respuestas "QUIERO", "INFO", "SI"
   - Leads calificados -> agendar visita
