import { Sparkles, Radio, CalendarClock } from 'lucide-react'
import { CampaignMode, CAMPAIGN_TYPES, AUDIO_MODES, MODE_BADGE, Template, Voice } from '../types'
import { ModeSelector } from './ModeSelector'
import { BannerModePanel } from './BannerModePanel'
import { RadioModePanel } from './RadioModePanel'
import { VocesModePanel } from './VocesModePanel'
import { useCampaignForm } from '../hooks/useCampaignForm'

interface CreateCampaignModalProps {
  onClose: () => void
  formState: ReturnType<typeof useCampaignForm>
  templatesData?: Template[]
  voicesData?: Voice[]
  optimalTime?: { best_window: string; best_hour: number }
  noCredits: boolean
  onCreate: (campaignData: any) => void
  isCreatePending: boolean
  currentUser?: { business_category?: string | null; current_plan?: string } | null
}

export function CreateCampaignModal({
  onClose,
  formState,
  templatesData,
  voicesData,
  optimalTime,
  noCredits,
  onCreate,
  isCreatePending,
  currentUser,
}: CreateCampaignModalProps) {
  const {
    form,
    setForm,
    mode,
    setMode,
    generating,
    variants,
    setVariants,
    multiMessages,
    setMultiMessages,
    intent,
    setIntent,
    productDesc,
    setProductDesc,
    protagonist,
    setProtagonist,
    hasCoupon,
    setHasCoupon,
    couponDesc,
    setCouponDesc,
    couponHours,
    setCouponHours,
    radioCountry,
    setRadioCountry,
    radioAudioUrl,
    setRadioAudioUrl,
    radioScript,
    setRadioScript,
    extraContext,
    setExtraContext,
    businessCategory,
    setBusinessCategory,
    radioVoiceId,
    setRadioVoiceId,
    scheduledAt,
    setScheduledAt,
    error,
    setError,
    abEnabled,
    setAbEnabled,
    abVariants,
    setAbVariants,
    abSplit,
    setAbSplit,
    abMetric,
    setAbMetric,
    bannerPromo,
    setBannerPromo,
    bannerPalette,
    setBannerPalette,
    bannerLayout,
    setBannerLayout,
    bannerCaption,
    setBannerCaption,
    bannerPreviewUrl,
    setBannerPreviewUrl,
    bannerPreviewing,
    vocesCollectionPrompt,
    setVocesCollectionPrompt,
    generateContent,
    previewBanner,
  } = formState

  const isMultiMode = mode === 'sequence' || mode === 'saga'
  const isRadioMode = AUDIO_MODES.includes(mode)
  const isBannerMode = mode === 'banner'
  const isVocesMode = mode === 'voces'
  const planSupportsRadio = ['growth', 'pro', 'business', 'enterprise'].includes(currentUser?.current_plan ?? '')

  const readyToCreate =
    form.name &&
    ((mode === 'regular' && form.message_text) ||
      (isMultiMode && multiMessages.length > 0) ||
      (isRadioMode && !!radioAudioUrl) ||
      (isBannerMode && !!bannerPromo) ||
      (isVocesMode && !!vocesCollectionPrompt))

  const handleCreate = () => {
    const ab_test: Record<string, any> = {
      campaign_mode: mode,
      has_coupon: hasCoupon,
      coupon_description: couponDesc,
      coupon_hours: couponHours,
    }
    if (mode !== 'regular' && multiMessages.length > 0) {
      ab_test.messages = multiMessages
    }
    if (abEnabled) {
      ab_test.enabled = true
      ab_test.variants = abVariants.filter(Boolean)
      ab_test.split = abSplit
      ab_test.metric = abMetric
    }
    if (isRadioMode) {
      ab_test.audio_url = radioAudioUrl
      ab_test.radio_script = radioScript
    }
    if (mode === 'banner') {
      ab_test.promo_description = bannerPromo
      ab_test.banner_palette = bannerPalette
      ab_test.banner_layout = bannerLayout
      ab_test.banner_caption = bannerCaption
    }
    const schedule = scheduledAt ? { start_date: new Date(scheduledAt).toISOString() } : {}
    const campaignStatus = scheduledAt ? 'scheduled' : 'draft'

    onCreate({
      ...form,
      message_text: form.message_text || radioScript || bannerPromo || vocesCollectionPrompt,
      ab_test,
      schedule,
      status: campaignStatus,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-card p-6 shadow-2xl max-h-[92vh] overflow-y-auto">
        <h3 className="mb-5 text-lg font-semibold text-foreground">Nueva campaña</h3>

        <div className="space-y-4">
          {/* Template picker */}
          {templatesData && templatesData.length > 0 && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">📋 Usar template guardado</label>
              <select
                defaultValue=""
                onChange={(e) => {
                  const t = templatesData.find((x) => x.id === e.target.value)
                  if (t) setForm({ ...form, message_text: t.content })
                }}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              >
                <option value="">— Seleccionar template —</option>
                {templatesData.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                    {t.category ? ` (${t.category})` : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Nombre + tipo */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre</label>
              <input
                type="text"
                placeholder="Ej: Promo verano"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Tipo</label>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              >
                {CAMPAIGN_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Modo de campaña */}
          <ModeSelector
            currentMode={mode}
            onModeChange={(newMode) => {
              setMode(newMode)
              setVariants([])
              setMultiMessages([])
              setRadioAudioUrl('')
              setRadioScript('')
            }}
          />

          {/* Inputs según modo */}
          {mode === 'regular' && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué quieres comunicar?</label>
              <textarea
                rows={2}
                placeholder="Ej: 30% de descuento este fin de semana"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Puedes usar <code>{'{{nombre}}'}</code>, <code>{'{{ciudad}}'}</code> en el mensaje para personalización automática
              </p>
            </div>
          )}
          {mode === 'sequence' && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué historia cuenta la secuencia?</label>
              <textarea
                rows={2}
                placeholder="Ej: Lanzamiento de nuevos platillos de temporada"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
              />
              <p className="mt-1 text-xs text-muted-foreground">Claude creará 3 mensajes para días 1, 3 y 5</p>
            </div>
          )}
          {mode === 'saga' && (
            <div className="space-y-3">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué producto/servicio protagoniza la saga?</label>
                <textarea
                  rows={2}
                  placeholder="Ej: Clases de yoga para mamás con poco tiempo"
                  value={productDesc}
                  onChange={(e) => setProductDesc(e.target.value)}
                  className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre del protagonista</label>
                <input
                  type="text"
                  value={protagonist}
                  onChange={(e) => setProtagonist(e.target.value)}
                  className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                />
              </div>
              <p className="text-xs text-muted-foreground">Claude creará 4 episodios semanales al estilo radionovela 📻</p>
            </div>
          )}

          {isBannerMode && (
            <BannerModePanel
              bannerPromo={bannerPromo}
              setBannerPromo={setBannerPromo}
              bannerPalette={bannerPalette}
              setBannerPalette={setBannerPalette}
              bannerLayout={bannerLayout}
              setBannerLayout={setBannerLayout}
              bannerCaption={bannerCaption}
              setBannerCaption={setBannerCaption}
              bannerPreviewUrl={bannerPreviewUrl}
              bannerPreviewing={bannerPreviewing}
              onPreview={() => previewBanner(currentUser?.business_category || undefined)}
            />
          )}

          {isRadioMode && (
            <RadioModePanel
              mode={mode}
              intent={intent}
              setIntent={setIntent}
              extraContext={extraContext}
              setExtraContext={setExtraContext}
              businessCategory={businessCategory}
              setBusinessCategory={setBusinessCategory}
              radioCountry={radioCountry}
              setRadioCountry={setRadioCountry}
              radioVoiceId={radioVoiceId}
              setRadioVoiceId={setRadioVoiceId}
              voicesData={voicesData}
              radioAudioUrl={radioAudioUrl}
              radioScript={radioScript}
              planSupportsRadio={planSupportsRadio}
            />
          )}

          {isVocesMode && (
            <VocesModePanel
              vocesCollectionPrompt={vocesCollectionPrompt}
              onPromptChange={(val) => {
                setVocesCollectionPrompt(val)
                setForm({ ...form, message_text: val })
              }}
            />
          )}

          {/* Botón generar */}
          {!isRadioMode && !isVocesMode && !isBannerMode && (
            <button
              type="button"
              onClick={generateContent}
              disabled={generating || !form.name || (mode !== 'saga' && !intent) || (mode === 'saga' && !productDesc)}
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {generating ? 'Generando con Claude...' : mode === 'regular' ? 'Generar 3 variantes' : mode === 'sequence' ? 'Generar secuencia' : 'Generar saga'}
            </button>
          )}
          {isRadioMode && (
            <button
              type="button"
              onClick={generateContent}
              disabled={generating || !form.name || !intent || !planSupportsRadio}
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60 transition-colors"
              title={!planSupportsRadio ? 'Actualiza a Growth o superior para usar cuñas de radio' : ''}
            >
              <Radio className="h-3.5 w-3.5" />
              {generating ? 'Generando cuña...' : radioAudioUrl ? `Regenerar ${MODE_BADGE[mode] || 'cuña'}` : `Generar ${MODE_BADGE[mode] || 'cuña de radio'}`}
            </button>
          )}

          {/* Variantes — modo regular */}
          {mode === 'regular' && variants.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-gray-700">Selecciona una variante:</p>
              {variants.map((v, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setForm({ ...form, message_text: v })}
                  className={`w-full rounded-lg border p-3 text-left text-sm transition-all ${
                    form.message_text === v
                      ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-300'
                      : 'border-border hover:border-brand-300 hover:bg-muted'
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          )}

          {/* Preview — modo secuencia o saga */}
          {isMultiMode && multiMessages.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-gray-700">
                {mode === 'sequence' ? '📻 Secuencia generada (3 mensajes)' : '🎭 Saga generada (4 episodios)'}
              </p>
              {multiMessages.map((msg, i) => (
                <div key={i} className="rounded-lg border border-border bg-muted p-3">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    {mode === 'sequence' ? `Día ${[1, 3, 5][i] ?? i + 1}` : `Semana ${i + 1}`}
                  </p>
                  <textarea
                    rows={3}
                    value={msg}
                    onChange={(e) => {
                      const updated = [...multiMessages]
                      updated[i] = e.target.value
                      setMultiMessages(updated)
                    }}
                    className="w-full rounded border border-border bg-card px-2.5 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none"
                  />
                </div>
              ))}
            </div>
          )}

          {/* Mensaje final — solo en regular */}
          {mode === 'regular' && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Mensaje final</label>
              <textarea
                rows={3}
                placeholder="El mensaje que recibirán tus clientes..."
                value={form.message_text}
                onChange={(e) => setForm({ ...form, message_text: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
              />
            </div>
          )}

          {/* Cupón */}
          <div className={`rounded-xl border p-4 transition-all ${hasCoupon ? 'border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'border-border'}`}>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={hasCoupon}
                onChange={(e) => setHasCoupon(e.target.checked)}
                className="h-4 w-4 rounded border-border text-amber-500"
              />
              <span className="text-sm font-medium text-gray-700">🎫 Incluir cupón con expiración</span>
            </label>
            {hasCoupon && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Descripción del cupón</label>
                  <input
                    type="text"
                    placeholder="Ej: 20% de descuento"
                    value={couponDesc}
                    onChange={(e) => setCouponDesc(e.target.value)}
                    className="w-full rounded-lg border border-amber-200 px-3 py-2 text-sm focus:border-amber-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Válido por (horas)</label>
                  <select
                    value={couponHours}
                    onChange={(e) => setCouponHours(Number(e.target.value))}
                    className="w-full rounded-lg border border-amber-200 px-3 py-2 text-sm focus:border-amber-400 focus:outline-none"
                  >
                    <option value={24}>24 horas</option>
                    <option value={48}>48 horas</option>
                    <option value={72}>72 horas</option>
                    <option value={168}>1 semana</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Prueba A/B */}
          <div className={`rounded-xl border p-4 transition-all ${abEnabled ? 'border-purple-300 bg-purple-50 dark:bg-purple-950/30' : 'border-border'}`}>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={abEnabled}
                onChange={(e) => setAbEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-border text-purple-500"
              />
              <span className="text-sm font-medium text-gray-700">🔬 Prueba A/B</span>
            </label>
            {abEnabled && (
              <div className="mt-3 space-y-3">
                {abVariants.map((v, i) => (
                  <div key={i}>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                      Variante {String.fromCharCode(65 + i)}
                    </label>
                    <textarea
                      rows={2}
                      placeholder={`Mensaje variante ${String.fromCharCode(65 + i)}...`}
                      value={v}
                      onChange={(e) => {
                        const updated = [...abVariants]
                        updated[i] = e.target.value
                        setAbVariants(updated)
                      }}
                      className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none resize-none"
                    />
                  </div>
                ))}
                {abVariants.length < 3 && (
                  <button
                    type="button"
                    onClick={() => setAbVariants([...abVariants, ''])}
                    className="text-xs text-purple-600 hover:text-purple-700 dark:text-purple-300 font-medium"
                  >
                    + Añadir variante C
                  </button>
                )}
                {abVariants.length === 3 && (
                  <button
                    type="button"
                    onClick={() => setAbVariants(abVariants.slice(0, 2))}
                    className="text-xs text-red-500 hover:text-red-600 font-medium"
                  >
                    - Quitar variante C
                  </button>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">División</label>
                    <select
                      value={abSplit}
                      onChange={(e) => setAbSplit(e.target.value)}
                      className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none"
                    >
                      <option value="50/50">50% / 50%</option>
                      <option value="70/30">70% / 30%</option>
                      <option value="33/33/34">33% / 33% / 34%</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Métrica</label>
                    <select
                      value={abMetric}
                      onChange={(e) => setAbMetric(e.target.value)}
                      className="w-full rounded-lg border border-purple-200 dark:border-purple-800 px-3 py-2 text-sm focus:border-purple-400 focus:outline-none"
                    >
                      <option value="response">Tasa de respuesta</option>
                      <option value="clicks">Tasa de clics</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Programación */}
          <div className="rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4">
            <label className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-800 dark:text-blue-200">
              <CalendarClock className="h-4 w-4" />
              Programar envío (opcional)
            </label>
            {optimalTime && (
              <p className="mb-2 text-xs text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/50 rounded-lg px-3 py-2">
                💡 Tus contactos responden más entre las <strong>{optimalTime.best_window}</strong> — considera enviarlo en ese horario.
              </p>
            )}
            <input
              type="datetime-local"
              value={scheduledAt}
              min={new Date().toISOString().slice(0, 16)}
              onChange={(e) => setScheduledAt(e.target.value)}
              className="w-full rounded-lg border border-blue-200 dark:border-blue-800 bg-card px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
            />
            {scheduledAt && (
              <p className="mt-1.5 text-xs text-blue-600 dark:text-blue-300">
                La campaña se enviará el {new Date(scheduledAt).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
              </p>
            )}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          {!scheduledAt && (
            <p className="text-xs text-muted-foreground">
              La campaña se guardará como borrador. Después podrás enviarla desde el listado.
            </p>
          )}
        </div>

        <div className="mt-5 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border border-border py-2.5 text-sm text-gray-700 hover:bg-muted dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={isCreatePending || !readyToCreate}
            className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
          >
            {isCreatePending ? 'Creando...' : scheduledAt ? 'Programar campaña' : 'Crear campaña'}
          </button>
        </div>
      </div>
    </div>
  )
}
