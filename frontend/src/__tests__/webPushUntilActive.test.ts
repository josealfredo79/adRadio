import { describe, expect, it } from 'vitest'
import { untilActive } from '@/lib/webPushClient'

// Desde /sitio, navigator.serviceWorker.ready nunca se resolvía (el service
// worker del portal vive en /c/): "Sí, avísame" se quedaba girando. Ahora se
// espera al registro mismo (prueba e2e local 2026-11-10).
function fakeWorker(state: string) {
  const listeners: (() => void)[] = []
  const sw = {
    state,
    addEventListener: (_: string, fn: () => void) => listeners.push(fn),
    go(next: string) {
      sw.state = next
      listeners.forEach((fn) => fn())
    },
  }
  return sw
}

describe('untilActive', () => {
  it('resolves at once when already active', async () => {
    await expect(untilActive({ active: {} } as unknown as ServiceWorkerRegistration)).resolves.toBeUndefined()
  })

  it('waits for the installing worker to activate', async () => {
    const sw = fakeWorker('installing')
    const p = untilActive({ active: null, installing: sw, waiting: null } as unknown as ServiceWorkerRegistration)
    sw.go('installed')
    sw.go('activated')
    await expect(p).resolves.toBeUndefined()
  })

  it('fails instead of hanging when the worker is discarded or never activates', async () => {
    const sw = fakeWorker('installing')
    const p = untilActive({ active: null, installing: sw, waiting: null } as unknown as ServiceWorkerRegistration)
    sw.go('redundant')
    await expect(p).rejects.toThrow()
    const stuck = fakeWorker('installing')
    await expect(
      untilActive({ active: null, installing: stuck, waiting: null } as unknown as ServiceWorkerRegistration, 20),
    ).rejects.toThrow()
  })
})
