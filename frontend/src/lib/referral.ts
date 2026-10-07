// "Recomiéndalo a un amigo": el código ?r= del link de quien recomendó se
// guarda por negocio (slug) al abrir su página, y se manda al registrarse
// (/q/{slug}), donde el backend le da el sello a quien recomendó.
const KEY = (slug: string) => `iaradio_ref_${slug}`
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000

export function captureRef(slug: string | undefined | null) {
  if (!slug) return
  try {
    const code = new URLSearchParams(window.location.search).get('r')
    if (code && /^[A-Za-z0-9_-]{10,40}$/.test(code)) localStorage.setItem(KEY(slug), JSON.stringify({ code, at: Date.now() }))
  } catch {
    // almacenamiento bloqueado: sin atribución, nada más
  }
}

export function readRef(slug: string | undefined | null): string | undefined {
  if (!slug) return undefined
  try {
    const raw = localStorage.getItem(KEY(slug))
    if (!raw) return undefined
    const { code, at } = JSON.parse(raw) as { code: string; at: number }
    return Date.now() - at < MAX_AGE_MS ? code : undefined
  } catch {
    return undefined
  }
}

export function referralLink(slug: string, code: string): string {
  return `${window.location.origin}/sitio/${slug}?r=${encodeURIComponent(code)}`
}
