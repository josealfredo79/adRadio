import { useEffect, useRef } from 'react'

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.style.opacity = '1'
          el.style.transform = 'translateY(0)'
          observer.disconnect()
        }
      },
      { threshold: 0.12 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return ref
}

export default function ProblemSection() {
  const titleRef = useScrollReveal()
  const leftRef = useScrollReveal()
  const rightRef = useScrollReveal()

  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg-light opacity-60" />
      <div className="mx-auto max-w-5xl">
        {/* Title */}
        <div
          ref={titleRef}
          className="mb-14 text-center"
          style={{ opacity: 0, transform: 'translateY(20px)', transition: 'opacity 0.6s ease, transform 0.6s ease' }}
        >
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">El problema real</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">
            Cada mensaje sin respuesta<br />es dinero que se va
          </h2>
          <p className="mt-4 text-gray-500 text-sm max-w-md mx-auto">
            Los negocios que no automatizan pierden en promedio <strong className="text-red-400">$4,800 MXN/mes</strong> en oportunidades sin atender.
          </p>
        </div>

        {/* Before / After grid */}
        <div className="relative grid grid-cols-1 gap-6 sm:grid-cols-2">
          {/* Divider center icon */}
          <div className="hidden sm:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
            <div className="h-10 w-10 rounded-full bg-[#06060f] border border-white/10 flex items-center justify-center shadow-lg">
              <span className="text-lg">⚡</span>
            </div>
          </div>

          {/* Before */}
          <div
            ref={leftRef}
            className="rounded-3xl border border-red-500/20 bg-red-500/5 p-8"
            style={{ opacity: 0, transform: 'translateY(24px)', transition: 'opacity 0.7s ease 0.1s, transform 0.7s ease 0.1s' }}
          >
            <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-red-500/15 px-3 py-1 text-xs font-bold text-red-400 uppercase tracking-widest">
              ✗ Sin IaRadio
            </div>
            <ul className="space-y-4 text-gray-400 text-sm">
              {[
                'Contestas WhatsApp uno a uno, todo el día',
                'Olvidas contactar a clientes y pierdes ventas',
                'No tienes tiempo para pensar en publicidad',
                'Mandas el mismo mensaje a todos, sin personalizar',
                'No sabes cuántos clientes leyeron tu mensaje',
              ].map(t => (
                <li key={t} className="flex items-start gap-3">
                  <span className="mt-0.5 h-5 w-5 rounded-full bg-red-500/20 flex items-center justify-center shrink-0 text-red-400 text-xs">✗</span>
                  {t}
                </li>
              ))}
            </ul>
          </div>

          {/* After */}
          <div
            ref={rightRef}
            className="rounded-3xl border border-indigo-500/30 bg-gradient-to-br from-[#674CC4]/10 to-[#6366F1]/5 p-8"
            style={{ opacity: 0, transform: 'translateY(24px)', transition: 'opacity 0.7s ease 0.25s, transform 0.7s ease 0.25s' }}
          >
            <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-bold text-indigo-300 uppercase tracking-widest">
              ✓ Con IaRadio
            </div>
            <ul className="space-y-4 text-gray-300 text-sm">
              {[
                'El bot responde automáticamente las 24 horas',
                'Campañas programadas llegan a todos tus contactos',
                'Claude IA escribe el texto publicitario por ti',
                'Cada mensaje tiene el nombre del cliente',
                'Dashboard en tiempo real: enviados, leídos, canjeados',
              ].map(t => (
                <li key={t} className="flex items-start gap-3">
                  <span className="mt-0.5 h-5 w-5 rounded-full bg-indigo-500/20 flex items-center justify-center shrink-0 text-indigo-400 text-xs">✓</span>
                  {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}
