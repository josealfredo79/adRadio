import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
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

const formatPrice = (price: string | null) =>
  price === null ? 'Cotizar' : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(price))

function ProductCard({ product, categoryFallback, color }: { product: PublicProduct; categoryFallback: string; color: string }) {
  return (
    <div className="rounded-2xl bg-white/5 border border-white/10 overflow-hidden text-left">
      <div className="h-36 bg-white/5 flex items-center justify-center overflow-hidden">
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
        {product.category && <p className="text-xs text-white/50">{product.category}</p>}
        {product.description && <p className="text-sm text-white/70 line-clamp-2">{product.description}</p>}
      </div>
    </div>
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

  return (
    <>
      <SEO
        title={site.business_name}
        description={`${site.business_name}${site.city ? ` — ${site.city}` : ''}. Chatea con nosotros.`}
      />
      <div className="min-h-screen bg-[#06060f] text-white font-sans">
        <header
          className="px-6 py-20 text-center"
          style={{ background: `linear-gradient(180deg, ${site.color}33 0%, transparent 100%)` }}
        >
          <div className="text-6xl mb-4">{categoryEmoji(site.business_category)}</div>
          <h1 className="text-3xl sm:text-4xl font-bold">{site.business_name}</h1>
          {site.tagline && <p className="mt-3 text-white/80 text-lg">{site.tagline}</p>}
          <div className="mt-3 flex items-center justify-center gap-3 text-white/60 text-sm flex-wrap">
            {site.business_category && <span>{site.business_category}</span>}
            {site.city && (
              <span className="flex items-center gap-1">
                <MapPin size={14} />
                {site.city}
              </span>
            )}
          </div>
        </header>

        {!!bestsellers.length && (
          <section className="max-w-4xl mx-auto px-6 pb-4">
            <h2 className="text-xl font-bold text-center mb-6">🔥 Los favoritos de nuestros clientes</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {bestsellers.map((p) => (
                <ProductCard key={p.id} product={p} categoryFallback={site.business_category} color={site.color} />
              ))}
            </div>
          </section>
        )}

        {!!products?.length && (
          <section className="max-w-4xl mx-auto px-6 pb-16">
            <h2 className="text-xl font-bold text-center mb-6">Nuestro catálogo</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {products.map((p) => (
                <ProductCard key={p.id} product={p} categoryFallback={site.business_category} color={site.color} />
              ))}
            </div>
          </section>
        )}

        <main className="max-w-2xl mx-auto px-6 pb-32 text-center space-y-6">
          {!site.tagline && (
            <p className="text-white/70 leading-relaxed">
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
      </div>
    </>
  )
}
