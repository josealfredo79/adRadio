import type { ChatPalette } from '@/lib/chatLook'
import { giroLook, hoursLines, progressOf, type Draft } from '@/lib/onboardingDraft'

// La página del negocio como tarjeta dentro del chat de IaRadio, que se va
// construyendo con cada respuesta del alta (OnboardingFlow). Lo que falta se
// ve como rayas que brillan; lo nuevo se ilumina un momento.

function money(p: number | null) {
  return p == null ? 'Pregunta' : `$${Number.isInteger(p) ? p : p.toFixed(2)}`
}

export default function OnboardingCard({
  draft, color, pal, flash, trial, published, link,
}: {
  draft: Draft
  color: string
  pal: ChatPalette
  flash: string | null
  trial: [string, string][]
  published: boolean
  link: string
}) {
  const g = giroLook(draft.business_category)
  const pct = published ? 100 : progressOf(draft)
  const where = [draft.address, draft.city].filter(Boolean).join(', ')
  const lines = hoursLines(draft.business_hours)
  const sk = (w: string) => <div className="onb-sk h-2.5 rounded-md" style={{ width: w }} />
  const just = (part: string) => (flash === part ? 'onb-flash' : '')

  return (
    <div
      className="anim-bubble mt-2 w-full max-w-[min(94%,26rem)] overflow-hidden rounded-2xl shadow-md"
      style={{ background: pal.incoming, color: pal.text, ['--c' as string]: color }}
      aria-live="polite"
    >
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold" style={{ color: pal.meta }}>
        {published ? (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">✓ Publicada</span>
        ) : (
          <span>{pct === 100 ? '✅ Tu página está lista' : '🔨 Construyendo tu página…'}</span>
        )}
        <span className="ml-auto tabular-nums">{pct}%</span>
      </div>
      <div className="h-1" style={{ background: 'color-mix(in srgb, currentColor 10%, transparent)' }}>
        <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>

      <div
        className={`relative flex min-h-[112px] flex-col justify-end gap-1 overflow-hidden px-3.5 pb-3 pt-4 text-white ${just('hero')}`}
        style={{
          background: draft.business_name || draft.business_category
            ? `linear-gradient(150deg, color-mix(in srgb, ${color} 85%, #000), color-mix(in srgb, ${color} 35%, #0e0d16))`
            : 'color-mix(in srgb, currentColor 8%, transparent)',
        }}
      >
        {draft.business_category && (
          <span aria-hidden className="pointer-events-none absolute -right-1 -top-3 rotate-[-8deg] text-[88px] opacity-30">{g.emoji}</span>
        )}
        {(draft.business_category || draft.city) && (
          <p className="text-[11px] uppercase tracking-wider opacity-85">
            {[draft.business_category, draft.city].filter(Boolean).join(' · ')}
          </p>
        )}
        {draft.business_name ? (
          <p className="text-2xl font-extrabold leading-tight">{draft.business_name}</p>
        ) : (
          <div className="grid gap-1.5">{sk('55%')}{sk('35%')}</div>
        )}
      </div>

      <section className={`grid gap-2 border-t px-3.5 py-2.5 ${just('services')}`} style={{ borderColor: 'color-mix(in srgb, currentColor 10%, transparent)' }}>
        <h4 className="text-[11px] font-bold uppercase tracking-wider" style={{ color: pal.meta }}>Lo más pedido</h4>
        {draft.services.length
          ? draft.services.slice(0, 6).map((s, i) => (
              <div key={s.name + i} className="flex items-center gap-2.5">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-lg" style={{ background: `color-mix(in srgb, ${color} 18%, transparent)` }}>{g.items[i % 3]}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">{s.name}</span>
                <span className="text-sm font-bold tabular-nums" style={{ color }}>{money(s.price)}</span>
              </div>
            ))
          : [0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-2.5">
                <span className="h-8 w-8 shrink-0 rounded-lg" style={{ background: 'color-mix(in srgb, currentColor 8%, transparent)' }} />
                {sk('65%')}
              </div>
            ))}
      </section>

      <section className={`grid gap-1 border-t px-3.5 py-2.5 ${just('hours')}`} style={{ borderColor: 'color-mix(in srgb, currentColor 10%, transparent)' }}>
        <h4 className="text-[11px] font-bold uppercase tracking-wider" style={{ color: pal.meta }}>Horario</h4>
        {lines.length ? lines.map((l) => <p key={l} className="text-sm tabular-nums">{l}</p>) : sk('60%')}
      </section>

      <section className={`grid gap-1 border-t px-3.5 py-2.5 ${just('where')}`} style={{ borderColor: 'color-mix(in srgb, currentColor 10%, transparent)' }}>
        <h4 className="text-[11px] font-bold uppercase tracking-wider" style={{ color: pal.meta }}>Dónde estamos</h4>
        {where ? <p className="text-sm">📍 {where}</p> : sk('80%')}
      </section>

      {trial.length > 0 && (
        <section className={`grid gap-1.5 border-t px-3.5 py-2.5 ${just('trial')}`} style={{ borderColor: 'color-mix(in srgb, currentColor 10%, transparent)', background: `color-mix(in srgb, ${color} 7%, transparent)` }}>
          <h4 className="text-[11px] font-bold uppercase tracking-wider" style={{ color: pal.meta }}>🧪 Prueba de tu asistente</h4>
          {trial.map(([q, a], i) => (
            <div key={i} className="grid gap-1">
              <p className="ml-auto max-w-[88%] rounded-lg px-2.5 py-1.5 text-sm" style={{ background: pal.outgoing }}>{q}</p>
              <div className="max-w-[88%] whitespace-pre-line rounded-lg border px-2.5 py-1.5 text-sm" style={{ borderColor: 'color-mix(in srgb, currentColor 12%, transparent)' }}>
                <p className="text-[11px] font-semibold" style={{ color }}>Asistente de {draft.business_name}</p>
                {a}
              </div>
            </div>
          ))}
        </section>
      )}

      <p className="truncate border-t px-3.5 py-2 text-xs" style={{ borderColor: 'color-mix(in srgb, currentColor 10%, transparent)', color: pal.meta }}>
        {link}
      </p>
    </div>
  )
}
