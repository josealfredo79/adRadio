// El chat web con cara de WhatsApp (lo que el cliente ya sabe usar) y el toque
// de IaRadio: el color del negocio en el encabezado y en sus burbujas, y un
// fondo con ondas de radio, micrófonos y notas en vez de los dibujitos de WhatsApp.

export interface ChatPalette {
  wallpaper: string
  doodle: string
  incoming: string
  outgoing: string
  text: string
  meta: string
  ticks: string
  bar: string
  field: string
  notice: string
  noticeText: string
  accent: string
  onBrand: string
}

// Con un color claro (amarillo, verde limón) el texto blanco no se lee.
function isLight(hex: string): boolean {
  const m = hex.trim().match(/^#?([0-9a-f]{6})$/i)
  if (!m) return false
  const n = parseInt(m[1], 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.7
}

export function chatPalette(color: string, dark: boolean): ChatPalette {
  const onBrand = isLight(color) ? '#111b21' : '#ffffff'
  return dark
    ? {
        wallpaper: '#0b141a',
        doodle: 'rgba(255,255,255,0.05)',
        incoming: '#202c33',
        outgoing: `color-mix(in srgb, ${color} 42%, #0b141a)`,
        text: '#e9edef',
        meta: '#8696a0',
        ticks: '#53bdeb',
        bar: '#1f2c34',
        field: '#2a3942',
        notice: '#182229',
        noticeText: '#ffd279',
        accent: `color-mix(in srgb, ${color} 65%, #ffffff)`,
        onBrand,
      }
    : {
        wallpaper: '#efeae2',
        doodle: 'rgba(17,27,33,0.07)',
        incoming: '#ffffff',
        // 32%: con colores tierra (café, mostaza) al 20% la burbuja se perdía en el fondo beige.
        outgoing: `color-mix(in srgb, ${color} 32%, #ffffff)`,
        text: '#111b21',
        meta: '#667781',
        ticks: '#53bdeb',
        bar: '#f0f2f5',
        field: '#ffffff',
        notice: '#fff3c4',
        noticeText: '#54656f',
        accent: `color-mix(in srgb, ${color} 80%, #000000)`,
        onBrand,
      }
}

// Mosaico de 160 px: radio, micrófono, ondas, nota musical, estrella, burbuja y corazón.
export function wallpaperPattern(stroke: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<rect x="14" y="22" width="34" height="22" rx="4"/><circle cx="25" cy="33" r="5"/><path d="M36 29h8M36 35h8M20 22l18-9"/>
<rect x="104" y="12" width="10" height="17" rx="5"/><path d="M99 25a10 10 0 0 0 20 0M109 35v6"/>
<path d="M70 70a10 10 0 0 1 0 14M76 64a19 19 0 0 1 0 26M64 70a10 10 0 0 0 0 14M58 64a19 19 0 0 0 0 26"/><circle cx="67" cy="77" r="2"/>
<path d="M128 74v-14l12-3v14"/><circle cx="125" cy="74" r="3"/><circle cx="137" cy="71" r="3"/>
<path d="M30 104l3 6 6 1-4.5 4.5 1 6.5-5.5-3-5.5 3 1-6.5L21 111l6-1z"/>
<path d="M92 112h24a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5h-14l-7 6v-6h-3a5 5 0 0 1-5-5v-10a5 5 0 0 1 5-5z"/>
<path d="M140 132c-3-4-9-2-9 3 0 4 9 9 9 9s9-5 9-9c0-5-6-7-9-3z"/>
<path d="M54 140a6 6 0 0 1 12 0M50 140a10 10 0 0 1 20 0"/>
</svg>`
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
}

export function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-MX', { hour: 'numeric', minute: '2-digit' })
}

// "Hoy", "Ayer", el día de la semana si fue esta semana, si no la fecha.
export function dayLabel(iso: string): string {
  const d = new Date(iso)
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((start(new Date()) - start(d)) / 86_400_000)
  if (days <= 0) return 'Hoy'
  if (days === 1) return 'Ayer'
  if (days < 7) {
    const w = d.toLocaleDateString('es-MX', { weekday: 'long' })
    return w.charAt(0).toUpperCase() + w.slice(1)
  }
  return d.toLocaleDateString('es-MX', { day: 'numeric', month: 'long', year: days > 300 ? 'numeric' : undefined })
}
