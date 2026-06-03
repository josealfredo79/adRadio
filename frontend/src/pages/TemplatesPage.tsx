import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { formatDate } from '@/lib/utils'

interface Template {
  id: string
  name: string
  content: string
  category: string | null
  created_at?: string
}

export default function TemplatesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', content: '', category: '' })

  const { data: templates, isLoading } = useQuery<Template[]>({
    queryKey: ['templates'],
    queryFn: () => api.get('/templates').then(r => r.data),
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

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-brand-50 p-2.5">
            <FileText className="h-5 w-5 text-brand-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Plantillas</h1>
            <p className="text-sm text-gray-500">Reutiliza mensajes en tus campañas</p>
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

      {showForm && (
        <div className="rounded-xl bg-white border border-gray-200 p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Nueva plantilla</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
            <input
              value={form.category}
              onChange={e => setForm({ ...form, category: e.target.value })}
              placeholder="Ej: Promoción, Recordatorio, Seguimiento"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Contenido</label>
            <textarea
              value={form.content}
              onChange={e => setForm({ ...form, content: e.target.value })}
              rows={4}
              placeholder="Usa {name}, {city}, {business_name} como variables"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none resize-none"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">Cancelar</button>
            <button
              onClick={() => createMutation.mutate({ name: form.name, content: form.content, category: form.category || undefined })}
              disabled={!form.name || !form.content || createMutation.isPending}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creando...' : 'Crear'}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-100 animate-pulse rounded-xl" />)}
        </div>
      ) : !templates?.length ? (
        <div className="rounded-xl bg-gray-50 border border-gray-200 p-8 text-center text-sm text-gray-400">
          No tienes plantillas aún.
        </div>
      ) : (
        <div className="grid gap-3">
          {templates.map(t => (
            <div key={t.id} className="rounded-xl bg-white border border-gray-200 p-5 flex items-start justify-between">
              <div className="space-y-1 flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-900">{t.name}</h3>
                  {t.category && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{t.category}</span>}
                </div>
                <p className="text-sm text-gray-600 truncate">{t.content}</p>
              </div>
              <button
                onClick={() => deleteMutation.mutate(t.id)}
                className="ml-3 rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
