import { AxiosError } from 'axios'
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
      toast({
        title: 'Campaña creada',
        description: 'Se guardó como borrador. Haz clic en el botón verde para enviarla.',
        variant: 'success',
      })
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
      toast({
        title: 'Campaña pausada',
        description: 'Los envíos se han detenido.',
        variant: 'info',
      })
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
      toast({
        title: 'Campaña iniciada',
        description: 'El envío ha comenzado. Puede tomar varios minutos en completarse.',
        variant: 'success',
      })
    },
    onError: (err: unknown) => {
      // 409 = an anti-ban gate blocked the send (segment cooldown, recipient
      // cap, quota). Not a failure — a rule the advertiser needs to know.
      const blocked = err instanceof AxiosError && err.response?.status === 409
      toast({
        title: blocked ? 'No se puede enviar todavía' : 'Error',
        description: getApiError(err, 'Error al iniciar campaña'),
        variant: blocked ? 'info' : 'error',
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
