import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import SEO from '@/components/SEO'
import BrandMark from '@/components/BrandMark'

// URL declarada en Meta for Developers → Configuración → Básica
// ("URL de instrucciones de eliminación de datos"). No cambiar la ruta sin
// actualizarla también allá.
export default function DataDeletionPage() {
  return (
    <>
      <SEO title="Eliminación de datos" description="Cómo solicitar la eliminación de tus datos en IaRadio." />
      <div className="min-h-screen bg-[#06060f] text-gray-300 font-sans p-5 sm:p-10">
      <div className="mx-auto max-w-4xl">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 mb-8 transition-colors">
          <ArrowLeft className="h-4 w-4" /> Volver al inicio
        </Link>
        <div className="glass rounded-3xl p-8 sm:p-12 border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="flex items-center gap-3 mb-10 pb-10 border-b border-white/10">
            <BrandMark className="h-12 w-12 shadow-lg rounded-[22%]" />
            <h1 className="text-3xl font-black text-white">Eliminación de datos</h1>
          </div>

          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="text-xl font-bold text-white mb-3">1. Cómo solicitar la eliminación</h2>
              <p>Puedes pedir que eliminemos tu cuenta de IaRadio y todos los datos asociados en cualquier momento:</p>
              <ol className="list-decimal pl-5 mt-2 space-y-1 text-gray-400">
                <li>Envía un correo a <a href="mailto:iaradio@iaradio.online?subject=Solicitud%20de%20eliminaci%C3%B3n%20de%20datos" className="text-indigo-400 underline">iaradio@iaradio.online</a> con el asunto "Solicitud de eliminación de datos".</li>
                <li>Escríbelo desde el correo con el que te registraste, para que podamos confirmar que la cuenta es tuya.</li>
                <li>Te confirmaremos la recepción y completaremos la eliminación en un plazo máximo de 30 días.</li>
              </ol>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">2. Qué se elimina</h2>
              <ul className="list-disc pl-5 mt-2 space-y-1 text-gray-400">
                <li>Tu cuenta: nombre, correo electrónico y datos de la empresa.</li>
                <li>La conexión con WhatsApp Business: los identificadores de tu cuenta de WhatsApp Business (WABA), del número de teléfono y los tokens de acceso de Meta.</li>
                <li>Los contactos de tus clientes, las conversaciones, las campañas, las citas y el contenido generado (textos y audios).</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">3. Qué conservamos</h2>
              <p>Solo conservamos lo que la ley nos obliga a guardar, como los registros de facturación con fines fiscales. Los datos de pago los procesa Stripe; IaRadio nunca almacena números de tarjeta.</p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-white mb-3">4. Revocar el acceso desde Facebook</h2>
              <p>También puedes quitarle a IaRadio el acceso a tu cuenta de Meta desde Facebook, en <strong>Configuración y privacidad → Configuración → Integraciones comerciales</strong>. Eso corta el acceso de inmediato, pero no borra los datos que ya estén en IaRadio. Para borrarlos, sigue el paso 1.</p>
            </section>

            <section lang="en">
              <h2 className="text-xl font-bold text-white mb-3">Data deletion (English)</h2>
              <p>To delete your IaRadio account and all associated data, email <a href="mailto:iaradio@iaradio.online?subject=Data%20deletion%20request" className="text-indigo-400 underline">iaradio@iaradio.online</a> from your registered address with the subject "Data deletion request". We delete your account, your WhatsApp Business connection (WABA and phone number IDs, Meta access tokens), your customer contacts, conversations, campaigns and generated content within 30 days, keeping only the billing records the law requires us to keep.</p>
            </section>

            <p className="pt-8 text-xs text-gray-500 border-t border-white/10">Ver también la <Link to="/privacy" className="text-indigo-400 underline">Política de Privacidad</Link>.</p>
          </div>
        </div>
      </div>
    </div>
    </>
  )
}
