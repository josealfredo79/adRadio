import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Radio } from 'lucide-react'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'

import { Campaign, Template, Voice } from './types'
import { useCampaignForm } from './hooks/useCampaignForm'
import { useCampaignMutations } from './hooks/useCampaignMutations'

import { CampaignCard } from './components/CampaignCard'
import { CampaignListHeader } from './components/CampaignListHeader'
import { Pagination } from './components/Pagination'
import { CreateCampaignModal } from './components/CreateCampaignModal'
import { ParrillaModal } from './components/ParrillaModal'
import { AnalyticsModal } from './components/AnalyticsModal'
import { VocesDetailModal } from './components/VocesDetailModal'

export default function CampaignsPage() {
  const { user: currentUser } = useAuth()
  const { toast } = useToast()

  const [showCreate, setShowCreate] = useState(false)
  const [showParrilla, setShowParrilla] = useState(false)
  const [analyticsId, setAnalyticsId] = useState<string | null>(null)
  const [vocesDetailId, setVocesDetailId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [resumingId, setResumingId] = useState<string | null>(null)
  const [pausingId, setPausingId] = useState<string | null>(null)

  const formState = useCampaignForm()
  const { setError, resetForm } = formState

  const mutations = useCampaignMutations({
    onSuccessCreate: () => {
      setShowCreate(false)
      resetForm()
    },
    onErrorCreate: (errorMsg) => {
      setError(errorMsg)
    },
  })

  const { data: campaignsData, isLoading } = useQuery<{ items: Campaign[]; total: number }>({
    queryKey: ['campaigns', page],
    queryFn: () => api.get('/campaigns', { params: { page, page_size: 20 } }).then((r) => r.data),
  })

  const campaigns = campaignsData?.items
  const totalCampaigns = campaignsData?.total ?? 0
  const totalPages = totalCampaigns > 0 ? Math.ceil(totalCampaigns / 20) : 0

  const { data: dashData } = useQuery<{ messages_remaining: number }>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/dashboard').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })
  const noCredits = (dashData?.messages_remaining ?? 1) <= 0

  const { data: templatesData } = useQuery<Template[]>({
    queryKey: ['templates'],
    queryFn: () => api.get('/templates').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })

  const { data: voicesData } = useQuery<Voice[]>({
    queryKey: ['radio-voices'],
    queryFn: () => api.get('/radio/voices').then((r) => r.data),
    staleTime: 1000 * 60 * 60,
  })

  const { data: optimalTime } = useQuery<{ best_window: string; best_hour: number }>({
    queryKey: ['optimal-send-time'],
    queryFn: () => api.get('/analytics/optimal-send-time').then((r) => r.data),
    staleTime: 1000 * 60 * 30,
  })

  const handleExportCsv = async () => {
    try {
      const response = await api.get('/campaigns/export-csv', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'campanas_iaradio.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast({ title: 'Error', description: 'Error al exportar', variant: 'error' })
    }
  }

  const analyticsTarget = campaigns?.find((c) => c.id === analyticsId)
  const vocesDetailTarget = campaigns?.find((c) => c.id === vocesDetailId)

  return (
    <>
      <SEO title="Campañas" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6">
        <CampaignListHeader
          totalCampaigns={totalCampaigns}
          hasCampaigns={(campaigns?.length ?? 0) > 0}
          noCredits={noCredits}
          onExportCsv={handleExportCsv}
          onShowParrilla={() => setShowParrilla(true)}
          onShowCreate={() => setShowCreate(true)}
        />

        <div className="print-area">
          {noCredits && (
            <div className="rounded-xl border border-orange-200 bg-orange-50 dark:bg-orange-950/30 px-5 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-orange-800 dark:text-orange-200">Sin mensajes disponibles</p>
                <p className="text-xs text-orange-600 dark:text-orange-300">Adquiere un plan para crear y enviar campañas.</p>
              </div>
              <a
                href="/app/plans"
                className="shrink-0 rounded-lg bg-orange-500 px-4 py-2 text-xs font-medium text-white hover:bg-orange-600 transition-colors"
              >
                Ver planes →
              </a>
            </div>
          )}

          <div className="space-y-3">
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-24 rounded-xl bg-muted animate-pulse dark:bg-gray-800" />
              ))
            ) : campaigns?.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl bg-card py-16 shadow-sm border border-border text-muted-foreground">
                <Radio className="h-12 w-12 mb-3" />
                <p className="text-sm font-medium">No hay campañas todavía</p>
                <p className="text-xs mt-1">Crea tu primera campaña — regular, secuencia o saga</p>
              </div>
            ) : (
              campaigns?.map((campaign) => (
                <CampaignCard
                  key={campaign.id}
                  campaign={campaign}
                  onViewAnalytics={(id) => setAnalyticsId(id)}
                  onViewVocesDetail={(id) => setVocesDetailId(id)}
                  onPause={(id) => {
                    setPausingId(id)
                    mutations.pauseMutation.mutate(id, {
                      onSettled: () => setPausingId(null),
                    })
                  }}
                  onResume={(id) => {
                    setResumingId(id)
                    mutations.resumeMutation.mutate(id, {
                      onSettled: () => setResumingId(null),
                    })
                  }}
                  onDelete={(id) => mutations.deleteMutation.mutate(id)}
                  resumingId={resumingId}
                  pausingId={pausingId}
                />
              ))
            )}
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            totalCampaigns={totalCampaigns}
            onPageChange={setPage}
          />
        </div>
      </div>

      {showCreate && (
        <CreateCampaignModal
          onClose={() => {
            setShowCreate(false)
            resetForm()
          }}
          formState={formState}
          templatesData={templatesData}
          voicesData={voicesData}
          optimalTime={optimalTime}
          noCredits={noCredits}
          onCreate={(campaignData) => mutations.createMutation.mutate(campaignData)}
          isCreatePending={mutations.createMutation.isPending}
          currentUser={currentUser}
        />
      )}

      {showParrilla && (
        <ParrillaModal onClose={() => setShowParrilla(false)} />
      )}

      {analyticsTarget && (
        <AnalyticsModal
          campaign={analyticsTarget}
          onClose={() => setAnalyticsId(null)}
        />
      )}

      {vocesDetailTarget && (
        <VocesDetailModal
          campaignId={vocesDetailTarget.id}
          campaignName={vocesDetailTarget.name}
          onClose={() => setVocesDetailId(null)}
        />
      )}
    </>
  )
}
