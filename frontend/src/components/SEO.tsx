import { Helmet } from 'react-helmet-async'

interface SEOProps {
  title?: string
  description?: string
  ogTitle?: string
  ogDescription?: string
  ogImage?: string
  ogUrl?: string
  canonical?: string
  noIndex?: boolean
}

const BASE_URL = import.meta.env.VITE_SITE_URL ?? 'https://iaradio.app'
const DEFAULT_TITLE = 'IaRadio — Radio Publicitaria por WhatsApp con IA'
const DEFAULT_DESCRIPTION = 'Campañas masivas por WhatsApp, bot IA que conoce tu negocio y cuñas de radio generadas en segundos. La plataforma de marketing conversacional para negocios mexicanos.'
const DEFAULT_OG_IMAGE = `${BASE_URL}/og-image.png`

export default function SEO({
  title,
  description,
  ogTitle,
  ogDescription,
  ogImage,
  ogUrl,
  canonical,
  noIndex,
}: SEOProps) {
  const fullTitle = title ? `${title} | IaRadio` : DEFAULT_TITLE
  const desc = description ?? DEFAULT_DESCRIPTION
  const oTitle = ogTitle ?? fullTitle
  const oDesc = ogDescription ?? desc
  const image = ogImage ?? DEFAULT_OG_IMAGE
  const url = ogUrl ?? BASE_URL
  const canon = canonical ?? url

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={desc} />
      {noIndex ? <meta name="robots" content="noindex, nofollow" /> : <meta name="robots" content="index, follow" />}
      <link rel="canonical" href={canon} />

      {/* Open Graph */}
      <meta property="og:type" content="website" />
      <meta property="og:url" content={url} />
      <meta property="og:title" content={oTitle} />
      <meta property="og:description" content={oDesc} />
      <meta property="og:image" content={image} />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />
      <meta property="og:locale" content="es_MX" />
      <meta property="og:site_name" content="IaRadio" />

      {/* Twitter Card */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={oTitle} />
      <meta name="twitter:description" content={oDesc} />
      <meta name="twitter:image" content={image} />
    </Helmet>
  )
}
