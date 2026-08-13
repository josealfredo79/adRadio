import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import { ArrowLeft, Check, Copy, MessageCircle, Share2 } from 'lucide-react'

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
}

const formatPrice = (price: string | null) =>
  price === null ? 'Cotizar' : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(price))

export default function ProductDetailPage() {
  const { slug, productId } = useParams<{ slug: string; productId: string }>()
  const [notFound, setNotFound] = useState(false)
  const [copied, setCopied] = useState(false)

  const { data: product, isLoading } = useQuery<ProductDetail>({
    queryKey: ['public-site-product', slug, productId],
    queryFn: () =>
      api
        .get(`/public/site/${slug}/products/${productId}`)
        .then((r) => r.data)
        .catch((err) => {
          if (err?.response?.status === 404) setNotFound(true)
          throw err
        }),
    enabled: !!slug && !!productId,
    retry: false,
  })

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-[#06060f] text-white">Cargando...</div>
  }

  if (notFound || !product) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[#06060f] text-white">
        <p className="text-2xl font-bold">Producto no encontrado</p>
        <Link to={`/sitio/${slug}`} className="text-white/60 underline">
          Volver al catálogo
        </Link>
      </div>
    )
  }

  const pageUrl = `${window.location.origin}/sitio/${slug}/producto/${product.id}`
  const waMessage = encodeURIComponent(`Hola, me interesa: ${product.name}`)

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
      <div className="min-h-screen bg-[#06060f] text-white font-sans">
        <div className="max-w-2xl mx-auto px-6 py-8">
          <Link to={`/sitio/${slug}`} className="inline-flex items-center gap-1.5 text-white/60 hover:text-white text-sm mb-6">
            <ArrowLeft size={16} />
            Volver a {product.business_name}
          </Link>

          <div className="rounded-2xl overflow-hidden bg-white/5 border border-white/10">
            <div className="aspect-square bg-white/5 flex items-center justify-center overflow-hidden">
              {product.photo_url ? (
                <img src={product.photo_url} alt={product.name} className="h-full w-full object-cover" />
              ) : (
                <span className="text-7xl">🎙️</span>
              )}
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <h1 className="text-2xl font-bold">{product.name}</h1>
                <span className="shrink-0 text-xl font-bold text-brand-400">{formatPrice(product.price)}</span>
              </div>
              {product.category && <p className="text-sm text-white/50">{product.category}</p>}
              {product.description && <p className="text-white/70 leading-relaxed">{product.description}</p>}

              <div className="flex flex-col sm:flex-row gap-3 pt-2">
                <a
                  href={`https://wa.me/?text=${waMessage}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex-1 inline-flex items-center justify-center gap-2 rounded-full bg-[#25D366] px-5 py-3 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
                >
                  <MessageCircle size={18} />
                  Preguntar por WhatsApp
                </a>
                <button
                  onClick={handleShare}
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-white/20 px-5 py-3 text-sm font-semibold text-white hover:bg-white/5 transition-colors"
                >
                  {copied ? <Check size={18} /> : <Share2 size={18} />}
                  {copied ? 'Link copiado' : 'Compartir'}
                </button>
              </div>
            </div>
          </div>

          <button
            onClick={() => navigator.clipboard.writeText(pageUrl)}
            className="mt-4 flex items-center gap-1.5 text-xs text-white/40 hover:text-white/60 mx-auto"
          >
            <Copy size={12} />
            {pageUrl}
          </button>
        </div>
      </div>
    </>
  )
}
