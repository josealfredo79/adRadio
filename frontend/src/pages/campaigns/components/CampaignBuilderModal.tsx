import { X } from 'lucide-react'
import { CampaignBuilderChat } from './CampaignBuilderChat'

// "Nueva campaña": la plática que pregunta (spec 2026-10-29-campana-que-pregunta).
// Lo avanzado (A/B, programar, plantillas) sigue en "Más opciones".
export function CampaignBuilderModal({ onClose, onMoreOptions }: { onClose: () => void; onMoreOptions: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-foreground">Nueva campaña</h2>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1 text-muted-foreground hover:bg-muted">
            <X className="h-5 w-5" />
          </button>
        </div>
        <CampaignBuilderChat />
        <button onClick={onMoreOptions} className="mt-4 w-full text-center text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">
          Más opciones (A/B, programar fecha, plantillas…)
        </button>
      </div>
    </div>
  )
}
