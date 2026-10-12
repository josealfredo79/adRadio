# Cómo guiar la prueba real del usuario

Lo aprendido el 2026-10-12, cuando una prueba de 5 minutos tardó una hora por instrucciones confusas.

## Quién es quién

- **Cuenta del usuario:** `tecnologicotlaxiaco@gmail.com`, negocio "IaRadio" (es la que recibe las pláticas del número central). Es admin. La contraseña es suya: nunca la pidas ni la guardes.
- **No usar** `iaradio@iaradio.online`: es la cuenta que Meta usa para revisar la App.
- **Su celular (+52 953 195 3182) está registrado como DUEÑO.** Si escribe al número central de IaRadio le contesta su **Copiloto**, no el bot de clientes. Desde su WhatsApp NO puede hacerse pasar por cliente.
- **Para ser cliente de su propio negocio:** Configuración → tarjeta "Agente inteligente" → botón **"Probar como cliente"**. Abre su tarjeta de cliente con chat ya identificado (contacto "Alfredo" o "Tú (prueba)"). Lo que escriba ahí llega al Inbox marcado "por la web".

## Reglas que confunden

- **Ventana de 24 h de WhatsApp:** contestar desde el Inbox a alguien que no ha escrito en 24 h no le llega (Meta lo rechaza, error 131047). Para probar respuestas por WhatsApp, primero el cliente escribe.
- **El bot NO se pausa** cuando el dueño contesta desde el Inbox (solo con "escalada"/pausa manual).
- **Laboratorio NO es un chat:** corre 6 clientes simulados contra el bot y tarda minutos (además gasta el límite de Voyage). Para preguntarle algo al bot, usar el chat de "Probar como cliente".
- **Funciones que dependen de lo que el cliente dijo antes** (como aprender del Inbox: busca la pregunta de las últimas 12 h): primero pregunta el cliente, luego contesta el dueño.

## Cómo escribir los pasos

1. Siempre una tabla de pestañas: qué pestaña, quién es ahí (cliente/dueño), qué hace.
2. El texto exacto a escribir, en negritas, y aclarar cuando es un ejemplo ("pon tu precio real").
3. Qué debe ver en cada paso, para que sepa si va bien.
4. Pídele captura si algo no sale y revisa con la skill `revisar-prod` antes de suponer.
5. Si el bot ya sabía la respuesta antes del cambio, la prueba no demuestra nada: usa un dato que el bot no conozca.
