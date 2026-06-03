import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { GitBranch, Plus, Zap, Users, MessageSquare } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import SEO from '@/components/SEO'

interface AutomationFlow {
  id: string
  name: string
  trigger: string
  trigger_value: string | null
  is_active: boolean
  created_at: string
  steps: { position: number; delay_minutes: number; message: string }[]
}

const TRIGGER_LABELS: Record<string, string> = {
  new_contact: 'Nuevo contacto',
  keyword: 'Palabra clave',
}

export default function AutomationsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', trigger: 'new_contact', trigger_value: '', steps: '' })

  const { data: flows, isLoading } = useQuery<AutomationFlow[]>({
    queryKey: ['automations'],
    queryFn: () => api.get('/automations').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; trigger: string; trigger_value?: string }) => api.post('/automations', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automations'] })
      setShowForm(false)
      setForm({ name: '', trigger: 'new_contact', trigger_value: '', steps: '' })
    },
  })

  return (
    <>
      <SEO title="Automatizaciones" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-brand-50 p-2.5">
            <GitBranch className="h-5 w-5 text-brand-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Automatizaciones</h1>
            <p className="text-sm text-gray-500">Flujos automáticos de mensajes para tus contactos</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          <Plus size={16} />
          Nueva
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl bg-white border border-gray-200 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Nuevo flujo</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Disparador</label>
            <select
              value={form.trigger}
              onChange={e => setForm({ ...form, trigger: e.target.value })}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none bg-white"
            >
              <option value="new_contact">Nuevo contacto</option>
              <option value="keyword">Palabra clave</option>
            </select>
          </div>
          {form.trigger === 'keyword' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Palabra clave</label>
              <input
                value={form.trigger_value}
                onChange={e => setForm({ ...form, trigger_value: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">Cancelar</button>
            <button
              onClick={() => createMutation.mutate({ name: form.name, trigger: form.trigger, trigger_value: form.trigger_value || undefined })}
              disabled={!form.name || createMutation.isPending}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear'}
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <div key={i} className="h-24 bg-gray-100 animate-pulse rounded-xl" />)}
        </div>
      ) : !flows?.length ? (
        <div className="rounded-xl bg-gray-50 border border-gray-200 p-8 text-center text-sm text-gray-400">
          No tienes automatizaciones aún. Crea una para empezar.
        </div>
      ) : (
        <div className="space-y-3">
          {flows.map(flow => (
            <div key={flow.id} className="rounded-xl bg-white border border-gray-200 p-5 flex items-start justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-900">{flow.name}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${flow.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {flow.is_active ? 'Activo' : 'Inactivo'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 flex items-center gap-1">
                  <Zap size={13} />
                  {TRIGGER_LABELS[flow.trigger] ?? flow.trigger}
                  {flow.trigger_value && <>: <strong>{flow.trigger_value}</strong></>}
                </p>
                {flow.steps.length > 0 && (
                  <p className="text-xs text-gray-400 flex items-center gap-1">
                    <MessageSquare size={12} />
                    {flow.steps.length} paso{flow.steps.length !== 1 ? 's' : ''} · {flow.steps.map(s => `${s.delay_minutes}min`).join(' → ')}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    </>
  )
}
