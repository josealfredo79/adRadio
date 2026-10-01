// Service worker del portal del cliente (/c/:token). Solo muestra las
// notificaciones web que manda el backend (app/services/web_push.py) y abre
// el portal al tocarlas. Sin caché offline a propósito: el portal siempre
// debe mostrar datos al día (citas, cupones).

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { body: event.data ? event.data.text() : '' }
  }
  const options = {
    body: data.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: data.url || '/' },
    lang: 'es-MX',
  }
  if (data.image) options.image = data.image
  // Mismo tag = reemplaza en vez de apilar (ej. el recordatorio de 1 h
  // sustituye al de 24 h de la misma cita).
  if (data.tag) {
    options.tag = data.tag
    options.renotify = true
  }
  event.waitUntil(self.registration.showNotification(data.title || 'Tienes un aviso', options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (w.url === url && 'focus' in w) return w.focus()
      }
      return self.clients.openWindow(url)
    }),
  )
})
