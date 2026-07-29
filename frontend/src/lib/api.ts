import axios, { AxiosError } from 'axios'

export function getApiError(err: unknown, fallback = 'Error'): string {
  if (err instanceof AxiosError) {
    return (err.response?.data as { detail?: string })?.detail ?? fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

// Access token stored in memory — never in localStorage (XSS-safe)
let _accessToken: string | null = null

export function setAccessToken(token: string | null) {
  _accessToken = token
}

export function getAccessToken(): string | null {
  return _accessToken
}

// Stable idempotency keys per (url + body) to prevent duplicate processing on retries
const _idempotencyMap = new Map<string, string>()

const api = axios.create({
  // In production (Railway) VITE_API_URL is set to the backend service URL.
  // In local dev the Vite proxy handles /api → http://backend:8000, so baseURL stays relative.
  baseURL: `${import.meta.env.VITE_API_URL ?? ''}/api/v1`,
  withCredentials: true, // send httpOnly refresh_token cookie automatically
  timeout: 10000,
})

// Attach in-memory access token to every request
api.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`
  }
  // Idempotency-Key for mutating requests to prevent duplicate processing
  if (config.method && ['post', 'put', 'patch'].includes(config.method)) {
    const bodyKey = config.data ? JSON.stringify(config.data) : ''
    const urlKey = config.url || ''
    const idemKey = `${urlKey}::${bodyKey}`
    if (!_idempotencyMap.has(idemKey)) {
      _idempotencyMap.set(idemKey, crypto.randomUUID())
    }
    config.headers['Idempotency-Key'] = _idempotencyMap.get(idemKey)
  }
  return config
})

// Auto-refresh on 401 using httpOnly cookie (no body needed)
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config

    // Don't intercept auth endpoints (login, register, etc.)
    // Let those errors flow to the caller for proper UI feedback.
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/')
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true
      try {
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_URL ?? ''}/api/v1/auth/refresh`,
          null,
          { withCredentials: true, timeout: 10000 },
        )
        setAccessToken(data.access_token)
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`
        return api(originalRequest)
      } catch {
        setAccessToken(null)
        const currentPath = window.location.pathname
        window.location.href = currentPath !== '/login' ? `/login?redirect=${encodeURIComponent(currentPath)}` : '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
