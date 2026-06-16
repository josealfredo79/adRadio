import { Plus, Download, CalendarRange } from 'lucide-react'
import PrintButton from '@/components/PrintButton'

interface CampaignListHeaderProps {
  totalCampaigns: number
  hasCampaigns: boolean
  noCredits: boolean
  onExportCsv: () => void
  onShowParrilla: () => void
  onShowCreate: () => void
}

export function CampaignListHeader({
  totalCampaigns,
  hasCampaigns,
  noCredits,
  onExportCsv,
  onShowParrilla,
  onShowCreate,
}: CampaignListHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Campañas</h1>
        <p className="mt-1 text-sm text-muted-foreground">{totalCampaigns} campañas creadas</p>
      </div>
      <div className="flex gap-3">
        <PrintButton />
        {hasCampaigns && (
          <button
            onClick={onExportCsv}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-gray-700 hover:bg-muted transition-colors dark:text-gray-300 dark:hover:bg-gray-800"
          >
            <Download className="h-4 w-4" /> Exportar CSV
          </button>
        )}
        <button
          onClick={onShowParrilla}
          className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-gray-700 hover:bg-muted transition-colors dark:text-gray-300 dark:hover:bg-gray-800"
        >
          <CalendarRange className="h-4 w-4 text-brand-500" /> Parrilla Semanal
        </button>
        <button
          onClick={onShowCreate}
          disabled={noCredits}
          title={noCredits ? 'Sin mensajes disponibles — adquiere un plan para continuar' : undefined}
          className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="h-4 w-4" /> Nueva campaña
        </button>
      </div>
    </div>
  )
}
