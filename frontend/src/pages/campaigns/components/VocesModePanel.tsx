interface VocesModePanelProps {
  vocesCollectionPrompt: string
  onPromptChange: (val: string) => void
  rewardCoupon: boolean
  onRewardCouponChange: (val: boolean) => void
  rewardDesc: string
  onRewardDescChange: (val: string) => void
  rewardDiscount: number
  onRewardDiscountChange: (val: number) => void
  rewardHours: number
  onRewardHoursChange: (val: number) => void
  consentLine: string
  onConsentLineChange: (val: string) => void
}

const inputCls =
  'w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none'

export function VocesModePanel({
  vocesCollectionPrompt,
  onPromptChange,
  rewardCoupon,
  onRewardCouponChange,
  rewardDesc,
  onRewardDescChange,
  rewardDiscount,
  onRewardDiscountChange,
  rewardHours,
  onRewardHoursChange,
  consentLine,
  onConsentLineChange,
}: VocesModePanelProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
          📝 Solicitud para tus clientes
        </label>
        <textarea
          rows={2}
          placeholder="Ej: Mándanos un audio de 10 segundos diciendo cuál es tu platillo favorito 🎙️"
          value={vocesCollectionPrompt}
          onChange={(e) => onPromptChange(e.target.value)}
          className={`${inputCls} resize-none`}
        />
        <p className="mt-1 text-xs text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2">
          🎤 Tus contactos reciben este mensaje y responden con audios. La IA los transcribe; tú
          apruebas cuáles se publican en la página del negocio.
        </p>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
          ✍️ Línea de consentimiento (se agrega al mensaje)
        </label>
        <textarea
          rows={2}
          value={consentLine}
          onChange={(e) => onConsentLineChange(e.target.value)}
          className={`${inputCls} resize-none`}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Usa <code>{'{negocio}'}</code> para el nombre del negocio. Al mandar su nota de voz, el
          cliente acepta esto.
        </p>
      </div>

      <div className="rounded-lg border border-border p-3 space-y-3">
        <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={rewardCoupon}
            onChange={(e) => onRewardCouponChange(e.target.checked)}
          />
          🎁 Regalar un Cupón VIP al mandar su historia
        </label>
        {rewardCoupon && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-3">
              <label className="mb-1 block text-xs text-muted-foreground">Nombre del cupón</label>
              <input
                type="text"
                value={rewardDesc}
                onChange={(e) => onRewardDescChange(e.target.value)}
                placeholder="Cupón Cliente VIP"
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">% de descuento</label>
              <input
                type="number"
                min={0}
                max={100}
                value={rewardDiscount}
                onChange={(e) => onRewardDiscountChange(Number(e.target.value))}
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Vigencia (horas)</label>
              <input
                type="number"
                min={1}
                value={rewardHours}
                onChange={(e) => onRewardHoursChange(Number(e.target.value))}
                className={inputCls}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
