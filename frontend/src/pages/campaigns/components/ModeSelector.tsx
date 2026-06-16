import { CampaignMode, CAMPAIGN_MODES } from '../types'

interface ModeSelectorProps {
  currentMode: CampaignMode
  onModeChange: (mode: CampaignMode) => void
}

export function ModeSelector({ currentMode, onModeChange }: ModeSelectorProps) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">🎙️ Modo de campaña</label>
      <div className="grid grid-cols-2 gap-2">
        {CAMPAIGN_MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => onModeChange(m.value as CampaignMode)}
            className={`rounded-xl border p-3 text-left transition-all ${
              currentMode === m.value
                ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30'
                : 'border-border hover:border-brand-300'
            }`}
          >
            <div className="text-sm font-medium text-foreground">{m.label}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{m.desc}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
