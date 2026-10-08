import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import AgentChat from '@/components/AgentChat'
import { getSiteTheme } from '@/pages/publicSite/theme'

// "Pruébalo" de la landing: el bot ORIGINAL de IaRadio (el de /sitio/iaradio),
// incrustado aquí. Primero platica y resuelve dudas; el alta del negocio
// empieza solo cuando la persona toca "✨ Quiero probarlo gratis" (y ahí
// mismo se construye su página y la publica). Antes había una demo de voz
// que mandaba a /register y aparte el chat de "Alex": mucha vuelta.
const SLUG = 'iaradio'

interface SiteForChat {
  advertiser_id: string
  business_name: string
  agent: string
  color: string
  greeting: string
  site_theme: string
  quick_asks?: { icon: string; text: string; action?: string }[] | null
}

export default function LandingSignup() {
  const { data: site } = useQuery<SiteForChat>({
    queryKey: ['landing-chat', SLUG],
    queryFn: () => api.get(`/public/site/${SLUG}`).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  })

  return (
    <section id="pruebalo" className="relative scroll-mt-20 px-4 py-16 sm:py-20">
      <div className="mx-auto mb-8 max-w-2xl text-center">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-indigo-300">Gratis 15 días · sin tarjeta</p>
        <h2 className="text-3xl font-black leading-tight text-white sm:text-4xl" style={{ textWrap: 'balance' }}>
          Platica con IaRadio y arma tu página aquí mismo
        </h2>
        <p className="mt-3 text-gray-400">
          Pregúntale lo que quieras de IaRadio. Cuando quieras tu página, toca “Quiero probarlo gratis” y se construye mientras le cuentas de tu negocio.
        </p>
      </div>

      <div className="relative mx-auto h-[min(720px,calc(100dvh-7rem))] w-full max-w-md overflow-hidden rounded-3xl border border-white/10 shadow-2xl shadow-indigo-500/20">
        {site ? (
          <AgentChat
            layout="pane"
            business={{
              advertiser_id: site.advertiser_id,
              name: site.business_name,
              agent: site.agent,
              color: site.color,
              greeting: site.greeting,
              quick_asks: site.quick_asks,
            }}
            theme={getSiteTheme(site.site_theme)}
            voiceBase={`/public/site/${SLUG}`}
            prefill={null}
            onClose={() => {}}
          />
        ) : (
          <div className="flex h-full items-center justify-center bg-[#0b141a] text-sm text-gray-400">Cargando a IaRadio…</div>
        )}
      </div>

      <p className="mx-auto mt-4 max-w-md text-center text-xs text-gray-500">
        ¿Ya tienes cuenta? <a href="/login" className="underline hover:text-gray-300">Entra con tu WhatsApp</a>
      </p>
    </section>
  )
}
