import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'

interface MutationCallbacks {
  onSuccessCreate?: () => void
  onErrorCreate?: (error: string) => void
}

export function useCampaignMutations(callbacks?: MutationCallbacks) {
  const qc = useQueryClient()
  const { toast } = useToast()

  const createMutation = useMutation({
    mutationFn: (body: object) => api.post('/campaigns', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      callbacks?.onSuccessCreate?.()
    },
    onError: (err: unknown) => {
      const errorMsg = getApiError(err)
      callbacks?.onErrorCreate?.(errorMsg)
    },
  })

  const pauseMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/pause`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (err: unknown) => {
      toast({
        title: 'Error',
        description: getApiError(err, 'Error al pausar campaña'),
        variant: 'error',
      })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/campaigns/${id}/resume`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (err: unknown) => {
      toast({
        title: 'Error',
        description: getApiError(err, 'Error al iniciar campaña'),
        variant: 'error',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/campaigns/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (err: unknown) => {
      toast({
        title: 'Error',
        description: getApiError(err, 'Error al eliminar campaña'),
        variant: 'error',
      })
    },
  })

  return {
    createMutation,
    pauseMutation,
    resumeMutation,
    deleteMutation,
  }
}
