import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import { MapPin, MessageCircle } from 'lucide-react'

interface PublicSite {
  advertiser_id: string
  business_name: string
  business_category: string
  city: string
  agent: string
  greeting: string
  color: string
  tagline: string
  logo_url: string
  hero_image_url: string
  site_theme: string
  whatsapp_number: string
}

const waDigits = (n: string) => n.replace(/\D/g, '')

export interface SiteThemeDef {
  name: string
  bg: string
  text: string
  muted: string
  cardBg: string
  cardBorder: string
}

export const SITE_THEMES: Record<string, SiteThemeDef> = {
  medianoche: { name: 'Medianoche', bg: '#06060f', text: '#ffffff', muted: 'rgba(255,255,255,.65)', cardBg: 'rgba(255,255,255,.05)', cardBorder: 'rgba(255,255,255,.1)' },
  pizarra: { name: 'Pizarra', bg: '#0f172a', text: '#f1f5f9', muted: 'rgba(241,245,249,.65)', cardBg: 'rgba(255,255,255,.04)', cardBorder: 'rgba(255,255,255,.08)' },
  esmeralda: { name: 'Esmeralda', bg: '#06120d', text: '#eafff5', muted: 'rgba(234,255,245,.65)', cardBg: 'rgba(255,255,255,.05)', cardBorder: 'rgba(255,255,255,.1)' },
  claro: { name: 'Claro', bg: '#f8fafc', text: '#0f172a', muted: '#64748b', cardBg: '#ffffff', cardBorder: '#e2e8f0' },
  crema: { name: 'Crema', bg: '#fdf6ec', text: '#2b2118', muted: '#8a7862', cardBg: '#ffffff', cardBorder: '#eee0cc' },
}

function getSiteTheme(key: string): SiteThemeDef {
  return SITE_THEMES[key] ?? SITE_THEMES.medianoche
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

interface PublicStory {
  id: string
  contact_name: string | null
  transcription: string
  media_url: string
  sentiment: string
}

const SENTIMENT_EMOJI: Record<string, string> = { positivo: '😊', negativo: '😕', neutro: '🙂' }

const formatPrice = (price: string | null) =>
  price === null ? 'Cotizar' : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(price))

function ProductCard({
  product,
  categoryFallback,
  color,
  slug,
  theme,
}: {
  product: PublicProduct
  categoryFallback: string
  color: string
  slug: string
  theme: SiteThemeDef
}) {
  return (
    <Link
      to={`/sitio/${slug}/producto/${product.id}`}
      className="rounded-2xl overflow-hidden text-left block transition-opacity hover:opacity-90"
      style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}
    >
      <div className="h-36 flex items-center justify-center overflow-hidden" style={{ background: theme.cardBg }}>
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
        {product.category && <p className="text-xs" style={{ color: theme.muted }}>{product.category}</p>}
        {product.description && <p className="text-sm line-clamp-2" style={{ color: theme.muted }}>{product.description}</p>}
      </div>
    </Link>
  )
}

const CATEGORY_EMOJI: Record<string, string> = {
  restaurante: '🍽️', comida: '🍽️', cocina: '🍽️',
  salud: '🩺', clinica: '🩺', clínica: '🩺', dental: '🦷', dentista: '🦷',
  belleza: '💇', salon: '💇', salón: '💇', spa: '💆', estetica: '💆', estética: '💆',
  ropa: '👗', moda: '👗', boutique: '👗',
  taller: '🔧', mecanico: '🔧', mecánico: '🔧', automotriz: '🚗',
  gimnasio: '🏋️', fitness: '🏋️',
  abogado: '⚖️', legal: '⚖️',
  inmobiliaria: '🏠', bienes: '🏠',
  educacion: '📚', educación: '📚', escuela: '📚', academia: '📚',
  tienda: '🛍️', comercio: '🛍️',
  hotel: '🏨', turismo: '🏨',
}

function categoryEmoji(category: string): string {
  const key = category.toLowerCase().trim()
  for (const [k, emoji] of Object.entries(CATEGORY_EMOJI)) {
    if (key.includes(k)) return emoji
  }
  return '🎙️'
}

const WIDGET_BASE = (import.meta.env.VITE_WIDGET_URL as string | undefined) ?? ''

export default function PublicSitePage() {
  const { slug } = useParams<{ slug: string }>()
  const [notFound, setNotFound] = useState(false)
  const widgetMounted = useRef(false)

  const { data: site, isLoading } = useQuery<PublicSite>({
    queryKey: ['public-site', slug],
    queryFn: () =>
      api
        .get(`/public/site/${slug}`)
        .then((r) => r.data)
        .catch((err) => {
          if (err?.response?.status === 404) setNotFound(true)
          throw err
        }),
    enabled: !!slug,
    retry: false,
  })

  const { data: products } = useQuery<PublicProduct[]>({
    queryKey: ['public-site-products', slug],
    queryFn: () => api.get(`/public/site/${slug}/products`).then((r) => r.data),
    enabled: !!slug && !!site,
    retry: false,
  })

  const { data: stories } = useQuery<PublicStory[]>({
    queryKey: ['public-site-stories', slug],
    queryFn: () => api.get(`/public/site/${slug}/stories`).then((r) => r.data),
    enabled: !!slug && !!site,
    retry: false,
  })

  const bestsellers = useMemo(
    () =>
      (products ?? [])
        .filter((p) => p.sales_count > 0)
        .sort((a, b) => b.sales_count - a.sales_count)
        .slice(0, 3),
    [products]
  )

  useEffect(() => {
    if (!site || widgetMounted.current) return
    widgetMounted.current = true

    ;(window as unknown as { IaRadioWidget?: unknown }).IaRadioWidget = {
      advertiserId: site.advertiser_id,
      apiBase: `${WIDGET_BASE}/api/v1`,
      business: site.business_name,
      agent: site.agent,
      greeting: site.greeting,
      color: site.color,
    }

    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `${WIDGET_BASE}/widget/widget.css`
    document.head.appendChild(link)

    const script = document.createElement('script')
    script.src = `${WIDGET_BASE}/widget/widget.js`
    script.defer = true
    document.body.appendChild(script)

    return () => {
      link.remove()
      script.remove()
      document.getElementById('iaradio-widget-popup')?.remove()
      document.getElementById('iaradio-widget-btn')?.remove()
    }
  }, [site])

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-[#06060f] text-white">Cargando...</div>
  }

  if (notFound || !site) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[#06060f] text-white">
        <p className="text-2xl font-bold">Página no encontrada</p>
        <p className="text-white/60">Este link no corresponde a ningún negocio.</p>
      </div>
    )
  }

  const theme = getSiteTheme(site.site_theme)

  return (
    <>
      <SEO
        title={site.business_name}
        description={`${site.business_name}${site.city ? ` — ${site.city}` : ''}. Chatea con nosotros.`}
      />
      <div className="min-h-screen font-sans" style={{ background: theme.bg, color: theme.text }}>
        <header
          className="px-6 py-20 text-center relative overflow-hidden"
          style={
            site.hero_image_url
              ? { backgroundImage: `url(${site.hero_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
              : { background: `linear-gradient(180deg, ${site.color}33 0%, transparent 100%)` }
          }
        >
          {/* Con foto de portada el texto siempre es blanco sobre un velo oscuro,
              sin importar el tema elegido — necesario para que se lea encima de
              cualquier foto real, no solo de los gradientes planos curados. */}
          {site.hero_image_url && (
            <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(0,0,0,.35) 0%, rgba(0,0,0,.65) 100%)' }} />
          )}
          <div className="relative" style={site.hero_image_url ? { color: '#fff' } : undefined}>
            {site.logo_url ? (
              <img src={site.logo_url} alt={site.business_name} className="h-20 w-20 rounded-2xl object-cover mx-auto mb-4 shadow-lg" />
            ) : (
              <div className="text-6xl mb-4">{categoryEmoji(site.business_category)}</div>
            )}
            <h1 className="text-3xl sm:text-4xl font-bold">{site.business_name}</h1>
            {site.tagline && (
              <p className="mt-3 text-lg" style={site.hero_image_url ? { color: 'rgba(255,255,255,.85)' } : { color: theme.muted }}>
                {site.tagline}
              </p>
            )}
            <div
              className="mt-3 flex items-center justify-center gap-3 text-sm flex-wrap"
              style={site.hero_image_url ? { color: 'rgba(255,255,255,.75)' } : { color: theme.muted }}
            >
              {site.business_category && <span>{site.business_category}</span>}
              {site.city && (
                <span className="flex items-center gap-1">
                  <MapPin size={14} />
                  {site.city}
                </span>
              )}
            </div>
          </div>
        </header>

        {!!stories?.length && (
          <section className="max-w-4xl mx-auto px-6 pt-16 pb-4">
            <h2 className="text-xl font-bold text-center mb-6">Lo que dicen nuestros clientes</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {stories.map((s) => (
                <div
                  key={s.id}
                  className="rounded-2xl p-5 space-y-3"
                  style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}
                >
                  <p className="text-sm leading-relaxed" style={{ color: theme.text }}>
                    "{s.transcription}"
                  </p>
                  <audio controls src={s.media_url} className="w-full h-9" />
                  <p className="text-xs" style={{ color: theme.muted }}>
                    {SENTIMENT_EMOJI[s.sentiment] ?? '🙂'} {s.contact_name ? `— ${s.contact_name}, cliente real` : '— Cliente real'}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        {!!bestsellers.length && (
          <section className="max-w-4xl mx-auto px-6 pb-4">
            <h2 className="text-xl font-bold text-center mb-6">🔥 Los favoritos de nuestros clientes</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {bestsellers.map((p) => (
                <ProductCard key={p.id} product={p} categoryFallback={site.business_category} color={site.color} slug={slug ?? ''} theme={theme} />
              ))}
            </div>
          </section>
        )}

        {!!products?.length && (
          <section className="max-w-4xl mx-auto px-6 pb-16">
            <h2 className="text-xl font-bold text-center mb-6">Nuestro catálogo</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {products.map((p) => (
                <ProductCard key={p.id} product={p} categoryFallback={site.business_category} color={site.color} slug={slug ?? ''} theme={theme} />
              ))}
            </div>
          </section>
        )}

        <main className="max-w-2xl mx-auto px-6 pb-16 text-center space-y-6">
          {!site.tagline && (
            <p className="leading-relaxed" style={{ color: theme.muted }}>
              Bienvenido a {site.business_name}. Escríbenos por el chat en la esquina de tu pantalla y {site.agent}{' '}
              te va a atender al instante.
            </p>
          )}
          <div
            className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold"
            style={{ background: site.color, color: '#fff' }}
          >
            <MessageCircle size={16} />
            Chatea con {site.agent}
          </div>
        </main>

        <footer className="border-t px-6 py-8 pb-32 text-center text-sm" style={{ borderColor: theme.cardBorder, color: theme.muted }}>
          {site.whatsapp_number && (
            <a
              href={`https://wa.me/${waDigits(site.whatsapp_number)}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 font-medium hover:opacity-80 transition-opacity"
              style={{ color: theme.text }}
            >
              <MessageCircle size={14} />
              {site.whatsapp_number}
            </a>
          )}
          <p className="mt-3">
            © {new Date().getFullYear()} {site.business_name}. Todos los derechos reservados.
          </p>
        </footer>
      </div>
    </>
  )
}
