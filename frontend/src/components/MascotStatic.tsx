import { useId } from 'react'
import type { FaceMood } from '@/components/BotFace'

// La misma mascota de Mascot3D en un SVG plano: sale al instante y no pesa
// nada. Es lo que se ve mientras carga el 3D, en teléfonos o conexiones que no
// lo aguantan, y la variante "imagen fija" de la prueba A/B (lib/mascotAb.ts).
// Los colores salen de la misma cuenta que palette() en Mascot3D.

const DEFAULT_COLOR = '#4fc77f'

function hexToHsl(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  const r = ((n >> 16) & 255) / 255
  const g = ((n >> 8) & 255) / 255
  const b = (n & 255) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  return [h / 6, s, l]
}

const hsl = (h: number, s: number, l: number) => `hsl(${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%)`

function mascotPalette(color?: string) {
  const [h, s0, l0] = hexToHsl(color ?? DEFAULT_COLOR) ?? hexToHsl(DEFAULT_COLOR)!
  const s = Math.max(0.35, Math.min(0.85, s0))
  const l = Math.max(0.42, Math.min(0.6, l0))
  return {
    body: hsl(h, s, l),
    bodyLight: hsl(h, s, Math.min(0.75, l + 0.12)),
    bezel: hsl(h, s * 0.7, 0.25),
    knob: hsl(h, s * 0.8, 0.36),
    glow: hsl(h, 0.95, 0.78),
  }
}

export default function MascotStatic({ mood = 'idle', size = 170, color }: { mood?: FaceMood; size?: number; color?: string }) {
  const p = mascotPalette(color)
  const gradId = `mb${useId().replace(/[^a-zA-Z0-9]/g, '')}`
  const happy = mood === 'happy'
  return (
    <svg
      width={size}
      height={Math.round(size * 1.15)}
      viewBox="-9 -4 118 136"
      role="img"
      aria-hidden="true"
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={p.bodyLight} />
          <stop offset="1" stopColor={p.body} />
        </linearGradient>
      </defs>
      {/* sombra */}
      <ellipse cx="50" cy="108" rx="26" ry="4" fill="#000" opacity="0.18" />
      {/* antena */}
      <rect x="57" y="18" width="2.4" height="16" rx="1.2" fill={p.knob} />
      <circle cx="58.2" cy="16" r="4.2" fill={p.glow} />
      {/* perillas */}
      <rect x="9" y="56" width="8" height="14" rx="3" fill={p.knob} />
      <rect x="83" y="56" width="8" height="14" rx="3" fill={p.knob} />
      {/* cuerpo */}
      <rect x="14" y="32" width="72" height="64" rx="17" fill={`url(#${gradId})`} />
      {/* pantalla */}
      <rect x="21" y="40" width="58" height="44" rx="11" fill={p.bezel} />
      <rect x="24" y="43" width="52" height="38" rx="9" fill="#0b1b2c" />
      {/* ojos */}
      {happy ? (
        <>
          <path d="M34 61 q5 -7 10 0" stroke={p.glow} strokeWidth="3.2" fill="none" strokeLinecap="round" />
          <path d="M56 61 q5 -7 10 0" stroke={p.glow} strokeWidth="3.2" fill="none" strokeLinecap="round" />
        </>
      ) : (
        <>
          <circle cx="39" cy="58" r="4.6" fill={p.glow} />
          <circle cx="61" cy="58" r="4.6" fill={p.glow} />
        </>
      )}
      {/* chapitas y sonrisa */}
      <circle cx="31" cy="67" r="3" fill="#ff8fb0" opacity="0.55" />
      <circle cx="69" cy="67" r="3" fill="#ff8fb0" opacity="0.55" />
      <path d="M43 68 q7 6 14 0" stroke={p.glow} strokeWidth="2.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}
