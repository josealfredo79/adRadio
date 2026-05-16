import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { Users, Plus, Upload, Trash2, Search, Download } from 'lucide-react'
import { formatDate } from '@/lib/utils'

interface Contact {
  id: string
  name: string
  phone: string
  email: string | null
  tags: string[]
  status: string
  engagement_score: number
  created_at: string
  city?: string | null
}

export default function ContactsPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '', email: '', city: '' })
  const [error, setError] = useState('')
  const [uploadMsg, setUploadMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const { data, isLoading } = useQuery<{ items: Contact[]; total: number }>({
    queryKey: ['contacts'],
    queryFn: () => api.get('/contacts').then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (body: typeof form) => {
      const payload = {
        name: body.name,
        phone: body.phone.trim().startsWith('+') ? body.phone.trim() : `+${body.phone.replace(/\D/g, '')}`,
        email: body.email.trim() || undefined,
        city: body.city.trim() || undefined,
      }
      return api.post('/contacts', payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setShowAdd(false)
      setForm({ name: '', phone: '', email: '', city: '' })
      setError('')
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail[0].msg);
      } else {
        setError(typeof detail === 'string' ? detail : 'Error al crear contacto');
      }
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/contacts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contacts'] }),
  })

  const filtered = data?.items.filter(
    (c) =>
      (statusFilter === 'all' || c.status === statusFilter) &&
      (
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.phone.includes(search)
      )
  ) ?? []

  const handleCSVUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadMsg(null)
    setIsUploading(true)
    const fd = new FormData()
    fd.append('file', file)
    try {
      await api.post('/contacts/import-csv', fd)
      setUploadMsg({ type: 'success', text: `Archivo "${file.name}" importado exitosamente.` })
      qc.invalidateQueries({ queryKey: ['contacts'] })
    } catch (err: any) {
      setUploadMsg({ type: 'error', text: err.response?.data?.detail ?? 'Error al importar CSV' })
    } finally {
      setIsUploading(false)
      e.target.value = ''
    }
  }

  const handleExport = async () => {
    try {
      const response = await api.get('/contacts/export-csv', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'contactos_iaradio.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Error al exportar contactos')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contactos</h1>
          <p className="mt-1 text-sm text-gray-500">
            {data?.total ?? 0} contactos en tu lista
          </p>
        </div>
        <div className="flex gap-2">
          <label className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${isUploading ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' : 'border-gray-300 text-gray-700 hover:bg-gray-50'}`}>
            <Upload className="h-4 w-4" />
            {isUploading ? 'Importando...' : 'Importar CSV'}
            <input type="file" accept=".csv" className="hidden" onChange={handleCSVUpload} disabled={isUploading} />
          </label>
          {(data?.total ?? 0) > 0 && (
            <button
              onClick={handleExport}
              disabled={isUploading}
              className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download className="h-4 w-4" />
              Exportar CSV
            </button>
          )}
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Agregar
          </button>
        </div>
      </div>

      {/* Upload feedback */}
      {uploadMsg && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${
          uploadMsg.type === 'success'
            ? 'border-green-200 bg-green-50 text-green-700'
            : 'border-red-200 bg-red-50 text-red-700'
        }`}>
          {uploadMsg.text}
          <button onClick={() => setUploadMsg(null)} className="ml-2 font-medium hover:underline">×</button>
        </div>
      )}

      {/* Status filter tabs */}
      <div className="flex gap-1.5 flex-wrap">
        {[
          { key: 'all', label: 'Todos', count: data?.total ?? 0 },
          { key: 'active', label: 'Activos', count: data?.items.filter((c) => c.status === 'active').length ?? 0 },
          { key: 'unsubscribed', label: 'Bajas', count: data?.items.filter((c) => c.status === 'unsubscribed').length ?? 0 },
          { key: 'blocked', label: 'Bloqueados', count: data?.items.filter((c) => c.status === 'blocked').length ?? 0 },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === tab.key
                ? 'bg-brand-500 text-white'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-brand-300'
            }`}
          >
            {tab.label}
            <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] ${
              statusFilter === tab.key ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-500'
            }`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por nombre o teléfono..."
          className="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        />
      </div>

      {/* Table */}
      <div className="rounded-xl bg-white shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 rounded-lg bg-gray-100 animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Users className="h-12 w-12 mb-3" />
            <p className="text-sm">No hay contactos todavía</p>
            <p className="text-xs mt-1">Importa un CSV o agrega contactos manualmente</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
              <tr>
                <th className="px-6 py-3 text-left">Nombre</th>
                <th className="px-6 py-3 text-left">Teléfono</th>
                <th className="px-6 py-3 text-left">Email</th>
                <th className="px-6 py-3 text-left">Ciudad</th>
                <th className="px-6 py-3 text-left">Estado</th>
                <th className="px-6 py-3 text-left">Agregado</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((contact) => (
                <tr key={contact.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{contact.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{contact.phone}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{contact.email ?? '—'}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{contact.city ?? '—'}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      contact.status === 'active'
                        ? 'bg-green-100 text-green-700'
                        : contact.status === 'unsubscribed'
                        ? 'bg-gray-100 text-gray-600'
                        : 'bg-red-100 text-red-600'
                    }`}>
                      {contact.status === 'active' ? 'Activo' : contact.status === 'unsubscribed' ? 'Dado de baja' : 'Bloqueado'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{formatDate(contact.created_at)}</td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => {
                        if (confirm('¿Eliminar este contacto?')) {
                          deleteMutation.mutate(contact.id)
                        }
                      }}
                      className="text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Contact Modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">Agregar contacto</h3>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Nombre *"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="tel"
                placeholder="Teléfono E.164 * (ej: +521234567890)"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="email"
                placeholder="Email (opcional)"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="text"
                placeholder="Ciudad (opcional)"
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => { setShowAdd(false); setError('') }}
                className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={() => createMutation.mutate(form)}
                disabled={createMutation.isPending || !form.name || !form.phone}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
              >
                {createMutation.isPending ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
