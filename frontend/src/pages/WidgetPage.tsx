import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, CheckCheck, ExternalLink, Smartphone, Palette, MessageSquare, MoveHorizontal, Save } from 'lucide-react'
import api from '@/lib/api'
import SEO from '@/components/SEO'

interface SnippetData {
  snippet: string
}

interface WidgetConfig {
  color: string
  greeting: string
  position: 'left' | 'right'
}

const PRESET_COLORS = [
  '#25D366', '#674CC4', '#3B82F6', '#EC4899', '#F59E0B', '#EF4444',
]

export default function WidgetPage() {
  const qc = useQueryClient()
  const [copied, setCopied] = useState(false)

  const { data: snippet, isLoading } = useQuery<SnippetData>({
    queryKey: ['widget-snippet'],
    queryFn: () => api.get('/widget/snippet').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: config } = useQuery<WidgetConfig>({
    queryKey: ['widget-config'],
    queryFn: () => api.get('/widget/config').then(r => r.data),
    staleTime: 60_000,
  })

  const [form, setForm] = useState<WidgetConfig | null>(null)

  const configData = form ?? config ?? { color: '#25D366', greeting: '¡Hola! ¿En qué puedo ayudarte?', position: 'right' }

  const saveMutation = useMutation({
    mutationFn: (data: WidgetConfig) => api.put('/widget/config', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['widget-config'] })
      qc.invalidateQueries({ queryKey: ['widget-snippet'] })
    },
  })

  const handleCopy = () => {
    if (!snippet?.snippet) return
    navigator.clipboard.writeText(snippet.snippet)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <SEO title="Widget" description="Panel de control de IaRadio." noIndex />
      <div className="max-w-4xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Widget de chat</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400 text-sm">
          Agrega un botón flotante a tu sitio web. Tus visitantes chatean directo ahí con tu bot (usando tu base de conocimiento) sin salir de tu página — no depende de tener WhatsApp conectado. Personaliza colores, saludo y posición.
        </p>
      </div>

      {/* Customization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Preview */}
        <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 relative overflow-hidden order-2 lg:order-1">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-4">
            <Smartphone size={16} />
            Vista previa en vivo
          </div>
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg h-80 flex items-end justify-end p-4 relative overflow-hidden">
            <span className="text-gray-300 dark:text-gray-600 text-sm absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
              Tu sitio web
            </span>
            {/* Simulated popup — greeting can run up to 200 chars, so this can
                grow tall; bottom-16 + overflow-hidden on the mockup above
                keep it from overlapping the "Vista previa" label past the box. */}
            <div
              className={`absolute bottom-16 ${configData.position === 'left' ? 'left-6' : 'right-6'} w-64 rounded-2xl bg-white dark:bg-gray-950 shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden`}
            >
              <div className="flex items-center gap-2 px-4 py-3" style={{ background: configData.color }}>
                <div className="w-9 h-9 rounded-full bg-white/25 flex items-center justify-center text-lg shrink-0">🎙️</div>
                <div className="text-white text-left">
                  <p className="text-sm font-bold leading-tight">Asistente</p>
                  <p className="text-xs opacity-80">En línea</p>
                </div>
              </div>
              <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900">
                <div
                  className="bg-white dark:bg-gray-950 rounded-r-xl rounded-bl-xl px-3 py-2 text-sm text-gray-700 dark:text-gray-300 shadow-sm max-w-[85%]"
                >
                  {configData.greeting}
                </div>
              </div>
              <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800">
                <a
                  className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-white text-sm font-semibold"
                  style={{ background: configData.color }}
                >
                  <svg viewBox="0 0 24 24" className="w-4 h-4 fill-white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>
                  Chatear por WhatsApp
                </a>
              </div>
            </div>
            {/* Simulated floating button */}
            <div
              className={`absolute bottom-6 ${configData.position === 'left' ? 'left-6' : 'right-6'} w-14 h-14 rounded-full flex items-center justify-center shadow-lg cursor-pointer transition-transform hover:scale-105`}
              style={{ background: configData.color }}
            >
              <svg viewBox="0 0 24 24" className="w-8 h-8 fill-white">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" />
                <path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z" />
              </svg>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-5 order-1 lg:order-2">
          {/* Color */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <Palette size={16} />
              Color del widget
            </div>
            <div className="flex flex-wrap gap-2">
              {PRESET_COLORS.map(c => (
                <button
                  key={c}
                  onClick={() => setForm(prev => ({ ...(prev ?? configData), color: c }))}
                  className={`w-9 h-9 rounded-full border-2 transition-all ${configData.color === c ? 'border-gray-800 scale-110' : 'border-transparent'}`}
                  style={{ background: c }}
                />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 dark:text-gray-500">o hex:</span>
              <input
                type="text"
                value={configData.color}
                onChange={e => setForm(prev => ({ ...(prev ?? configData), color: e.target.value }))}
                className="w-24 rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1.5 text-xs font-mono focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none"
                maxLength={7}
              />
            </div>
          </div>

          {/* Greeting */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <MessageSquare size={16} />
              Saludo
            </div>
            <textarea
              value={configData.greeting}
              onChange={e => setForm(prev => ({ ...(prev ?? configData), greeting: e.target.value }))}
              maxLength={200}
              rows={2}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none resize-none"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 text-right">{configData.greeting.length}/200</p>
          </div>

          {/* Position */}
          <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <MoveHorizontal size={16} />
              Posición
            </div>
            <div className="flex gap-2">
              {(['left', 'right'] as const).map(pos => (
                <button
                  key={pos}
                  onClick={() => setForm(prev => ({ ...(prev ?? configData), position: pos }))}
                  className={`flex-1 rounded-lg py-2 text-sm font-medium border transition-colors ${
                    configData.position === pos
                      ? 'border-brand-500 dark:border-brand-400 bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-300'
                      : 'border-gray-200 dark:border-gray-800 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {pos === 'left' ? 'Izquierda' : 'Derecha'}
                </button>
              ))}
            </div>
          </div>

          {/* Save */}
          <button
            onClick={() => {
              if (!form) return
              saveMutation.mutate(form)
              setForm(null)
            }}
            disabled={!form || saveMutation.isPending}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand-500 dark:bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition-colors"
          >
            <Save size={16} />
            {saveMutation.isPending ? 'Guardando...' : 'Guardar cambios'}
          </button>
          {saveMutation.isSuccess && <p className="text-sm text-green-600 dark:text-green-400 font-medium text-center">✓ Widget actualizado</p>}
        </div>
      </div>

      {/* Code snippet */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800 dark:text-gray-200">Código de instalación</h2>
          <button
            onClick={handleCopy}
            disabled={isLoading || !snippet}
            className="flex items-center gap-2 text-sm px-4 py-2 bg-brand-500 dark:bg-brand-600 text-white rounded-lg hover:bg-brand-600 dark:hover:bg-brand-500 disabled:opacity-50 transition"
          >
            {copied ? <CheckCheck size={16} /> : <Copy size={16} />}
            {copied ? 'Copiado!' : 'Copiar código'}
          </button>
        </div>
        {isLoading ? (
          <div className="h-32 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-lg" />
        ) : (
          <pre className="bg-gray-900 text-green-300 text-xs rounded-xl p-5 overflow-x-auto whitespace-pre-wrap leading-relaxed">
            {snippet?.snippet}
          </pre>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl p-5 space-y-2">
        <h3 className="font-semibold text-blue-800 dark:text-blue-200 text-sm">Instrucciones de instalación</h3>
        <ol className="text-sm text-blue-700 dark:text-blue-300 space-y-1 list-decimal list-inside">
          <li>Copia el código de arriba.</li>
          <li>Pégalo en el HTML de tu sitio web, justo antes de la etiqueta <code className="bg-blue-100 dark:bg-blue-900/50 px-1 rounded">&lt;/body&gt;</code>.</li>
          <li>Guarda y publica tu sitio. El botón aparecerá en la esquina inferior {configData.position === 'left' ? 'izquierda' : 'derecha'}.</li>
        </ol>
        <a
          href="https://wa.me/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1"
        >
          <ExternalLink size={12} />
          Probar link de WhatsApp
        </a>
      </div>
    </div>
    </>
  )
}
