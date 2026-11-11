import api from '@/lib/api'

// Avisos web (Web Push) del cliente: los usan el portal (/c/) y el chat de la
// página del negocio (tras agendar). Backend: api/v1/portal.py /push/*.
export type NotifyState = 'loading' | 'unsupported' | 'ios-install' | 'denied' | 'off' | 'on'

export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
}

export function detectNotifyState(): NotifyState | Promise<NotifyState> {
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
  const standalone =
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
  // En iPhone, Safari solo ofrece push a la app ya agregada a la pantalla de inicio.
  if (ios && !standalone) return 'ios-install'
  if (!supported) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  return navigator.serviceWorker
    .getRegistration('/c/')
    .then((reg) => reg?.pushManager.getSubscription())
    .then((sub): NotifyState => (sub ? 'on' : 'off'))
    .catch((): NotifyState => 'off')
}

/** Espera a que el service worker recién registrado quede activo (hace falta para suscribir). */
export function untilActive(reg: ServiceWorkerRegistration, timeoutMs = 10000): Promise<void> {
  if (reg.active) return Promise.resolve()
  const sw = reg.installing ?? reg.waiting
  if (!sw) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('service worker no se activó')), timeoutMs)
    sw.addEventListener('statechange', () => {
      if (sw.state === 'activated') {
        clearTimeout(timer)
        resolve()
      } else if (sw.state === 'redundant') {
        clearTimeout(timer)
        reject(new Error('service worker descartado'))
      }
    })
  })
}

/** Pide permiso y suscribe. Regresa el nuevo estado y si cayó el sello de regalo. */
export async function enablePush(token: string, publicKey: string): Promise<{ state: NotifyState; stamped: boolean }> {
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return { state: permission === 'denied' ? 'denied' : 'off', stamped: false }
  // No `navigator.serviceWorker.ready`: solo se resuelve con un service worker
  // que controle ESTA página, y el del portal vive en /c/. Desde el chat de
  // /sitio se quedaba esperando para siempre (botón "Sí, avísame" girando).
  const reg = await navigator.serviceWorker.register('/portal-sw.js', { scope: '/c/' })
  await untilActive(reg)
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
    }))
  const { data } = await api.post(`/public/portal/${token}/push/subscribe`, sub.toJSON())
  return { state: 'on', stamped: !!data?.stamped }
}
