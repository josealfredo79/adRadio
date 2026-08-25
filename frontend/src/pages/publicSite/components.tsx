import { Link } from 'react-router-dom'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Menu, MessageCircle, X } from 'lucide-react'
import { categoryEmoji, formatBusinessHours, formatPrice, waDigits } from './utils'
import type { BusinessHours } from './utils'
import type { SiteThemeDef } from './theme'
import { isDarkTheme } from './theme'

export const SITE_SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif"

export function MeshBackground({ color, dark }: { color: string; dark: boolean }) {
  const a = dark ? ['40', '26', '1a'] : ['14', '0d', '0a']
  return (
    <div
      className="pointer-events-none fixed inset-0 z-0"
      aria-hidden="true"
      style={{
        background: `radial-gradient(ellipse 70% 50% at 12% -10%, ${color}${a[0]} 0%, transparent 60%),
                      radial-gradient(ellipse 60% 45% at 88% 20%, ${color}${a[1]} 0%, transparent 60%),
                      radial-gradient(ellipse 55% 50% at 50% 100%, ${color}${a[2]} 0%, transparent 65%)`,
      }}
    />
  )
}

export function Badge({
  children,
  color,
  icon,
  onPhoto,
}: {
  children: ReactNode
  color: string
  icon?: ReactNode
  onPhoto?: boolean
}) {
  const style = onPhoto
    ? { background: 'rgba(255,255,255,.15)', color: '#fff', border: '1px solid rgba(255,255,255,.3)' }
    : { background: `${color}1a`, color, border: `1px solid ${color}40` }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold" style={style}>
      {icon}
      {children}
    </span>
  )
}

export interface NavLink {
  label: string
  href: string
}

export function NavBar({
  businessName,
  logoUrl,
  categoryFallback,
  whatsappNumber,
  agent,
  color,
  theme,
  links,
}: {
  businessName: string
  logoUrl: string
  categoryFallback: string
  whatsappNumber: string
  agent: string
  color: string
  theme: SiteThemeDef
  links: NavLink[]
}) {
  const [open, setOpen] = useState(false)
  const waHref = whatsappNumber ? `https://wa.me/${waDigits(whatsappNumber)}` : null

  return (
    <div
      className="sticky top-0 z-40"
      style={{ background: `${theme.bg}ee`, backdropFilter: 'blur(8px)', borderBottom: `1px solid ${theme.cardBorder}` }}
    >
      <div className="max-w-4xl mx-auto px-6 py-3 flex items-center justify-between gap-6">
        <a href="#" className="flex items-center gap-2.5 min-w-0">
          {logoUrl ? (
            <img src={logoUrl} alt={businessName} className="h-9 w-9 rounded-lg object-cover shrink-0" />
          ) : (
            <span className="text-xl shrink-0">{categoryEmoji(categoryFallback)}</span>
          )}
          <span className="font-semibold text-[15px] truncate" style={{ color: theme.text }}>
            {businessName}
          </span>
        </a>

        {!!links.length && (
          <div className="psite-nav-links">
            {links.map((l) => (
              <a key={l.href} href={l.href} className="psite-nav-link text-sm font-medium" style={{ color: theme.text }}>
                {l.label}
              </a>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 shrink-0">
          {waHref && (
            <a
              href={waHref}
              target="_blank"
              rel="noreferrer"
              className="psite-btn-primary psite-nav-cta items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold shadow"
              style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, color: '#fff', ...glowVar(color, theme) }}
            >
              <MessageCircle size={13} />
              Chatea con {agent}
            </a>
          )}
          {!!links.length && (
            <button
              type="button"
              aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
              onClick={() => setOpen((v) => !v)}
              className="sm:hidden -m-2 p-2"
              style={{ color: theme.text }}
            >
              {open ? <X size={22} /> : <Menu size={22} />}
            </button>
          )}
        </div>
      </div>

      {open && !!links.length && (
        <div className="sm:hidden px-4 pb-3 flex flex-col gap-1" style={{ borderTop: `1px solid ${theme.cardBorder}` }}>
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="psite-mobile-link rounded-lg px-3 py-2.5 text-[15px] font-medium"
              style={{ color: theme.text }}
            >
              {l.label}
            </a>
          ))}
          {waHref && (
            <a
              href={waHref}
              target="_blank"
              rel="noreferrer"
              onClick={() => setOpen(false)}
              className="psite-btn-primary mt-1 flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold"
              style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, color: '#fff' }}
            >
              <MessageCircle size={15} />
              Chatea con {agent}
            </a>
          )}
        </div>
      )}
    </div>
  )
}

export function SectionHeading({ eyebrow, title, color }: { eyebrow: string; title: string; color: string }) {
  return (
    <div className="text-center mb-6">
      <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color }}>
        {eyebrow}
      </p>
      <h2 className="text-2xl sm:text-3xl font-medium" style={{ fontFamily: SITE_SERIF }}>{title}</h2>
    </div>
  )
}

export function Avatar({ name, color }: { name: string | null; color: string }) {
  return (
    <div
      className="h-10 w-10 rounded-full flex items-center justify-center text-sm font-bold text-white shrink-0"
      style={{ background: `linear-gradient(135deg, ${color}cc, ${color}66)`, boxShadow: `0 0 0 2px ${color}40`, fontFamily: SITE_SERIF }}
    >
      {name ? (
        name[0].toUpperCase()
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />
        </svg>
      )}
    </div>
  )
}

export function BusinessHoursCard({ hours, color, theme }: { hours: BusinessHours | null | undefined; color: string; theme: SiteThemeDef }) {
  const rows = formatBusinessHours(hours)
  if (!rows.length) return null
  return (
    <div
      className="rounded-2xl p-6"
      style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, ...cardElevationStyle(theme) }}
    >
      <div className="flex items-center gap-2 mb-4">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>
        <span className="text-xs font-bold uppercase tracking-wide" style={{ color: theme.text }}>Horario de atención</span>
      </div>
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex items-center justify-between text-sm py-2"
          style={{ borderBottom: `1px solid ${theme.cardBorder}`, color: theme.muted }}
        >
          <span>{row.label}</span>
          <span className="font-semibold" style={{ color: theme.text }}>{row.range}</span>
        </div>
      ))}
      <div className="flex items-center justify-between text-sm pt-2">
        <span style={{ color: theme.muted }}>WhatsApp</span>
        <span className="font-semibold" style={{ color }}>Respuesta 24/7</span>
      </div>
    </div>
  )
}

export function cardElevationStyle(theme: SiteThemeDef): React.CSSProperties {
  return isDarkTheme(theme)
    ? { backdropFilter: 'blur(12px)', boxShadow: '0 8px 30px rgba(0,0,0,.35)' }
    : { boxShadow: '0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06)' }
}

export function glowVar(color: string, theme: SiteThemeDef): React.CSSProperties {
  return { '--psite-glow': `${color}${isDarkTheme(theme) ? '4d' : '26'}` } as React.CSSProperties
}

interface PublicProduct {
  id: string
  name: string
  description: string
  price: string | null
  category: string
  photo_url: string
  sales_count: number
}

export function ProductCard({
  product,
  categoryFallback,
  color,
  slug,
  theme,
  promoted,
  style,
}: {
  product: PublicProduct
  categoryFallback: string
  color: string
  slug: string
  theme: SiteThemeDef
  promoted?: boolean
  style?: React.CSSProperties
}) {
  return (
    <Link
      to={`/sitio/${slug}/producto/${product.id}`}
      className="psite-hover-lift rounded-2xl overflow-hidden text-left block relative"
      style={{
        background: theme.cardBg,
        border: `1px solid ${promoted ? color : theme.cardBorder}`,
        ...cardElevationStyle(theme),
        ...glowVar(color, theme),
        ...(promoted ? { boxShadow: `0 0 0 1px ${color}, 0 12px 32px -8px ${color}66` } : {}),
        ...style,
      }}
    >
      {promoted && (
        <span
          className="absolute top-2 right-2 z-10 rounded-full px-2.5 py-1 text-[11px] font-bold text-white"
          style={{ background: color }}
        >
          🔥 Más vendido
        </span>
      )}
      <div className="h-36 flex items-center justify-center overflow-hidden relative" style={{ background: theme.cardBg }}>
        {product.category && (
          <span
            className="absolute top-2 left-2 z-10 rounded-full px-2.5 py-1 text-[11px] font-semibold text-white"
            style={{ background: 'rgba(0,0,0,.55)', backdropFilter: 'blur(4px)' }}
          >
            {product.category}
          </span>
        )}
        {product.photo_url ? (
          <img src={product.photo_url} alt={product.name} className="h-full w-full object-cover" />
        ) : (
          <span className="text-4xl">{categoryEmoji(product.category || categoryFallback)}</span>
        )}
      </div>
      <div className="p-4 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">{product.name}</h3>
          <span className="shrink-0 text-sm font-semibold" style={{ color }}>
            {formatPrice(product.price)}
          </span>
        </div>
        {product.description && <p className="text-sm line-clamp-2" style={{ color: theme.muted }}>{product.description}</p>}
      </div>
    </Link>
  )
}
