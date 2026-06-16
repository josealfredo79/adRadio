export default function ProblemSection() {
  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg-light opacity-60" />
      <div className="mx-auto max-w-5xl">
        <div className="mb-14 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">El problema real</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">
            Cada mensaje sin respuesta<br />es dinero que se va
          </h2>
        </div>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {/* Before */}
          <div className="rounded-3xl border border-red-500/20 bg-red-500/5 p-8">
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
          <div className="rounded-3xl border border-indigo-500/30 bg-gradient-to-br from-[#674CC4]/10 to-[#6366F1]/5 p-8">
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
