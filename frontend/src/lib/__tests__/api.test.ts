import { afterEach, describe, expect, it, vi } from 'vitest'
import axios, { type InternalAxiosRequestConfig } from 'axios'
import api, { setAccessToken } from '@/lib/api'

// La app del cliente (/mi) manda su propia credencial; con el dueño logueado
// en el mismo navegador no hay que cambiársela (2026-10-05: 401 en bucle).
describe('api interceptors', () => {
  const seen: InternalAxiosRequestConfig[] = []
  const original = api.defaults.adapter

  afterEach(() => {
    api.defaults.adapter = original
    setAccessToken(null)
    seen.length = 0
  })

  it('keeps an explicit Authorization header (customer account token)', async () => {
    setAccessToken('owner-jwt')
    api.defaults.adapter = async (config) => {
      seen.push(config)
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    }
    await api.get('/public/me/businesses', { headers: { Authorization: 'Bearer customer-token' } })
    await api.get('/me')
    expect(seen[0].headers.Authorization).toBe('Bearer customer-token')
    expect(seen[1].headers.Authorization).toBe('Bearer owner-jwt')
  })

  it('does not try the owner refresh (nor redirect to /login) on a public 401', async () => {
    const refresh = vi.spyOn(axios, 'post').mockRejectedValue(new Error('sin sesión de dueño'))
    api.defaults.adapter = async (config) => {
      seen.push(config)
      const err = Object.assign(new Error('401'), { config, response: { status: 401, data: {}, headers: {}, config } })
      throw err
    }
    await expect(api.get('/public/me/businesses', { headers: { Authorization: 'Bearer old' } })).rejects.toBeTruthy()
    expect(seen).toHaveLength(1) // sin reintento con la sesión del dueño
    expect(refresh).not.toHaveBeenCalled() // ni renovarla (y luego mandar al /login del panel)
    refresh.mockRestore()
  })
})
