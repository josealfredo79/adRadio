import { AlertCircle } from 'lucide-react'
import { CampaignMode, MODE_BADGE, Voice } from '../types'

interface RadioModePanelProps {
  mode: CampaignMode
  intent: string
  setIntent: (val: string) => void
  extraContext: string
  setExtraContext: (val: string) => void
  businessCategory: string
  setBusinessCategory: (val: string) => void
  radioCountry: string
  setRadioCountry: (val: string) => void
  radioVoiceId: string
  setRadioVoiceId: (val: string) => void
  voicesData?: Voice[]
  radioAudioUrl: string
  radioScript: string
  planSupportsRadio?: boolean
}

export function RadioModePanel({
  mode,
  intent,
  setIntent,
  extraContext,
  setExtraContext,
  businessCategory,
  setBusinessCategory,
  radioCountry,
  setRadioCountry,
  radioVoiceId,
  setRadioVoiceId,
  voicesData,
  radioAudioUrl,
  radioScript,
  planSupportsRadio = true,
}: RadioModePanelProps) {
  return (
    <div className="space-y-3">
      {!planSupportsRadio && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4 space-y-2">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">🔒 Cuñas de radio no disponibles</p>
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Tu plan no incluye cuñas de radio.
            <a href="/app/plans" className="ml-1 font-medium underline hover:text-amber-800 dark:hover:text-amber-200">
              Actualiza a Growth o superior
            </a>
            {' '}para usar esta función.
          </p>
        </div>
      )}
      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
          {mode === 'comunitaria'
            ? '¿Qué valor genuino puede dar tu negocio?'
            : mode === 'capsula'
            ? '¿Sobre qué tema quieres el dato sorprendente?'
            : mode === 'trivia'
            ? '¿Sobre qué área será la pregunta?'
            : mode === 'historia'
            ? '¿Qué problema resuelve tu negocio?'
            : mode === 'alerta'
            ? '¿Cuál es el tema de la alerta?'
            : mode === 'estacional'
            ? '¿Qué ángulo de tu negocio esta temporada?'
            : '¿Qué quieres anunciar?'}
        </label>
        <textarea
          rows={2}
          placeholder={
            mode === 'comunitaria'
              ? 'Ej: Restaurante vegano — tips de alimentación saludable'
              : mode === 'capsula'
              ? 'Ej: farmacia — datos curiosos de salud'
              : mode === 'trivia'
              ? 'Ej: cocina mexicana, historia, salud'
              : mode === 'historia'
              ? 'Ej: dolor de espalda, falta de tiempo para cocinar'
              : mode === 'alerta'
              ? 'Ej: temporada de lluvias, calor extremo, quincena'
              : mode === 'estacional'
              ? 'Ej: regreso a clases, ofertas de fin de año'
              : 'Ej: Gran remate de zapatos, 50% de descuento sólo este sábado'
          }
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
        />
        {mode === 'comunitaria' && (
          <p className="mt-1 text-xs text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950/30 rounded-lg px-3 py-2">
            🌿 El guión primero dará un consejo útil relacionado con tu categoría, luego mencionará tu negocio con honestidad — como la radio que educaba antes de vender.
          </p>
        )}
        {mode === 'capsula' && (
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-2">
            💡 Un dato real y sorprendente que el oyente no esperaba saber, seguido de la mención natural de tu negocio.
          </p>
        )}
        {mode === 'trivia' && (
          <p className="mt-1 text-xs text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2">
            🧠 Pregunta curiosa → el oyente responde por WhatsApp → interacción natural con tu negocio.
          </p>
        )}
        {mode === 'historia' && (
          <p className="mt-1 text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/30 rounded-lg px-3 py-2">
            📖 Mini radionovela de 30s: un personaje con un problema real y tu negocio como la solución creíble.
          </p>
        )}
        {mode === 'alerta' && (
          <p className="mt-1 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
            🚨 Información oportuna que el oyente necesita HOY, conectada naturalmente con tu negocio.
          </p>
        )}
        {mode === 'estacional' && (
          <p className="mt-1 text-xs text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-950/30 rounded-lg px-3 py-2">
            🗓️ El mensaje correcto en el momento correcto — conecta tu negocio con lo que la gente ya está viviendo.
          </p>
        )}
      </div>

      {/* Extra context — trivia (premio), alerta/estacional (fecha/temporada) */}
      {(mode === 'trivia' || mode === 'alerta' || mode === 'estacional') && (
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
            {mode === 'trivia'
              ? '🎁 Premio mencionado en la trivia'
              : mode === 'alerta'
              ? '📅 Contexto actual (fecha, clima, evento)'
              : '📅 Temporada o momento del año'}
          </label>
          <input
            type="text"
            placeholder={
              mode === 'trivia'
                ? 'Ej: un 20% de descuento en tu próxima compra'
                : mode === 'alerta'
                ? 'Ej: Temporada de lluvias en Guadalajara'
                : 'Ej: Regreso a clases, Navidad, quincena'
            }
            value={extraContext}
            onChange={(e) => setExtraContext(e.target.value)}
            className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          />
        </div>
      )}

      {/* Categoría del negocio */}
      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Categoría del negocio (opcional)</label>
        <input
          type="text"
          placeholder="Ej: farmacia, restaurante, gimnasio, inmobiliaria..."
          value={businessCategory}
          onChange={(e) => setBusinessCategory(e.target.value)}
          className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">País / acento del locutor</label>
        <select
          value={radioCountry}
          onChange={(e) => setRadioCountry(e.target.value)}
          className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
        >
          <option value="mx">🇲🇽 México</option>
          <option value="co">🇨🇴 Colombia</option>
          <option value="ar">🇦🇷 Argentina</option>
          <option value="es">🇪🇸 España</option>
        </select>
      </div>

      {voicesData && voicesData.length > 0 && (
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Voz del locutor</label>
          <select
            value={radioVoiceId}
            onChange={(e) => setRadioVoiceId(e.target.value)}
            className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="">— Por defecto según país —</option>
            {voicesData.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.gender === 'female' ? 'Femenina' : 'Masculina'})
              </option>
            ))}
          </select>
        </div>
      )}

      {!radioAudioUrl && (
        <p className="text-xs text-muted-foreground">
          Claude escribe el guión → voz de locutor → audio .ogg listo para WhatsApp {MODE_BADGE[mode]?.split(' ')[0] || '🎙️'}
        </p>
      )}

      {radioAudioUrl && (
        <div className="rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-4 space-y-2">
          <p className="text-sm font-medium text-green-700 dark:text-green-300">{MODE_BADGE[mode] || '✅'} Cuña generada</p>
          <audio controls src={radioAudioUrl} className="w-full" />
          {radioScript && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium">Ver guión</summary>
              <p className="mt-2 whitespace-pre-wrap">{radioScript}</p>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
