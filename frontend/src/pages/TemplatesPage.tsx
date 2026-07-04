import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { FileText, Plus, Trash2, Download, Check } from 'lucide-react'
import { formatDate } from '@/lib/utils'

interface Template {
  id: string
  name: string
  content: string
  category: string | null
  created_at?: string
}

interface SeedTemplate {
  name: string
  content: string
  category: string | null
}

export default function TemplatesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', content: '', category: '' })
  const [tab, setTab] = useState<'mine' | 'seeds'>('mine')

  const { data: templates, isLoading } = useQuery<Template[]>({
    queryKey: ['templates'],
    queryFn: () => api.get('/templates').then(r => r.data),
  })

  const { data: seedTemplates } = useQuery<SeedTemplate[]>({
    queryKey: ['template-seeds'],
    queryFn: () => api.get('/templates/seeds').then(r => r.data),
    enabled: tab === 'seeds',
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; content: string; category?: string }) => api.post('/templates', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['templates'] })
      setShowForm(false)
      setForm({ name: '', content: '', category: '' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/templates/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates'] }),
  })

  const seedAllMutation = useMutation({
    mutationFn: () => api.post('/templates/seed-all').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['templates'] })
    },
  })

  const applySeedTemplate = (t: SeedTemplate) => {
    setTab('mine')
    setShowForm(true)
    setForm({ name: t.name, content: t.content, category: t.category || '' })
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
            <div className="rounded-xl bg-brand-50 dark:bg-brand-950/30 p-2.5">
            <FileText className="h-5 w-5 text-brand-500 dark:text-brand-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Plantillas</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">Reutiliza mensajes en tus campañas</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 rounded-xl bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          <Plus size={16} />
          Nueva
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800 pb-1">
        <button
          onClick={() => setTab('mine')}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
            tab === 'mine' ? 'text-brand-600 border-b-2 border-brand-500 dark:text-brand-400 dark:border-brand-400' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
          }`}
        >
          Mis plantillas
        </button>
        <button
          onClick={() => setTab('seeds')}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
            tab === 'seeds' ? 'text-brand-600 border-b-2 border-brand-500 dark:text-brand-400 dark:border-brand-400' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
          }`}
        >
          Pre-armadas
        </button>
      </div>

      {showForm && tab === 'mine' && (
        <div className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-200">Nueva plantilla</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nombre</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Categoría</label>
            <input
              value={form.category}
              onChange={e => setForm({ ...form, category: e.target.value })}
              placeholder="Ej: Promoción, Recordatorio, Seguimiento"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Contenido</label>
            <textarea
              value={form.content}
              onChange={e => setForm({ ...form, content: e.target.value })}
              rows={4}
              placeholder="Usa {name}, {city}, {business_name} como variables"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-900">Cancelar</button>
            <button
              onClick={() => createMutation.mutate({ name: form.name, content: form.content, category: form.category || undefined })}
              disabled={!form.name || !form.content || createMutation.isPending}
              className="rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear'}
            </button>
          </div>
        </div>
      )}

      {/* Mis plantillas */}
      {tab === 'mine' && (
        <>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-xl" />)}
            </div>
          ) : !templates?.length ? (
            <div className="rounded-xl bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-8 text-center text-sm text-gray-400 dark:text-gray-500">
              No tienes plantillas aún.
            </div>
          ) : (
            <div className="grid gap-3">
              {templates.map(t => (
                <div key={t.id} className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-5 flex items-start justify-between">
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">{t.name}</h3>
                      {t.category && <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full">{t.category}</span>}
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 truncate">{t.content}</p>
                  </div>
                  <button
                    onClick={() => deleteMutation.mutate(t.id)}
                    className="ml-3 rounded-lg p-2 text-gray-400 dark:text-gray-500 hover:bg-red-50 dark:hover:bg-red-950 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Pre-armadas */}
      {tab === 'seeds' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">Plantillas listas para usar. Impórtalas todas o úsalas individualmente.</p>
            <button
              onClick={() => seedAllMutation.mutate()}
              disabled={seedAllMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
            >
              <Download size={15} />
              {seedAllMutation.isPending ? 'Importando...' : 'Importar todas'}
            </button>
          </div>
          {seedAllMutation.data && (
            <div className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 px-4 py-3 text-sm text-green-700 dark:text-green-400">
              {seedAllMutation.data.message}
            </div>
          )}
          {!seedTemplates ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-xl" />)}
            </div>
          ) : (
            <div className="grid gap-3">
              {seedTemplates.map((t, i) => (
                <div key={i} className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-5 flex items-start justify-between">
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">{t.name}</h3>
                      {t.category && <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full">{t.category}</span>}
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">{t.content}</p>
                  </div>
                  <button
                    onClick={() => applySeedTemplate(t)}
                    className="ml-3 flex items-center gap-1.5 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/30 px-3 py-1.5 text-xs font-medium text-brand-600 dark:text-brand-400 hover:bg-brand-100 dark:hover:bg-brand-950 transition-colors"
                  >
                    <Check size={13} />
                    Usar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
