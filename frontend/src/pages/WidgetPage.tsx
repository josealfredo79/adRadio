import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Copy, CheckCheck, ExternalLink, Smartphone } from 'lucide-react'
import api from '@/lib/api'

interface SnippetData {
  snippet: string
}

export default function WidgetPage() {
  const [copied, setCopied] = useState(false)

  const { data, isLoading } = useQuery<SnippetData>({
    queryKey: ['widget-snippet'],
    queryFn: () => api.get('/widget/snippet').then(r => r.data),
    staleTime: 60_000,
  })

  const handleCopy = () => {
    if (!data?.snippet) return
    navigator.clipboard.writeText(data.snippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Widget de WhatsApp</h1>
        <p className="mt-1 text-gray-500 text-sm">
          Agrega un botón flotante de WhatsApp a tu sitio web. Copia el código y pégalo antes de{' '}
          <code className="bg-gray-100 px-1 rounded text-xs">&lt;/body&gt;</code>.
        </p>
      </div>

      {/* Preview */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 relative overflow-hidden">
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
          <Smartphone size={16} />
          Vista previa
        </div>
        <div className="bg-white border border-gray-200 rounded-lg h-48 flex items-end justify-end p-4 relative">
          <span className="text-gray-300 text-sm absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            Tu sitio web
          </span>
          {/* Simulated floating button */}
          <div className="w-14 h-14 rounded-full bg-[#25D366] flex items-center justify-center shadow-lg cursor-pointer hover:scale-105 transition-transform">
            <svg viewBox="0 0 24 24" className="w-8 h-8 fill-white">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" />
              <path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z" />
            </svg>
          </div>
        </div>
      </div>

      {/* Code snippet */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800">Código de instalación</h2>
          <button
            onClick={handleCopy}
            disabled={isLoading || !data}
            className="flex items-center gap-2 text-sm px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition"
          >
            {copied ? <CheckCheck size={16} /> : <Copy size={16} />}
            {copied ? 'Copiado!' : 'Copiar código'}
          </button>
        </div>
        {isLoading ? (
          <div className="h-32 bg-gray-100 animate-pulse rounded-lg" />
        ) : (
          <pre className="bg-gray-900 text-green-300 text-xs rounded-xl p-5 overflow-x-auto whitespace-pre-wrap leading-relaxed">
            {data?.snippet}
          </pre>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 space-y-2">
        <h3 className="font-semibold text-blue-800 text-sm">Instrucciones de instalación</h3>
        <ol className="text-sm text-blue-700 space-y-1 list-decimal list-inside">
          <li>Copia el código de arriba.</li>
          <li>Pégalo en el HTML de tu sitio web, justo antes de la etiqueta <code className="bg-blue-100 px-1 rounded">&lt;/body&gt;</code>.</li>
          <li>Guarda y publica tu sitio. El botón aparecerá en la esquina inferior derecha.</li>
        </ol>
        <a
          href="https://wa.me/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1"
        >
          <ExternalLink size={12} />
          Probar link de WhatsApp
        </a>
      </div>
    </div>
  )
}
