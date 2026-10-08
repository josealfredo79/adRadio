import { lazy, Suspense, useCallback, useRef, useState } from 'react'
import OnboardingFlow from '@/components/OnboardingFlow'
import MascotSmart from '@/components/MascotSmart'
import type { FaceMood } from '@/components/BotFace'
import { chatPalette, wallpaperPattern } from '@/lib/chatLook'

const Mascot3D = lazy(() => import('@/components/Mascot3D'))

// "Pruébalo" de la landing: el alta del negocio pasa AQUÍ mismo — radiecito
// pregunta, la página se construye en una tarjeta y se publica con WhatsApp
// y código. Antes había una demo de voz que solo enseñaba cómo contestaría
// el bot y mandaba a /register, y aparte el chat de "Alex": mucha vuelta.
const BRAND = '#674CC4'

export default function LandingSignup() {
  const pal = chatPalette(BRAND, true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [mood, setMood] = useState<FaceMood | null>(null)
  const [run, setRun] = useState(0)
  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }))
  }, [])

  return (
    <section id="pruebalo" className="relative scroll-mt-20 px-4 py-16 sm:py-20">
      <div className="mx-auto mb-8 max-w-2xl text-center">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-indigo-300">Gratis 15 días · sin tarjeta</p>
        <h2 className="text-3xl font-black leading-tight text-white sm:text-4xl" style={{ textWrap: 'balance' }}>
          Arma tu página aquí mismo, en 5 minutos
        </h2>
        <p className="mt-3 text-gray-400">
          Cuéntale a radiecito de tu negocio, con tu voz o con botones. Mientras contestas, tu página se va construyendo.
        </p>
      </div>

      <div
        className="mx-auto flex h-[min(720px,calc(100dvh-7rem))] w-full max-w-md flex-col overflow-hidden rounded-3xl border border-white/10 shadow-2xl shadow-indigo-500/20"
        style={{ background: pal.wallpaper }}
      >
        <div className="flex items-center gap-3 px-4 py-3" style={{ background: BRAND, color: pal.onBrand }}>
          <MascotSmart mood={mood ?? 'idle'} size={40} color={BRAND} allow3d />
          <div className="min-w-0">
            <p className="font-bold leading-tight">radiecito</p>
            <p className="text-xs opacity-85">IaRadio · en línea</p>
          </div>
        </div>

        {mood && (
          <div className="flex shrink-0 justify-center py-1" style={{ background: `color-mix(in srgb, ${BRAND} 22%, #0a0f2e)` }}>
            <Suspense fallback={<div style={{ height: 150 }} />}>
              <Mascot3D mood={mood} size={130} color={BRAND} />
            </Suspense>
          </div>
        )}

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto overscroll-contain px-3 py-3"
          style={{ backgroundImage: wallpaperPattern(pal.doodle), backgroundSize: '160px 160px' }}
        >
          <OnboardingFlow
            key={run}
            pal={pal}
            brand={BRAND}
            onBrand={pal.onBrand}
            onActivity={scrollToEnd}
            // Aquí no hay otro chat al cual volver: "Salir" empieza de nuevo.
            onExit={() => setRun((n) => n + 1)}
            onVoiceMood={setMood}
            exitLabel="Empezar de nuevo"
            intro="¡Hola! Soy radiecito 📻 Te armo tu página mientras me cuentas de tu negocio. Mírala aquí abajo 👇"
          />
        </div>
      </div>

      <p className="mx-auto mt-4 max-w-md text-center text-xs text-gray-500">
        ¿Ya tienes cuenta? <a href="/login" className="underline hover:text-gray-300">Entra con tu WhatsApp</a>
      </p>
    </section>
  )
}
