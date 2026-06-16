export default function IntegrationsSection() {
  const INTEGRATIONS = [
    { label: 'WhatsApp Business', color: 'text-green-400', emoji: '🟢' },
    { label: 'Claude IA (Anthropic)', color: 'text-orange-400', emoji: '🤖' },
    { label: 'Twilio', color: 'text-red-400', emoji: '📞' },
    { label: 'Stripe', color: 'text-blue-400', emoji: '💳' },
    { label: 'Voyage AI', color: 'text-purple-400', emoji: '🧠' },
    { label: 'Cloudflare R2', color: 'text-orange-300', emoji: '☁️' },
  ]

  return (
    <section className="px-5 py-16 border-y border-white/5">
      <div className="mx-auto max-w-4xl text-center">
        <p className="mb-8 text-sm font-semibold uppercase tracking-widest text-gray-600">Integrado con las mejores herramientas</p>
        <div className="flex flex-wrap items-center justify-center gap-6">
          {INTEGRATIONS.map(i => (
            <div key={i.label} className="glass rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm font-medium text-gray-400">
              <span>{i.emoji}</span> {i.label}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
