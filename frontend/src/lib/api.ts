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
    config.headers['Idempotency-Key'] = crypto.randomUUID()
  }
  return config
})

// Auto-refresh on 401 using httpOnly cookie (no body needed)
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
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
