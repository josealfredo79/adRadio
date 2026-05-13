import { Link } from 'react-router-dom'
import { Radio, ArrowLeft } from 'lucide-react'

export default function PrivacyPage() {
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
            <h1 className="text-3xl font-black text-white">Política de Privacidad</h1>
          </div>
          
          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="text-xl font-bold text-white mb-3">1. Información que recopilamos</h2>
              <p>Recopilamos información cuando te registras en IaRadio, creas una suscripción o usas nuestros servicios. Esto incluye:</p>
              <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-400">
                <li>Información de la cuenta (nombre, correo electrónico, nombre de la empresa).</li>
                <li>Datos de facturación (procesados de forma segura por Stripe; IaRadio no almacena números de tarjetas de crédito).</li>
                <li>Información de uso de la plataforma.</li>
              </ul>
            </section>
            
            <section>
              <h2 className="text-xl font-bold text-white mb-3">2. Base de Datos de tus Clientes (Procesamiento de Datos)</h2>
              <p>Como usuario de IaRadio, subirás contactos (números de teléfono y nombres) de tus propios clientes. En este contexto, IaRadio actúa exclusivamente como "Procesador de Datos" y tú eres el "Controlador de Datos".</p>
              <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-400">
                <li>Garantizamos que la base de datos que subes es privada y tuya.</li>
                <li>IaRadio no venderá, alquilará ni utilizará los contactos de tus clientes para fines ajenos a tu cuenta.</li>
                <li>Es tu responsabilidad legal asegurar que has obtenido dichos datos de manera lícita y con el consentimiento necesario.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">3. Uso de la Información</h2>
              <p>Utilizamos la información recopilada para:</p>
              <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-400">
                <li>Proveer y mantener nuestro servicio.</li>
                <li>Procesar tus pagos y gestionar tu suscripción.</li>
                <li>Enviar avisos técnicos, actualizaciones de seguridad y soporte.</li>
              </ul>
            </section>
            
            <section>
              <h2 className="text-xl font-bold text-white mb-3">4. Compartir con Terceros</h2>
              <p>No compartimos tu información personal con terceros, excepto con proveedores de servicios necesarios para el funcionamiento de la plataforma (como Stripe para pagos, Cloudflare para almacenamiento, Twilio para mensajería, y servicios de IA como Anthropic, OpenAI, Voyage AI y Fish Audio para procesar textos y audios). Estos proveedores están sujetos a estrictas obligaciones de confidencialidad.</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">5. Seguridad de los Datos</h2>
              <p>Implementamos medidas de seguridad estándar de la industria (como encriptación de contraseñas usando bcrypt y conexiones seguras HTTPS) para proteger tu información y la de tus clientes contra acceso no autorizado, alteración o destrucción.</p>
            </section>

            <p className="pt-8 text-xs text-gray-500 border-t border-white/10">Última actualización: {new Date().toLocaleDateString()}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
