import { Link } from 'react-router-dom'
import { Radio, ArrowLeft } from 'lucide-react'

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-[#06060f] text-gray-300 font-sans p-5 sm:p-10">
      <div className="mx-auto max-w-4xl">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 mb-8 transition-colors">
          <ArrowLeft className="h-4 w-4" /> Volver al inicio
        </Link>
        <div className="glass rounded-3xl p-8 sm:p-12 border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="flex items-center gap-3 mb-10 pb-10 border-b border-white/10">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg">
              <Radio className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-3xl font-black text-white">Términos y Condiciones</h1>
          </div>
          
          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="text-xl font-bold text-white mb-3">1. Introducción</h2>
              <p>Bienvenido a IaRadio. Al utilizar nuestra plataforma, aceptas estos Términos y Condiciones. IaRadio proporciona un servicio de automatización de marketing y radio publicitaria por WhatsApp ("Software as a Service").</p>
            </section>
            
            <section>
              <h2 className="text-xl font-bold text-white mb-3">2. Uso Aceptable y Políticas de WhatsApp (Meta)</h2>
              <p>Nuestros usuarios deben cumplir estrictamente con las políticas de Meta Platforms, Inc. sobre el uso de WhatsApp Business. Al usar IaRadio, aceptas que:</p>
              <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-400">
                <li>Solo enviarás mensajes a usuarios que hayan dado su consentimiento previo (Opt-in) para ser contactados.</li>
                <li>Incluirás en tus mensajes una forma clara para que el destinatario pueda darse de baja (Opt-out), por ejemplo: "Responde ALTO para dejar de recibir mensajes".</li>
                <li>No utilizarás el servicio para enviar spam, mensajes engañosos, fraude o cualquier contenido ilegal.</li>
              </ul>
              <p className="mt-2 text-red-400 font-semibold">IaRadio se reserva el derecho de suspender cualquier cuenta que reciba reportes de spam excesivos o viole estas políticas, sin derecho a reembolso.</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">3. Inteligencia Artificial y Contenido Sintético</h2>
              <p>IaRadio utiliza modelos de IA de terceros (como Anthropic y ElevenLabs) para generar texto y audio. Eres responsable de utilizar estas herramientas éticamente. En muchas jurisdicciones es obligatorio declarar que el contenido ha sido generado por Inteligencia Artificial o que el interlocutor es un bot. Te recomendamos actuar con transparencia hacia tus clientes finales.</p>
            </section>
            
            <section>
              <h2 className="text-xl font-bold text-white mb-3">4. Suscripciones y Pagos (Stripe)</h2>
              <p>Ofrecemos planes de suscripción mensual procesados a través de Stripe. Al suscribirte, aceptas los cargos recurrentes. Puedes cancelar tu suscripción en cualquier momento desde tu panel de control. La cancelación evitará cobros futuros, pero no generará un reembolso por el mes en curso ya pagado, salvo que la ley local exija lo contrario.</p>
            </section>
            
            <section>
              <h2 className="text-xl font-bold text-white mb-3">5. Limitación de Responsabilidad</h2>
              <p>IaRadio no se hace responsable por bloqueos de números de WhatsApp por parte de Meta, ni por pérdidas de ingresos derivadas del uso o imposibilidad de uso de nuestra plataforma. El servicio se ofrece "tal cual" (as is) sin garantías implícitas de rendimiento.</p>
            </section>

            <p className="pt-8 text-xs text-gray-500 border-t border-white/10">Última actualización: {new Date().toLocaleDateString()}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
