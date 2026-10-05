import { lazy, Suspense, useEffect, useState } from 'react'
import type { FaceMood } from '@/components/BotFace'
import MascotStatic from '@/components/MascotStatic'

const Mascot3D = lazy(() => import('@/components/Mascot3D'))

/** ¿Vale la pena el 3D aquí? No con ahorro de datos, conexión lenta,
 * movimiento reducido ni en teléfonos de pocos núcleos: ahí la imagen fija
 * se ve igual de bien y no frena la página. */
function canAfford3D(): boolean {
  if (typeof window === 'undefined') return false
  try {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return false
    const conn = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection
    if (conn?.saveData) return false
    if (conn?.effectiveType && ['slow-2g', '2g', '3g'].includes(conn.effectiveType)) return false
    if (navigator.hardwareConcurrency && navigator.hardwareConcurrency < 4) return false
  } catch {
    return true
  }
  return true
}

/** La mascota que sale al instante (SVG) y, si el equipo aguanta y `allow3d`,
 * se cambia por la 3D cuando el navegador ya terminó lo importante. */
export default function MascotSmart({
  mood,
  size,
  color,
  allow3d = true,
}: {
  mood: FaceMood
  size: number
  color?: string
  allow3d?: boolean
}) {
  const [load3d, setLoad3d] = useState(false)

  useEffect(() => {
    if (!allow3d || !canAfford3D()) return
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void }
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setLoad3d(true), { timeout: 2500 })
      return () => w.cancelIdleCallback?.(id)
    }
    const t = window.setTimeout(() => setLoad3d(true), 1200)
    return () => window.clearTimeout(t)
  }, [allow3d])

  const still = <MascotStatic mood={mood} size={size} color={color} />
  if (!load3d) return still
  return (
    <Suspense fallback={still}>
      <Mascot3D mood={mood} size={size} color={color} />
    </Suspense>
  )
}
