import { useEffect, useRef, useState } from 'react'
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
