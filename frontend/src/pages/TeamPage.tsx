import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Users, UserPlus, Trash2, Shield, Eye, Loader2 } from 'lucide-react'
import SEO from '@/components/SEO'

interface TeamMember {
  id: string
  member_email: string
  role: 'agent' | 'viewer'
  invited_at: string
  accepted_at: string | null
}

const ROLE_LABELS: Record<string, string> = {
  agent: 'Agente',
  viewer: 'Visor',
}
const ROLE_COLORS: Record<string, string> = {
  agent: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  viewer: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

export default function TeamPage() {
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'agent' | 'viewer'>('agent')
  const [error, setError] = useState('')

  const { data: members, isLoading } = useQuery<TeamMember[]>({
    queryKey: ['team'],
    queryFn: () => api.get('/team').then((r) => r.data),
  })

  const inviteMutation = useMutation({
    mutationFn: () => api.post('/team', { email, role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team'] })
      setEmail('')
      setError('')
    },
    onError: (err: unknown) => setError(getApiError(err, 'Error al invitar')),
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/team/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team'] }),
  })

  const updateRoleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      api.patch(`/team/${id}`, { email: '', role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team'] }),
  })

  return (
    <>
      <SEO title="Equipo" description="Panel de control de IaRadio." noIndex />
      <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Equipo</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Invita colaboradores a tu cuenta de IaRadio.</p>
      </div>

      {/* Invite form */}
      <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-6 shadow-sm">
        <h2 className="mb-4 font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <UserPlus className="h-5 w-5 text-brand-600 dark:text-brand-400" /> Invitar miembro
        </h2>
        {error && <p className="mb-3 rounded-lg bg-red-50 dark:bg-red-950/30 px-3 py-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
        <div className="flex gap-3">
          <input
            type="email"
            placeholder="email@ejemplo.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="flex-1 rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as 'agent' | 'viewer')}
            className="rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="agent">Agente</option>
            <option value="viewer">Visor</option>
          </select>
          <button
            onClick={() => inviteMutation.mutate()}
            disabled={!email || inviteMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-brand-600 dark:bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700 dark:hover:bg-brand-600 disabled:opacity-60"
          >
            {inviteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            Invitar
          </button>
        </div>
        <div className="mt-3 flex gap-4 text-xs text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1"><Shield className="h-3 w-3 text-blue-500" /> <strong>Agente:</strong> puede responder conversaciones y crear campañas</span>
          <span className="flex items-center gap-1"><Eye className="h-3 w-3 text-gray-400" /> <strong>Visor:</strong> solo lectura</span>
        </div>
      </div>

      {/* Members list */}
      <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Users className="h-5 w-5 text-gray-400 dark:text-gray-500" /> Miembros del equipo
          </h2>
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center py-12 text-gray-400 dark:text-gray-500">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (members?.length ?? 0) === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
            Aún no hay miembros invitados.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {members?.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-6 py-4">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{m.member_email}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    Invitado {new Date(m.invited_at).toLocaleDateString('es-MX')}
                    {m.accepted_at ? ' · Aceptado' : ' · Pendiente'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <select
                    value={m.role}
                    onChange={(e) => updateRoleMutation.mutate({ id: m.id, role: e.target.value })}
                    className="rounded-lg border border-gray-200 dark:border-gray-700 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none"
                  >
                    <option value="agent">Agente</option>
                    <option value="viewer">Visor</option>
                  </select>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ROLE_COLORS[m.role] ?? ''}`}>
                    {ROLE_LABELS[m.role] ?? m.role}
                  </span>
                  <button
                    onClick={() => removeMutation.mutate(m.id)}
                    className="text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
    </>
  )
}
