import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { X, Megaphone, Sparkles } from 'lucide-react'
import api, { getApiError } from '@/lib/api'

interface VocesDetailModalProps {
  campaignId: string
  campaignName: string
  onClose: () => void
}

interface Story {
  id: string
  contact_name?: string
  sentiment: string
  transcription: string
  media_url: string
  approved: boolean
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

interface StoriesResponse {
  stories: Story[]
  total: number
  approved_count: number
  pending_count: number
}

export function VocesDetailModal({
  campaignId,
  campaignName,
  onClose,
}: VocesDetailModalProps) {
  const [capsuleAudioUrl, setCapsuleAudioUrl] = useState('')
  const [capsuleScript, setCapsuleScript] = useState('')
  const [capsuleGenerating, setCapsuleGenerating] = useState(false)
  const [error, setError] = useState('')

  const {
    data: storiesData,
    isLoading: storiesLoading,
    refetch: refetchStories,
  } = useQuery<StoriesResponse>({
    queryKey: ['campaign-stories', campaignId],
    queryFn: () => api.get(`/campaigns/${campaignId}/stories`).then((r) => r.data),
    enabled: !!campaignId,
  })

  const [approvedToast, setApprovedToast] = useState(false)

  const approveStoryMutation = useMutation({
    mutationFn: (storyId: string) => api.patch(`/campaigns/stories/${storyId}/approve`),
    onSuccess: () => {
      setApprovedToast(true)
      setTimeout(() => setApprovedToast(false), 4000)
      refetchStories()
    },
  })

  const rejectStoryMutation = useMutation({
    mutationFn: (storyId: string) => api.patch(`/campaigns/stories/${storyId}/reject`),
    onSuccess: () => refetchStories(),
  })

  const generateCapsule = async () => {
    setCapsuleGenerating(true)
    setError('')
    try {
      const { data } = await api.post(`/campaigns/${campaignId}/generate-capsule`)
      setCapsuleAudioUrl(data.audio_url)
      setCapsuleScript(data.script ?? '')
    } catch (err: unknown) {
      setError(getApiError(err, 'Error al generar cápsula'))
    } finally {
      setCapsuleGenerating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-foreground">🎤 {campaignName}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">Voces del Barrio — Historias de clientes</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        {storiesLoading ? (
          <div className="flex items-center justify-center py-8">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
          </div>
        ) : storiesData && storiesData.stories.length > 0 ? (
          <>
            <div className="mb-3 flex items-center gap-3 text-sm text-muted-foreground">
              <span>📥 Total: {storiesData.total}</span>
              <span className="text-green-600 dark:text-green-300">✅ Aprobadas: {storiesData.approved_count}</span>
              <span className="text-yellow-600 dark:text-yellow-300">⏳ Pendientes: {storiesData.pending_count}</span>
            </div>

            <div className="space-y-3 mb-4 max-h-80 overflow-y-auto">
              {storiesData.stories.map((story) => (
                <div
                  key={story.id}
                  className={`rounded-xl border p-3 ${
                    story.status === 'rejected' ? 'border-border bg-muted/40 opacity-60' : 'border-border bg-card'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-foreground dark:text-gray-200">{story.contact_name || 'Cliente'}</p>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-full ${
                        story.sentiment === 'positivo'
                          ? 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-300'
                          : story.sentiment === 'negativo'
                          ? 'bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-300'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {story.sentiment}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap">{story.transcription}</p>
                  {story.media_url && <audio controls src={story.media_url} className="mt-2 w-full h-9" />}
                  <div className="mt-2 flex items-center justify-between">
                    <p className="text-[10px] text-muted-foreground">
                      {new Date(story.created_at).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}
                    </p>
                    {story.status === 'rejected' ? (
                      <button
                        onClick={() => approveStoryMutation.mutate(story.id)}
                        className="rounded-lg px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground hover:bg-yellow-100 hover:text-yellow-700"
                      >
                        Restaurar
                      </button>
                    ) : (
                      <div className="flex gap-2">
                        {story.status !== 'approved' && (
                          <button
                            onClick={() => rejectStoryMutation.mutate(story.id)}
                            className="rounded-lg px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground hover:bg-red-100 hover:text-red-700"
                          >
                            Rechazar
                          </button>
                        )}
                        <button
                          onClick={() => approveStoryMutation.mutate(story.id)}
                          disabled={story.status === 'approved'}
                          className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                            story.status === 'approved'
                              ? 'bg-green-100 text-green-700 dark:text-green-300 cursor-default'
                              : 'bg-yellow-100 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200'
                          }`}
                        >
                          {story.status === 'approved' ? '✅ Al aire' : 'Aprobar y publicar'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {approvedToast && (
              <p className="mb-3 rounded-lg bg-green-50 dark:bg-green-950/30 px-3 py-2 text-xs text-green-700 dark:text-green-300">
                ✅ Publicada. Le avisamos al cliente que ya está al aire con el link a tu página.
              </p>
            )}
            {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

            <div className="border-t border-border pt-4 space-y-3">
              <button
                onClick={generateCapsule}
                disabled={capsuleGenerating || storiesData.approved_count === 0}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-purple-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-600 disabled:opacity-60 transition-colors"
              >
                <Sparkles className="h-4 w-4" />
                {capsuleGenerating ? 'Generando cápsula...' : capsuleAudioUrl ? '🎤 Regenerar cápsula narrativa' : '🎤 Generar cápsula narrativa'}
              </button>
              {storiesData.approved_count === 0 && (
                <p className="text-center text-xs text-yellow-600 dark:text-yellow-300 font-medium">Aprueba al menos una historia para generar la cápsula</p>
              )}

              {capsuleAudioUrl && (
                <div className="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 p-4 space-y-2">
                  <p className="text-sm font-medium text-purple-700 dark:text-purple-300">🎤 Cápsula generada</p>
                  <audio controls src={capsuleAudioUrl} className="w-full" />
                  {capsuleScript && (
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer font-medium">Ver guión</summary>
                      <p className="mt-2 whitespace-pre-wrap">{capsuleScript}</p>
                    </details>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Megaphone className="mx-auto h-10 w-10 mb-2" />
            <p className="text-sm font-medium">No hay historias todavía</p>
            <p className="text-xs mt-1">Cuando tus contactos envíen audios a esta campaña, aparecerán aquí</p>
          </div>
        )}
      </div>
    </div>
  )
}
