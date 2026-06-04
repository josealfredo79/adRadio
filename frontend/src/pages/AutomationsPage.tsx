import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { GitBranch, Plus, Zap, MessageSquare, Trash2, Power, PowerOff } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'
import SEO from '@/components/SEO'

interface Step {
  position: number
  delay_minutes: number
  message: string
}

interface AutomationFlow {
  id: string
  name: string
  trigger: string
  trigger_value: string | null
  is_active: boolean
  created_at: string
  steps: Step[]
}

const TRIGGER_LABELS: Record<string, string> = {
  new_contact: 'Nuevo contacto',
  keyword: 'Palabra clave',
  tag_added: 'Tag agregado',
}

export default function AutomationsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    name: '',
    trigger: 'new_contact' as string,
    trigger_value: '',
    steps: [] as { delay_minutes: number; message: string }[],
  })

  const { data: flows, isLoading } = useQuery<AutomationFlow[]>({
    queryKey: ['automations'],
    queryFn: () => api.get('/automations').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string
      trigger: string
      trigger_value?: string
      steps: { position: number; delay_minutes: number; message: string }[]
    }) => api.post('/automations', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automations'] })
      setShowForm(false)
      setForm({ name: '', trigger: 'new_contact', trigger_value: '', steps: [] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/automations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  })

  const toggleMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/automations/${id}/toggle`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  })

  const addStep = () => {
    setForm(prev => ({
      ...prev,
      steps: [...prev.steps, { delay_minutes: prev.steps.length === 0 ? 0 : 1440, message: '' }],
    }))
  }

  const removeStep = (idx: number) => {
    setForm(prev => ({
      ...prev,
      steps: prev.steps.filter((_, i) => i !== idx),
    }))
  }

  const updateStep = (idx: number, field: 'delay_minutes' | 'message', value: string | number) => {
    setForm(prev => {
      const steps = [...prev.steps]
      steps[idx] = { ...steps[idx], [field]: value }
      return { ...prev, steps }
    })
  }

  return (
    <>
      <SEO title="Automatizaciones" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-brand-50 dark:bg-brand-950/30 p-2.5">
            <GitBranch className="h-5 w-5 text-brand-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Automatizaciones</h1>
            <p className="text-sm text-muted-foreground">Flujos automáticos de mensajes para tus contactos</p>
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
        <div className="rounded-xl bg-card border border-border p-5 space-y-4">
          <h2 className="font-semibold text-foreground">Nuevo flujo</h2>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Nombre</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
              placeholder="Ej: Bienvenida, Seguimiento post-venta..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Disparador</label>
            <select
              value={form.trigger}
              onChange={e => setForm({ ...form, trigger: e.target.value })}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
            >
              <option value="new_contact">Nuevo contacto</option>
              <option value="keyword">Palabra clave</option>
            </select>
          </div>
          {form.trigger === 'keyword' && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Palabra clave</label>
              <input
                value={form.trigger_value}
                onChange={e => setForm({ ...form, trigger_value: e.target.value })}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
                placeholder="Ej: menu, promo, horarios"
              />
            </div>
          )}

          {/* Steps builder */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-foreground">Pasos del flujo</label>
              <button
                type="button"
                onClick={addStep}
                className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-600 font-medium"
              >
                <Plus size={14} /> Agregar paso
              </button>
            </div>
            <div className="space-y-3">
              {form.steps.length === 0 ? (
                <p className="text-xs text-muted-foreground py-2">Agrega al menos un paso para que el flujo envíe mensajes.</p>
              ) : (
                form.steps.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-3">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-[11px] font-bold text-white">
                      {idx + 1}
                    </div>
                    <div className="flex-1 space-y-2 min-w-0">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-muted-foreground whitespace-nowrap">Esperar</label>
                        <select
                          value={step.delay_minutes}
                          onChange={e => updateStep(idx, 'delay_minutes', Number(e.target.value))}
                          className="rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground focus:border-brand-500 focus:outline-none"
                        >
                          <option value={0}>0 min (inmediato)</option>
                          <option value={5}>5 min</option>
                          <option value={15}>15 min</option>
                          <option value={30}>30 min</option>
                          <option value={60}>1 hora</option>
                          <option value={180}>3 horas</option>
                          <option value={360}>6 horas</option>
                          <option value={720}>12 horas</option>
                          <option value={1440}>1 día</option>
                          <option value={2880}>2 días</option>
                          <option value={4320}>3 días</option>
                          <option value={10080}>7 días</option>
                        </select>
                      </div>
                      <textarea
                        value={step.message}
                        onChange={e => updateStep(idx, 'message', e.target.value)}
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none resize-none"
                        rows={2}
                        placeholder="Texto del mensaje..."
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeStep(idx)}
                      className="shrink-0 rounded-lg p-1.5 text-muted-foreground hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950/30 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted">
              Cancelar
            </button>
            <button
              onClick={() =>
                createMutation.mutate({
                  name: form.name,
                  trigger: form.trigger,
                  trigger_value: form.trigger_value || undefined,
                  steps: form.steps.map((s, i) => ({ position: i, delay_minutes: s.delay_minutes, message: s.message })),
                })
              }
              disabled={!form.name || form.steps.length === 0 || createMutation.isPending}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear flujo'}
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}
        </div>
      ) : !flows?.length ? (
        <div className="rounded-xl bg-muted border border-border p-8 text-center text-sm text-muted-foreground">
          No tienes automatizaciones aún. Crea una para empezar.
        </div>
      ) : (
        <div className="space-y-3">
          {flows.map(flow => (
            <div key={flow.id} className="rounded-xl bg-card border border-border p-5 flex items-start justify-between gap-4">
              <div className="space-y-1.5 min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-foreground">{flow.name}</h3>
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full font-medium',
                    flow.is_active
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                  )}>
                    {flow.is_active ? 'Activo' : 'Inactivo'}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground flex items-center gap-1">
                  <Zap size={13} />
                  {TRIGGER_LABELS[flow.trigger] ?? flow.trigger}
                  {flow.trigger_value && <>: <strong>{flow.trigger_value}</strong></>}
                </p>
                {flow.steps.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <MessageSquare size={12} />
                      {flow.steps.length} paso{flow.steps.length !== 1 ? 's' : ''}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {flow.steps.map((s, i) => (
                        <span key={i} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                          {i + 1}. {s.delay_minutes === 0 ? 'Inmediato' : `${s.delay_minutes < 60 ? s.delay_minutes + 'min' : s.delay_minutes >= 1440 ? Math.round(s.delay_minutes / 1440) + 'd' : Math.round(s.delay_minutes / 60) + 'h'}`}
                          {i < flow.steps.length - 1 && <span className="text-muted-foreground/40">→</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">Creado {formatDate(flow.created_at)}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => toggleMutation.mutate(flow.id)}
                  className={cn(
                    'rounded-lg p-2 transition-colors',
                    flow.is_active
                      ? 'text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-950/30'
                      : 'text-muted-foreground hover:bg-muted'
                  )}
                  title={flow.is_active ? 'Desactivar' : 'Activar'}
                >
                  {flow.is_active ? <Power size={16} /> : <PowerOff size={16} />}
                </button>
                <button
                  onClick={() => { if (confirm('¿Eliminar este flujo?')) deleteMutation.mutate(flow.id) }}
                  className="rounded-lg p-2 text-muted-foreground hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950/30 transition-colors"
                  title="Eliminar"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    </>
  )
}
