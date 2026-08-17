import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import { ArrowLeft, Check, Copy, MessageCircle, Share2 } from 'lucide-react'
import { getSiteTheme, isDarkTheme } from '@/pages/publicSite/theme'
import { waDigits, formatPrice } from '@/pages/publicSite/utils'
import { MeshBackground, cardElevationStyle } from '@/pages/publicSite/components'
import { PUBLIC_SITE_STYLES } from '@/pages/publicSite/styles'

interface ProductDetail {
  id: string
  name: string
  description: string
  price: string | null
  category: string
  photo_url: string
  sales_count: number
  business_name: string
  slug: string
  whatsapp_number: string
  site_theme: string
  color: string
}

export default function ProductDetailPage() {
  // Two route shapes point here: /sitio/:slug/producto/:productId (business
  // has published a landing page) and /p/:advertiserId/:productId (works
  // for every advertiser regardless — see public_site.py's product_router
  // docstring for why the slug can't be a hard dependency here).
  const { slug, advertiserId, productId } = useParams<{ slug?: string; advertiserId?: string; productId: string }>()
  const [notFound, setNotFound] = useState(false)
  const [copied, setCopied] = useState(false)

  const apiPath = slug
    ? `/public/site/${slug}/products/${productId}`
    : `/public/product/${advertiserId}/${productId}`

  const { data: product, isLoading } = useQuery<ProductDetail>({
    queryKey: ['public-product', slug ?? advertiserId, productId],
    queryFn: () =>
      api
        .get(apiPath)
        .then((r) => r.data)
        .catch((err) => {
          if (err?.response?.status === 404) setNotFound(true)
          throw err
        }),
    enabled: !!(slug || advertiserId) && !!productId,
    retry: false,
  })

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-[#06060f] text-white">Cargando...</div>
  }

  if (notFound || !product) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[#06060f] text-white">
        <p className="text-2xl font-bold">Producto no encontrado</p>
        {slug && (
          <Link to={`/sitio/${slug}`} className="text-white/60 underline">
            Volver al catálogo
          </Link>
        )}
      </div>
    )
  }

  const theme = getSiteTheme(product.site_theme)
  const dark = isDarkTheme(theme)

  const pageUrl = slug
    ? `${window.location.origin}/sitio/${slug}/producto/${product.id}`
    : `${window.location.origin}/p/${advertiserId}/${product.id}`
  const waMessage = encodeURIComponent(`Hola, me interesa: ${product.name}`)
  // Sin número conectado, wa.me/?text= abre WhatsApp sin destinatario — no
  // hay forma de "arreglarlo" del todo sin un número real, así que el botón
  // solo se muestra cuando sí existe uno.
  const waHref = product.whatsapp_number ? `https://wa.me/${waDigits(product.whatsapp_number)}?text=${waMessage}` : null

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: product.name, url: pageUrl })
        return
      } catch {
        // user cancelled the native share sheet — fall through to copy
      }
    }
    await navigator.clipboard.writeText(pageUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <SEO
        title={`${product.name} — ${product.business_name}`}
        description={product.description || `${product.name} en ${product.business_name}`}
        ogImage={product.photo_url || undefined}
        ogUrl={pageUrl}
        canonical={pageUrl}
      />
      <style>{PUBLIC_SITE_STYLES}</style>
      <div className="min-h-screen font-sans" style={{ background: theme.bg, color: theme.text }}>
        <MeshBackground color={product.color} dark={dark} />

        <div className="relative z-10 max-w-2xl mx-auto px-6 py-8">
          {product.slug && (
            <Link
              to={`/sitio/${product.slug}`}
              className="inline-flex items-center gap-1.5 text-sm mb-6 hover:opacity-80 transition-opacity"
              style={{ color: theme.muted }}
            >
              <ArrowLeft size={16} />
              Volver a {product.business_name}
            </Link>
          )}

          <div
            className="rounded-2xl overflow-hidden"
            style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, ...cardElevationStyle(theme) }}
          >
            <div className="aspect-square flex items-center justify-center overflow-hidden" style={{ background: theme.cardBg }}>
              {product.photo_url ? (
                <img src={product.photo_url} alt={product.name} className="h-full w-full object-cover" />
              ) : (
                <span className="text-7xl">🎙️</span>
              )}
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <h1 className="text-2xl font-bold">{product.name}</h1>
                <span className="shrink-0 text-xl font-bold" style={{ color: product.color }}>
                  {formatPrice(product.price)}
                </span>
              </div>
              {product.category && <p className="text-sm" style={{ color: theme.muted }}>{product.category}</p>}
              {product.description && <p className="leading-relaxed" style={{ color: theme.muted }}>{product.description}</p>}

              <div className="flex flex-col sm:flex-row gap-3 pt-2">
                {waHref && (
                  <a
                    href={waHref}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-2 rounded-full bg-[#25D366] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#25D366]/20 hover:scale-[1.03] active:scale-[0.98] transition-all duration-300"
                  >
                    <MessageCircle size={18} />
                    Preguntar por WhatsApp
                  </a>
                )}
                <button
                  onClick={handleShare}
                  className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition-colors hover:opacity-80"
                  style={{ border: `1px solid ${theme.cardBorder}`, color: theme.text }}
                >
                  {copied ? <Check size={18} /> : <Share2 size={18} />}
                  {copied ? 'Link copiado' : 'Compartir'}
                </button>
              </div>
            </div>
          </div>

          <button
            onClick={() => navigator.clipboard.writeText(pageUrl)}
            className="mt-4 flex items-center gap-1.5 text-xs mx-auto hover:opacity-80"
            style={{ color: theme.muted }}
          >
            <Copy size={12} />
            {pageUrl}
          </button>
        </div>
      </div>
    </>
  )
}
