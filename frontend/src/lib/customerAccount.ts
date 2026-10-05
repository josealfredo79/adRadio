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
