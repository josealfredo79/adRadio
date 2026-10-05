import api from '@/lib/api'

// Prueba A/B de la mascota en la página pública (backend: services/mascot_ab.py).
// A cada visitante le toca una variante al azar y la conserva, para que no vea
// una y otra según el día. Sin almacenamiento (modo privado) se sortea cada vez:
// cuenta igual, solo un poco menos limpio.
export type MascotVariant = '3d' | 'static'
export type MascotEvent = 'view' | 'chat_open' | 'message' | 'confirmed' | 'whatsapp'

const VARIANT_KEY = 'iaradio_mascot_ab'
const VISITOR_KEY = 'iaradio_visitor'

function randomId() {
  try {
    return crypto.randomUUID().replace(/-/g, '')
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36)
  }
}

function stored(key: string, make: () => string): string {
  try {
    const v = localStorage.getItem(key)
    if (v) return v
    const fresh = make()
    localStorage.setItem(key, fresh)
    return fresh
  } catch {
    return make()
  }
}

let cached: { variant: MascotVariant; visitor: string } | null = null

export function mascotAb() {
  if (!cached) {
    const v = stored(VARIANT_KEY, () => (Math.random() < 0.5 ? '3d' : 'static'))
    cached = {
      variant: v === 'static' ? 'static' : '3d',
      visitor: stored(VISITOR_KEY, randomId),
    }
  }
  return cached
}

/** Cuenta un evento de la prueba. Nunca falla hacia el visitante. */
export function trackMascot(slug: string | undefined, event: MascotEvent) {
  if (!slug) return
  const { variant, visitor } = mascotAb()
  api.post(`/public/site/${slug}/ab`, { variant, event, visitor }).catch(() => {})
}
