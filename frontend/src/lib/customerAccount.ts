// Sesión de la cuenta del cliente (/mi) — el token firmado que devuelve el
// backend (services/customer_account.py). La usan /mi y el registro por QR.

const TOKEN_KEY = 'iaradio_account_token'

export function readAccountToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function saveAccountToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // almacenamiento bloqueado (modo privado): la sesión dura lo que la pestaña
  }
}

// Cuándo vio el cliente por última vez cada chat (por token de su tarjeta), para
// el globito de "no leído" en la lista de /mi. Solo en este navegador.
const SEEN_KEY = 'iaradio_chat_seen'

function readSeen(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(SEEN_KEY) || '{}')
  } catch {
    return {}
  }
}

export function markChatSeen(portalToken: string) {
  try {
    const seen = readSeen()
    seen[portalToken] = new Date().toISOString()
    localStorage.setItem(SEEN_KEY, JSON.stringify(seen))
  } catch {
    // sin almacenamiento (modo privado): no hay globito, nada más
  }
}

export function chatSeenAt(portalToken: string): string | null {
  return readSeen()[portalToken] ?? null
}
