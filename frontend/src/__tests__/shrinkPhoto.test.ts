import { afterEach, describe, expect, it, vi } from 'vitest'
import { shrinkPhoto } from '@/lib/shrinkPhoto'

// Cartel que convence (docs/specs/2026-11-12-cartel-que-convence.md): la foto
// del celular se achica antes de subirla (el servidor acepta hasta 5 MB).

const big = () => new File([new Uint8Array(6 * 1024 * 1024)], 'IMG_2041.HEIC.png', { type: 'image/png' })

describe('shrinkPhoto', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('una foto de 6 MB y 4000 px sale como JPEG chico de 1600 px', async () => {
    const close = vi.fn()
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 4000, height: 3000, close }))
    const draw = vi.fn()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw } as never)
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (cb) {
      cb(new Blob([new Uint8Array(300 * 1024)], { type: 'image/jpeg' }))
    })
    const out = await shrinkPhoto(big())
    expect(out.type).toBe('image/jpeg')
    expect(out.name).toBe('IMG_2041.HEIC.jpg')
    expect(out.size).toBeLessThan(1024 * 1024)
    expect(draw).toHaveBeenCalledWith(expect.anything(), 0, 0, 1600, 1200)
    expect(close).toHaveBeenCalled()
  })

  it('si el navegador no puede, se sube la foto tal cual', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('no')))
    const f = big()
    expect(await shrinkPhoto(f)).toBe(f)
  })
})
