// Lo que un visitante le dictó a la carita en la landing, guardado en SU
// navegador (la demo es sin cuenta y el servidor no guarda nada). Después de
// registrarse, /app/voice-setup lo recupera para que no repita nada.

const KEY = 'iaradio-demo-draft'
const MAX_AGE_MS = 7 * 24 * 3600 * 1000

export function saveDemoDraft(profile: unknown): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ profile, at: Date.now() }))
  } catch {
    // sin almacenamiento (modo privado): solo no se recupera después
  }
}

export function loadDemoDraft<T>(): T | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const { profile, at } = JSON.parse(raw) as { profile: T; at: number }
    if (!profile || Date.now() - at > MAX_AGE_MS) {
      localStorage.removeItem(KEY)
      return null
    }
    return profile
  } catch {
    return null
  }
}

export function clearDemoDraft(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // nada que limpiar
  }
}
