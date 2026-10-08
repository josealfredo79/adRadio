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

// Chats abiertos en este celular aunque no haya entrado con su número (llegó por
// el link de WhatsApp): "atrás" lleva a una lista de chats, como en WhatsApp, y
// no a otra pantalla. Solo guarda lo que este navegador ya tenía.
const RECENT_KEY = 'iaradio_recent_chats'
const RECENT_MAX = 20

export interface RecentChat {
  portal_path: string
  name: string
  logo_url: string
  color: string
  at: string
}

export function readRecentChats(): RecentChat[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
  } catch {
    return []
  }
}

export function rememberChat(chat: Omit<RecentChat, 'at'>) {
  try {
    const rest = readRecentChats().filter((c) => c.portal_path !== chat.portal_path)
    const list = [{ ...chat, at: new Date().toISOString() }, ...rest].slice(0, RECENT_MAX)
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    // sin almacenamiento: no hay lista local
  }
}
