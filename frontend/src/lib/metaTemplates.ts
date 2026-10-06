import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'

export interface MetaTemplate {
  id: string
  name: string
  language: string
  category: string
  status: string
  body: string
  rejected_reason: string | null
}

export function useMetaTemplates(enabled: boolean) {
  return useQuery<MetaTemplate[]>({
    queryKey: ['meta-templates'],
    queryFn: () => api.get('/me/whatsapp-templates/meta').then((r) => r.data),
    enabled,
    staleTime: 30_000,
    // Una plantilla recién enviada suele resolverse en minutos.
    refetchInterval: (q) => (q.state.data?.some((t) => t.status === 'PENDING') ? 30_000 : false),
  })
}
