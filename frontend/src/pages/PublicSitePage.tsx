import { Fragment, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import AgentChat from '@/components/AgentChat'
import MascotSmart from '@/components/MascotSmart'
import { mascotAb, trackMascot } from '@/lib/mascotAb'
import { useNativeViewport } from '@/lib/useNativeViewport'
import { ArrowRight, Clock, MapPin, MessageCircle, Zap } from 'lucide-react'
import { getSiteTheme, isDarkTheme } from '@/pages/publicSite/theme'
import { waDigits, categoryEmoji, openStatus, stockPhotos, DEFAULT_LANDING_SECTIONS, type BusinessHours, type LandingSectionId } from '@/pages/publicSite/utils'
import HeroSlider from '@/pages/publicSite/HeroSlider'
import { captureRef } from '@/lib/referral'
import { FLAT_LOGO, isFlatImage } from '@/lib/flatImage'
import { MeshBackground, NavBar, BenefitsSection, SectionHeading, Avatar, ProductCard, BusinessHoursCard, cardElevationStyle, glowVar, SITE_SERIF } from '@/pages/publicSite/components'
import type { NavLink } from '@/pages/publicSite/components'
import { PUBLIC_SITE_STYLES } from '@/pages/publicSite/styles'

const SITE_FONT_HREF = 'https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap'

interface PublicSite {
  advertiser_id: string
  business_name: string
  business_category: string
  city: string
  agent: string
  greeting: string
  quick_asks?: { icon: string; text: string }[] | null
  color: string
  tagline: string
  logo_url: string
  hero_image_url: string
  site_photos: string[]
  site_about: string
  site_theme: string
  whatsapp_number: string
  business_hours: BusinessHours | null
  landing_sections: LandingSectionId[] | null
  slug: string
  account_available: boolean
}

// El agente 3D (la mascota robot que habla) — se descarga aparte, solo aquí.

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

export default function PublicSitePage() {
  const { slug } = useParams<{ slug: string }>()
  const [notFound, setNotFound] = useState(false)
  // Chat web con el agente: gratis para el negocio y sin salir de la página
  // (antes los botones mandaban a WhatsApp, que Meta cobra).
  const [chatOpen, setChatOpen] = useState(false)
  // Fotos o logo del dueño que no cargaron (archivo borrado, link roto): se
  // ocultan y la página sigue con las fotos de stock de su giro.
  const [broken, setBroken] = useState<string[]>([])
  const markBroken = (src: string) => setBroken((b) => (b.includes(src) ? b : [...b, src]))
  const abVariant = mascotAb().variant
  const openChat = () => {
    setChatOpen(true)
    trackMascot(site?.slug || slug, 'chat_open')
  }

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

  useNativeViewport(site ? getSiteTheme(site.site_theme).bg : undefined)

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

  // Prueba A/B de la mascota: una visita por visitante (el servidor descarta repetidas).
  const siteSlug = site?.slug
  useEffect(() => {
    if (siteSlug) trackMascot(siteSlug, 'view')
    captureRef(siteSlug)
  }, [siteSlug])

  useEffect(() => {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = SITE_FONT_HREF
    document.head.appendChild(link)
    return () => { link.remove() }
  }, [])

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
  const dark = isDarkTheme(theme)
  // Portada: las fotos del dueño; si no tiene, su portada vieja; si no, las de stock de su giro.
  const ownPhotos = (site.site_photos?.length ? site.site_photos : site.hero_image_url ? [site.hero_image_url] : []).filter(
    (src) => !broken.includes(src)
  )
  const logoUrl = site.logo_url && !broken.includes(site.logo_url) ? site.logo_url : ''
  const heroPhotos = ownPhotos.length ? ownPhotos : stockPhotos(site.business_category)
  const aboutPhoto = ownPhotos[1] ?? ownPhotos[0] ?? heroPhotos[1] ?? heroPhotos[0]
  const status = openStatus(site.business_hours)

  const sections: LandingSectionId[] = site.landing_sections?.length ? site.landing_sections : DEFAULT_LANDING_SECTIONS

  const navLinks: NavLink[] = sections.flatMap((id): NavLink[] => {
    switch (id) {
      case 'beneficios':
        return [{ label: 'Beneficios', href: '#beneficios' }]
      case 'opiniones':
        return stories?.length ? [{ label: 'Opiniones', href: '#opiniones' }] : []
      case 'catalogo':
        return products?.length ? [{ label: 'Catálogo', href: '#catalogo' }] : []
      case 'nosotros_horario':
        return [
          { label: 'Nosotros', href: '#nosotros' },
          ...(site.business_hours ? [{ label: 'Horario', href: '#horario' }] : []),
        ]
      default:
        return []
    }
  })

  return (
    <>
      <SEO
        title={site.business_name}
        description={`${site.business_name}${site.city ? ` — ${site.city}` : ''}. Chatea con nosotros.`}
      />
      <style>{PUBLIC_SITE_STYLES}</style>
      <div className="min-h-screen font-sans" style={{ background: theme.bg, color: theme.text }}>
        <MeshBackground color={site.color} dark={dark} />

        <div className="relative z-10">
          <NavBar
            businessName={site.business_name}
            logoUrl={logoUrl}
            categoryFallback={site.business_category}
            whatsappNumber={site.whatsapp_number}
            agent={site.agent}
            color={site.color}
            theme={theme}
            links={navLinks}
            onChat={openChat}
          />

          <HeroSlider photos={heroPhotos} alt={site.business_name} color={site.color} onBroken={markBroken}>
            <div className="psite-hero-text relative mx-auto flex w-full max-w-6xl flex-col justify-end px-6 pb-16 pt-28 text-white sm:px-10 sm:pb-20">
              {logoUrl ? (
                <img
                  src={logoUrl}
                  alt=""
                  onError={() => markBroken(logoUrl)}
                  onLoad={(e) => { if (isFlatImage(e.currentTarget, FLAT_LOGO)) markBroken(logoUrl) }}
                  className="mb-5 h-16 w-16 rounded-2xl object-cover shadow-xl ring-2 ring-white/70 sm:h-20 sm:w-20" />
              ) : (
                <span className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/15 text-4xl backdrop-blur-md ring-1 ring-white/30">
                  {categoryEmoji(site.business_category)}
                </span>
              )}
              <h1
                className={`${site.business_name.length > 32 ? 'text-4xl sm:text-6xl' : 'text-5xl sm:text-7xl'} max-w-4xl font-medium leading-[1.02] tracking-tight text-balance`}
                style={{ fontFamily: SITE_SERIF, textShadow: '0 2px 24px rgba(0,0,0,.35)' }}
              >
                {site.business_name}
              </h1>
              {site.tagline && <p className="mt-4 max-w-2xl text-lg text-white/90 sm:text-xl">{site.tagline}</p>}
              <div className="mt-5 flex flex-wrap items-center gap-2">
                {status && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-black/35 px-3 py-1.5 text-xs font-semibold backdrop-blur-md ring-1 ring-white/20">
                    <span className={`h-2 w-2 rounded-full ${status.open ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                    {status.label}
                  </span>
                )}
                {site.city && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-black/35 px-3 py-1.5 text-xs font-semibold backdrop-blur-md ring-1 ring-white/20">
                    <MapPin size={12} /> {site.city}
                  </span>
                )}
              </div>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={openChat}
                  className="psite-btn-primary inline-flex items-center gap-2 rounded-full px-6 py-3.5 text-[15px] font-semibold shadow-xl"
                  style={{ background: site.color, color: '#fff', ...glowVar(site.color, theme) }}
                >
                  <MessageCircle size={18} />
                  Platica con {site.agent}
                </button>
                {!!products?.length && (
                  <a
                    href="#catalogo"
                    className="psite-btn-primary inline-flex items-center gap-2 rounded-full bg-white/15 px-6 py-3.5 text-[15px] font-semibold text-white ring-1 ring-white/40 backdrop-blur-md"
                  >
                    Ver catálogo <ArrowRight size={16} />
                  </a>
                )}
              </div>
              {site.whatsapp_number && (
                <a
                  href={`https://wa.me/${waDigits(site.whatsapp_number)}`}
                  onClick={() => trackMascot(slug, 'whatsapp')}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 w-fit text-sm text-white/80 underline underline-offset-4 hover:text-white"
                >
                  o escríbenos por WhatsApp
                </a>
              )}
            </div>
          </HeroSlider>

          {/* Lo que el cliente quiere saber de un vistazo. */}
          <section className="relative z-10 mx-auto -mt-8 max-w-5xl px-4 sm:px-6">
            <div
              className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl sm:grid-cols-3"
              style={{ background: theme.cardBorder, ...cardElevationStyle(theme) }}
            >
              {[
                { icon: Clock, title: status?.open ? 'Abierto ahora' : 'Horario', text: status?.label.split(' · ')[1] ?? 'Consulta nuestro horario abajo', href: '#horario' },
                { icon: Zap, title: 'Respuesta al instante', text: `${site.agent} te atiende por chat, texto o voz`, onClick: openChat },
                { icon: MapPin, title: site.city || 'Visítanos', text: site.city ? `${site.business_name} en ${site.city}` : 'Pregúntanos cómo llegar', onClick: openChat },
              ].map((it) => {
                const body = (
                  <>
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" style={{ background: `${site.color}1f`, color: site.color }}>
                      <it.icon size={20} />
                    </span>
                    <span className="min-w-0 text-left">
                      <span className="block text-sm font-semibold" style={{ color: theme.text }}>{it.title}</span>
                      <span className="block truncate text-sm" style={{ color: theme.muted }}>{it.text}</span>
                    </span>
                  </>
                )
                const cls = 'flex items-center gap-3 px-5 py-4 transition-opacity hover:opacity-90'
                const st = { background: dark ? '#10121c' : theme.cardBg }
                return it.href ? (
                  <a key={it.title} href={it.href} className={cls} style={st}>{body}</a>
                ) : (
                  <button key={it.title} type="button" onClick={it.onClick} className={cls} style={st}>{body}</button>
                )
              })}
            </div>
          </section>

          {/* Galería: solo fotos reales del negocio (las de stock no se presentan como suyas). */}
          {ownPhotos.length >= 2 && (
            <section id="galeria" className="psite-anchor mx-auto max-w-6xl px-6 pt-20">
              <SectionHeading eyebrow="Galería" title={`Así es ${site.business_name}`} color={site.color} />
              <div className="psite-gallery grid auto-rows-[160px] grid-cols-2 gap-3 sm:auto-rows-[220px] sm:grid-cols-4">
                {ownPhotos.slice(0, 8).map((src, k) => (
                  <a
                    key={src}
                    href={src}
                    target="_blank"
                    rel="noreferrer"
                    className={`overflow-hidden rounded-2xl ${k === 0 ? 'col-span-2 row-span-2' : ''}`}
                    style={cardElevationStyle(theme)}
                  >
                    <img src={src} alt={`${site.business_name} — foto ${k + 1}`} loading="lazy" className="h-full w-full object-cover" />
                  </a>
                ))}
              </div>
            </section>
          )}

          {sections.map((id) => {
            switch (id) {
              case 'beneficios':
                return <BenefitsSection key={id} businessName={site.business_name} agent={site.agent} color={site.color} theme={theme} />

              case 'opiniones':
                return stories?.length ? (
                  <section key={id} id="opiniones" className="psite-anchor max-w-6xl mx-auto px-6 pt-20 pb-4">
                    <SectionHeading eyebrow="Historias reales" title="Lo que dicen nuestros clientes" color={site.color} />
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {stories.map((s, idx) => (
                        <div
                          key={s.id}
                          className="psite-hover-lift rounded-2xl p-5 space-y-3"
                          style={{
                            background: theme.cardBg,
                            border: `1px solid ${theme.cardBorder}`,
                            animation: `psiteFadeUp 0.5s ease ${idx * 0.07}s both`,
                            ...cardElevationStyle(theme),
                            ...glowVar(site.color, theme),
                          }}
                        >
                          <div className="flex items-center gap-3">
                            <Avatar name={s.contact_name} color={site.color} />
                            <p className="text-xs" style={{ color: theme.muted }}>
                              {SENTIMENT_EMOJI[s.sentiment] ?? '🙂'} {s.contact_name ? `${s.contact_name}, cliente real` : 'Cliente real'}
                            </p>
                          </div>
                          <p className="text-sm leading-relaxed" style={{ color: theme.text }}>
                            "{s.transcription}"
                          </p>
                          <audio controls src={s.media_url} className="w-full h-9" />
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null

              case 'catalogo':
                return (
                  <Fragment key={id}>
                    {!!bestsellers.length && (
                      <section className="max-w-6xl mx-auto px-6 pt-20 pb-4">
                        <SectionHeading eyebrow="Tendencia" title="🔥 Los favoritos de nuestros clientes" color={site.color} />
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {bestsellers.map((p, idx) => (
                            <ProductCard
                              key={p.id}
                              product={p}
                              categoryFallback={site.business_category}
                              color={site.color}
                              slug={slug ?? ''}
                              theme={theme}
                              promoted={idx === 0}
                              style={{ animation: `psiteFadeUp 0.5s ease ${idx * 0.07}s both` }}
                            />
                          ))}
                        </div>
                      </section>
                    )}
                    {!!products?.length && (
                      <section id="catalogo" className="psite-anchor max-w-6xl mx-auto px-6 pt-20 pb-20">
                        <SectionHeading eyebrow="Catálogo" title="Nuestro catálogo" color={site.color} />
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {products.map((p, idx) => (
                            <ProductCard
                              key={p.id}
                              product={p}
                              categoryFallback={site.business_category}
                              color={site.color}
                              slug={slug ?? ''}
                              theme={theme}
                              style={{ animation: `psiteFadeUp 0.5s ease ${Math.min(idx, 6) * 0.05}s both` }}
                            />
                          ))}
                        </div>
                      </section>
                    )}
                  </Fragment>
                )

              case 'nosotros_horario':
                return (
                  <section key={id} className="mx-auto max-w-6xl px-6 pb-20">
                    <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
                      <div id="nosotros" className="psite-anchor relative">
                        <img
                          src={aboutPhoto}
                          alt={site.business_name}
                          loading="lazy"
                          className="aspect-[4/3] w-full rounded-3xl object-cover"
                          style={cardElevationStyle(theme)}
                        />
                        <div
                          className="absolute -bottom-5 left-5 right-5 rounded-2xl px-5 py-4 sm:left-auto sm:right-6 sm:w-72"
                          style={{ background: dark ? '#10121c' : theme.cardBg, border: `1px solid ${theme.cardBorder}`, ...cardElevationStyle(theme) }}
                        >
                          <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: site.color }}>Te atiende</p>
                          <p className="mt-1 text-sm" style={{ color: theme.text }}>
                            <strong>{site.agent}</strong>, por chat o con tu voz, a la hora que quieras.
                          </p>
                        </div>
                      </div>
                      <div className="pt-6 lg:pt-0">
                        <p className="mb-2 text-xs font-semibold uppercase tracking-widest" style={{ color: site.color }}>Sobre nosotros</p>
                        <h2 className="text-3xl font-medium sm:text-4xl" style={{ fontFamily: SITE_SERIF }}>Conoce a {site.business_name}</h2>
                        <p className="mt-4 whitespace-pre-line text-[17px] leading-relaxed" style={{ color: theme.muted }}>
                          {site.site_about ||
                            `Bienvenido a ${site.business_name}${site.city ? `, en ${site.city}` : ''}. Pregúntale a ${site.agent} lo que necesites: precios, disponibilidad, citas o pedidos. Te responde al instante.`}
                        </p>
                        <div id="horario" className="psite-anchor mt-8">
                          <BusinessHoursCard hours={site.business_hours} color={site.color} theme={theme} />
                        </div>
                      </div>
                    </div>
                  </section>
                )

              default:
                return null
            }
          })}

          {/* Cierre con foto: la última invitación a escribir. */}
          <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
            <div className="relative isolate overflow-hidden rounded-3xl px-6 py-16 text-center text-white sm:py-20">
              <img src={heroPhotos[heroPhotos.length > 2 ? 2 : 0]} alt="" loading="lazy" className="absolute inset-0 -z-20 h-full w-full object-cover" />
              <div className="absolute inset-0 -z-10" style={{ background: `linear-gradient(135deg, ${site.color}e6, rgba(0,0,0,.72))` }} />
              <p className="text-3xl font-medium sm:text-4xl" style={{ fontFamily: SITE_SERIF }}>¿Listo para escribirnos?</p>
              <p className="mx-auto mt-3 max-w-md text-white/85">Un mensaje y {site.agent} te responde al instante: precios, citas, pedidos.</p>
              <button
                type="button"
                onClick={openChat}
                className="psite-btn-primary mt-7 inline-flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-[15px] font-semibold shadow-xl"
                style={{ color: site.color }}
              >
                <MessageCircle size={18} />
                Platica con {site.agent}
              </button>
            </div>
          </section>

          <footer className="border-t px-6 pb-32 pt-10 text-sm" style={{ borderColor: theme.cardBorder, color: theme.muted }}>
            <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 text-center sm:flex-row sm:justify-between sm:text-left">
              <div className="flex items-center gap-3">
                {logoUrl ? (
                  <img src={logoUrl} alt="" className="h-10 w-10 rounded-xl object-cover" />
                ) : (
                  <span className="text-2xl">{categoryEmoji(site.business_category)}</span>
                )}
                <div>
                  <p className="font-semibold" style={{ color: theme.text }}>{site.business_name}</p>
                  {site.city && <p className="text-xs">{site.city}</p>}
                </div>
              </div>
              <div className="flex flex-col items-center gap-1 sm:items-end">
                {site.whatsapp_number && (
                  <a
                    href={`https://wa.me/${waDigits(site.whatsapp_number)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 font-medium transition-opacity hover:opacity-80"
                    style={{ color: theme.text }}
                  >
                    <MessageCircle size={14} />
                    {site.whatsapp_number}
                  </a>
                )}
                <p className="text-xs">© {new Date().getFullYear()} {site.business_name} · Página hecha con IaRadio</p>
              </div>
            </div>
          </footer>
        </div>

        {/* La mascota es el botón del chat: saluda y al tocarla abre la plática
            (3D o imagen fija según la prueba A/B, lib/mascotAb.ts). */}
        {!chatOpen && (
          <button
            type="button"
            onClick={openChat}
            aria-label={`Platicar con ${site.agent}`}
            className="press fixed right-4 z-30 flex items-end gap-1"
            style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }}
          >
            <span
              className="mb-6 max-w-[11rem] rounded-2xl rounded-br-sm px-3.5 py-2 text-left text-sm font-medium shadow-xl"
              style={{ background: dark ? '#1b1f2e' : '#fff', color: theme.text, border: `1px solid ${theme.cardBorder}` }}
            >
              ¡Hola! Soy {site.agent.split(' ')[0]} 👋 ¿Te ayudo?
            </span>
            <span
              className="flex h-[76px] w-[76px] items-center justify-center rounded-full bg-white shadow-2xl"
              style={{ boxShadow: `0 0 0 3px ${site.color}, 0 12px 32px ${site.color}66` }}
            >
              <MascotSmart mood="happy" size={70} color={site.color} allow3d={abVariant === '3d'} />
            </span>
          </button>
        )}
        {chatOpen && (
          <AgentChat
            business={{
              advertiser_id: site.advertiser_id,
              name: site.business_name,
              agent: site.agent,
              color: site.color,
              greeting: site.greeting,
              quick_asks: site.quick_asks,
            }}
            theme={theme}
            voiceBase={`/public/site/${site.slug || slug}`}
            joinPath={site.account_available && site.slug ? `/q/${site.slug}` : undefined}
            whatsappHref={site.whatsapp_number ? `https://wa.me/${waDigits(site.whatsapp_number)}` : undefined}
            prefill={null}
            mascot3d={abVariant === '3d'}
            onEvent={(e) => trackMascot(site.slug || slug, e)}
            onClose={() => setChatOpen(false)}
          />
        )}
      </div>
    </>
  )
}
