import { describe, it, expect, vi, beforeEach } from 'vitest'

// docs/specs/2026-10-12-coexistencia.md — casos 1 y 2 del lado del navegador.
type Login = (cb: (r: unknown) => void, opts: Record<string, unknown>) => void

function installFb(login: Login) {
  window.FB = {
    init: vi.fn(),
    login: login as never,
    logout: vi.fn(),
    getLoginStatus: vi.fn(),
    Event: { subscribe: vi.fn() },
    AppEvents: { logPageView: vi.fn() },
  }
}

describe('launchEmbeddedSignup', () => {
  beforeEach(() => vi.resetModules())

  it('caso 1: uses Embedded Signup v4 (empty setup extras, no v2 feature flags)', async () => {
    let options: Record<string, unknown> = {}
    installFb((cb, opts) => {
      options = opts
      cb({ authResponse: { code: 'c1' } })
    })
    const { launchEmbeddedSignup } = await import('@/lib/fbSdk')
    await launchEmbeddedSignup('app', 'cfg')
    expect(options.config_id).toBe('cfg')
    expect(options.extras).toEqual({ setup: {} })
  })

  it('caso 2: business app onboarding (via window.postMessage) is reported as coexistence', async () => {
    installFb((cb) => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://www.facebook.com',
        data: JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', data: { waba_id: 'w9' } }),
      }))
      cb({ authResponse: { code: 'c2' } })
    })
    const { launchEmbeddedSignup } = await import('@/lib/fbSdk')
    expect(await launchEmbeddedSignup('app', 'cfg')).toEqual({ code: 'c2', wabaId: 'w9', phoneNumberId: '', coexistence: true })
  })

  it('ignores messages that do not come from facebook.com', async () => {
    installFb((cb) => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://malicioso.example',
        data: JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', data: { waba_id: 'x' } }),
      }))
      cb({ authResponse: { code: 'c3' } })
    })
    const { launchEmbeddedSignup } = await import('@/lib/fbSdk')
    expect(await launchEmbeddedSignup('app', 'cfg')).toEqual({ code: 'c3', wabaId: '', phoneNumberId: '', coexistence: false })
  })
})
