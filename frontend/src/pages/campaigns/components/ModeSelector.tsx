import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { AUDIO_MODES, CampaignMode, CAMPAIGN_MODES, HIDDEN_MODES } from '../types'
import { CampaignQuota, quotaBadge } from '../campaignQuota'

interface ModeSelectorProps {
  currentMode: CampaignMode
  onModeChange: (mode: CampaignMode) => void
}

export function ModeSelector({ currentMode, onModeChange }: ModeSelectorProps) {
  const { data: quota } = useQuery<CampaignQuota>({
    queryKey: ['campaign-quota'],
    queryFn: () => api.get('/campaigns/quota').then((r) => r.data),
  })
  const badge = (mode: CampaignMode) =>
    quotaBadge(AUDIO_MODES.includes(mode) ? quota?.audio : mode === 'banner' ? quota?.image : undefined)

  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">🎙️ Modo de campaña</label>
      <div className="grid grid-cols-2 gap-2">
        {CAMPAIGN_MODES.filter((m) => !HIDDEN_MODES.includes(m.value as CampaignMode)).map((m) => {
          const b = badge(m.value as CampaignMode)
          return (
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
              {b && <div className="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-400">{b}</div>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
