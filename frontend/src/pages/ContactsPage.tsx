import { useState, useRef, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { Users, Plus, Upload, Trash2, Search, Download, Tag, X, Tags, Send, CheckCheck } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import SEO from '@/components/SEO'
import PrintButton from '@/components/PrintButton'

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

interface Campaign {
  id: string
  name: string
}

export default function ContactsPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [tagFilter, setTagFilter] = useState<string>('')
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '', email: '', city: '', tags: [] as string[] })
  const [tagInput, setTagInput] = useState('')
  const [error, setError] = useState('')
  const [uploadMsg, setUploadMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [editTagsId, setEditTagsId] = useState<string | null>(null)
  const [editTagsValue, setEditTagsValue] = useState<string[]>([])
  const [editTagInput, setEditTagInput] = useState('')
  const tagInputRef = useRef<HTMLInputElement>(null)

  // Batch selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showTagModal, setShowTagModal] = useState(false)
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [showCampaignModal, setShowCampaignModal] = useState(false)
  const [batchTagInput, setBatchTagInput] = useState('')
  const [batchTagAction, setBatchTagAction] = useState<'add' | 'remove'>('add')
  const [batchStatus, setBatchStatus] = useState('active')
  const [batchCampaignId, setBatchCampaignId] = useState('')

  const { data, isLoading } = useQuery<{ items: Contact[]; total: number }>({
    queryKey: ['contacts'],
    queryFn: () => api.get('/contacts').then((r) => r.data),
  })

  const campaignsQuery = useQuery<Campaign[]>({
    queryKey: ['campaigns'],
    queryFn: () => api.get('/campaigns').then(r => r.data),
    enabled: showCampaignModal,
  })

  const createMutation = useMutation({
    mutationFn: (body: typeof form) => {
      const payload = {
        name: body.name,
        phone: body.phone.trim().startsWith('+') ? body.phone.trim() : `+${body.phone.replace(/\D/g, '')}`,
        email: body.email.trim() || undefined,
        city: body.city.trim() || undefined,
        tags: body.tags,
      }
      return api.post('/contacts', payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setShowAdd(false)
      setForm({ name: '', phone: '', email: '', city: '', tags: [] })
      setTagInput('')
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

  const updateTagsMutation = useMutation({
    mutationFn: ({ id, tags }: { id: string; tags: string[] }) =>
      api.patch(`/contacts/${id}`, { tags }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setEditTagsId(null)
    },
  })

  const bulkTagMutation = useMutation({
    mutationFn: (body: { contact_ids: string[]; tags: string[]; action: string }) =>
      api.post('/contacts/bulk/tag', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setShowTagModal(false)
      setBatchTagInput('')
      setSelectedIds(new Set())
    },
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: (contact_ids: string[]) =>
      api.post('/contacts/bulk/delete', { contact_ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setSelectedIds(new Set())
    },
  })

  const bulkStatusMutation = useMutation({
    mutationFn: (body: { contact_ids: string[]; status: string }) =>
      api.post('/contacts/bulk/status', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setShowStatusModal(false)
      setSelectedIds(new Set())
    },
  })

  const bulkCampaignMutation = useMutation({
    mutationFn: (body: { contact_ids: string[]; campaign_id: string }) =>
      api.post('/contacts/bulk/send-campaign', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setShowCampaignModal(false)
      setBatchCampaignId('')
      setSelectedIds(new Set())
    },
  })

  // Collect all unique tags from loaded contacts
  const allTags = Array.from(new Set((data?.items ?? []).flatMap((c) => c.tags))).sort()

  const filtered = data?.items.filter(
    (c) =>
      (statusFilter === 'all' || c.status === statusFilter) &&
      (!tagFilter || c.tags.includes(tagFilter)) &&
      (
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.phone.includes(search)
      )
  ) ?? []

  const addTagToForm = () => {
    const t = tagInput.trim().toLowerCase()
    if (t && !form.tags.includes(t)) {
      setForm({ ...form, tags: [...form.tags, t] })
    }
    setTagInput('')
    tagInputRef.current?.focus()
  }

  const addTagToEdit = () => {
    const t = editTagInput.trim().toLowerCase()
    if (t && !editTagsValue.includes(t)) {
      setEditTagsValue([...editTagsValue, t])
    }
    setEditTagInput('')
  }

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

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filtered.map(c => c.id)))
    }
  }

  const handleBulkDelete = () => {
    if (confirm(`¿Eliminar ${selectedIds.size} contactos seleccionados?`)) {
      bulkDeleteMutation.mutate(Array.from(selectedIds))
    }
  }

  const confirmBulkTag = () => {
    const tags = batchTagInput.split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
    if (tags.length === 0) return
    bulkTagMutation.mutate({ contact_ids: Array.from(selectedIds), tags, action: batchTagAction })
  }

  return (
    <>
      <SEO title="Contactos" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6 pb-20">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Contactos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data?.total ?? 0} contactos en tu lista
          </p>
        </div>
        <div className="flex gap-2">
          <PrintButton />
          <label className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${isUploading ? 'bg-muted text-muted-foreground border-border cursor-not-allowed' : 'border-border text-muted-foreground hover:bg-muted'}`}>
            <Upload className="h-4 w-4" />
            {isUploading ? 'Importando...' : 'Importar CSV'}
            <input type="file" accept=".csv" className="hidden" onChange={handleCSVUpload} disabled={isUploading} />
          </label>
          {(data?.total ?? 0) > 0 && (
            <button
              onClick={handleExport}
              disabled={isUploading}
              className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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

      <div className="print-area">
      {/* Upload feedback */}
      {uploadMsg && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${
          uploadMsg.type === 'success'
            ? 'border-green-200 bg-green-50 text-green-700 dark:text-green-300'
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
                : 'bg-card border border-border text-muted-foreground hover:border-brand-300'
            }`}
          >
            {tab.label}
            <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] ${
              statusFilter === tab.key ? 'bg-white/20 text-white' : 'bg-muted text-muted-foreground'
            }`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Tag filter */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <Tag className="h-3.5 w-3.5 text-muted-foreground" />
          <button
            onClick={() => setTagFilter('')}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              !tagFilter ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            Todas
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setTagFilter(tagFilter === tag ? '' : tag)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                tagFilter === tag ? 'bg-brand-500 text-white' : 'bg-purple-50 dark:bg-purple-950/30 text-purple-600 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por nombre o teléfono..."
          className="w-full rounded-lg border border-border py-2.5 pl-10 pr-4 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        />
      </div>

      {/* Table */}
      <div className="rounded-xl bg-card shadow-sm border border-border overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Users className="h-12 w-12 mb-3" />
            <p className="text-sm">No hay contactos todavía</p>
            <p className="text-xs mt-1">Importa un CSV o agrega contactos manualmente</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted text-xs font-medium text-muted-foreground uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.size === filtered.length}
                      onChange={toggleSelectAll}
                      className="rounded border-border text-brand-500 focus:ring-brand-500"
                    />
                  </th>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Teléfono</th>
                  <th className="hidden md:table-cell px-6 py-3 text-left">Email</th>
                  <th className="hidden md:table-cell px-6 py-3 text-left">Ciudad</th>
                  <th className="px-6 py-3 text-left">Tags</th>
                  <th className="px-6 py-3 text-left">Estado</th>
                  <th className="hidden md:table-cell px-6 py-3 text-left">Agregado</th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((contact) => (
                  <Fragment key={contact.id}>
                  <tr className={`hover:bg-muted transition-colors ${selectedIds.has(contact.id) ? 'bg-brand-50/50 dark:bg-brand-950/30' : ''}`}>
                    <td className="px-4 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(contact.id)}
                        onChange={() => toggleSelect(contact.id)}
                        className="rounded border-border text-brand-500 focus:ring-brand-500"
                      />
                    </td>
                    <td className="px-6 py-4 text-sm font-medium text-foreground">{contact.name}</td>
                    <td className="px-6 py-4 text-sm text-muted-foreground">{contact.phone}</td>
                    <td className="hidden md:table-cell px-6 py-4 text-sm text-muted-foreground">{contact.email ?? '—'}</td>
                    <td className="hidden md:table-cell px-6 py-4 text-sm text-muted-foreground">{contact.city ?? '—'}</td>
                    <td className="px-6 py-4 hidden md:table-cell">
                      {editTagsId === contact.id ? (
                        <div className="flex flex-wrap gap-1 min-w-[160px]">
                          {editTagsValue.map((t) => (
                            <span key={t} className="flex items-center gap-0.5 rounded-full bg-purple-100 dark:bg-purple-900/50 px-2 py-0.5 text-xs text-purple-700 dark:text-purple-300">
                              {t}
                              <button onClick={() => setEditTagsValue(editTagsValue.filter((x) => x !== t))} className="ml-0.5 hover:text-red-500">
                                <X className="h-3 w-3" />
                              </button>
                            </span>
                          ))}
                          <input
                            autoFocus
                            type="text"
                            value={editTagInput}
                            onChange={(e) => setEditTagInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTagToEdit() }
                              if (e.key === 'Escape') setEditTagsId(null)
                            }}
                            placeholder="+ tag"
                            className="w-16 rounded border-0 bg-transparent text-xs text-foreground outline-none placeholder-gray-400"
                          />
                          <button
                            onClick={() => updateTagsMutation.mutate({ id: contact.id, tags: editTagsValue })}
                            className="rounded bg-brand-500 px-2 py-0.5 text-[10px] text-white hover:bg-brand-600"
                          >
                            ✓
                          </button>
                          <button onClick={() => setEditTagsId(null)} className="text-muted-foreground hover:text-gray-600">
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <div
                          className="flex flex-wrap gap-1 cursor-pointer group"
                          onClick={() => { setEditTagsId(contact.id); setEditTagsValue([...contact.tags]); setEditTagInput('') }}
                          title="Click para editar tags"
                        >
                          {contact.tags.length > 0
                            ? contact.tags.map((t) => (
                                <span key={t} className="rounded-full bg-purple-50 dark:bg-purple-950/30 px-2 py-0.5 text-xs text-purple-600 dark:text-purple-400">
                                  {t}
                                </span>
                              ))
                            : <span className="text-xs text-muted-foreground group-hover:text-muted-foreground">+ tag</span>
                          }
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        contact.status === 'active'
                          ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300'
                          : contact.status === 'unsubscribed'
                          ? 'bg-muted text-muted-foreground'
                          : 'bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400'
                      }`}>
                        {contact.status === 'active' ? 'Activo' : contact.status === 'unsubscribed' ? 'Dado de baja' : 'Bloqueado'}
                      </span>
                    </td>
                    <td className="hidden md:table-cell px-6 py-4 text-sm text-muted-foreground">{formatDate(contact.created_at)}</td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => {
                          if (confirm('¿Eliminar este contacto?')) {
                            deleteMutation.mutate(contact.id)
                          }
                        }}
                        className="text-muted-foreground hover:text-red-500 transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                  <tr key={`${contact.id}-mobile`} className="md:hidden">
                    <td colSpan={9} className="px-4 py-3">
                      <div className="border rounded-xl p-4 space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="font-medium text-foreground">{contact.name}</div>
                          <span className={`shrink-0 inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            contact.status === 'active'
                              ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300'
                              : contact.status === 'unsubscribed'
                              ? 'bg-muted text-muted-foreground'
                              : 'bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400'
                          }`}>
                            {contact.status === 'active' ? 'Activo' : contact.status === 'unsubscribed' ? 'Dado de baja' : 'Bloqueado'}
                          </span>
                        </div>
                        <div className="text-sm text-muted-foreground">{contact.phone}</div>
                        <div className="text-sm text-muted-foreground">{contact.email ?? '—'}  ·  {contact.city ?? '—'}</div>
                        <div className="text-xs text-muted-foreground">Agregado {formatDate(contact.created_at)}</div>
                        <div className="flex flex-wrap gap-1">
                          {contact.tags.length > 0
                            ? contact.tags.map((t) => (
                                <span key={t} className="rounded-full bg-purple-50 dark:bg-purple-950/30 px-2 py-0.5 text-xs text-purple-600 dark:text-purple-400">{t}</span>
                              ))
                            : <span className="text-xs text-muted-foreground">Sin etiquetas</span>
                          }
                        </div>
                        <div className="flex justify-end gap-2 pt-1">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(contact.id)}
                            onChange={() => toggleSelect(contact.id)}
                            className="rounded border-border text-brand-500 focus:ring-brand-500"
                          />
                          <button
                            onClick={() => {
                              if (confirm('¿Eliminar este contacto?')) {
                                deleteMutation.mutate(contact.id)
                              }
                            }}
                            className="text-muted-foreground hover:text-red-500 transition-colors p-1"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Batch actions toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-2xl bg-card border border-border shadow-xl px-5 py-3">
          <span className="text-sm font-medium text-foreground whitespace-nowrap">
            <CheckCheck className="inline h-4 w-4 mr-1 text-brand-500" />
            {selectedIds.size} seleccionados
          </span>
          <div className="h-6 w-px bg-border" />
          <button
            onClick={() => setShowTagModal(true)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-950/30 transition-colors"
          >
            <Tags size={15} />
            Etiqueta
          </button>
          <button
            onClick={() => setShowStatusModal(true)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <CheckCheck size={15} />
            Estado
          </button>
          <button
            onClick={() => setShowCampaignModal(true)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/30 transition-colors"
          >
            <Send size={15} />
            Campaña
          </button>
          <div className="h-6 w-px bg-border" />
          <button
            onClick={handleBulkDelete}
            disabled={bulkDeleteMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            <Trash2 size={15} />
            Eliminar
          </button>
        </div>
      )}

      {/* Add Contact Modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-card-foreground">Agregar contacto</h3>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Nombre *"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="tel"
                placeholder="Teléfono E.164 * (ej: +521234567890)"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="email"
                placeholder="Email (opcional)"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <input
                type="text"
                placeholder="Ciudad (opcional)"
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
              <div>
                <div className="flex flex-wrap gap-1.5 mb-1.5 min-h-[1.5rem]">
                  {form.tags.map((t) => (
                    <span key={t} className="flex items-center gap-0.5 rounded-full bg-purple-100 dark:bg-purple-900/50 px-2.5 py-0.5 text-xs text-purple-700 dark:text-purple-300">
                      {t}
                      <button onClick={() => setForm({ ...form, tags: form.tags.filter((x) => x !== t) })} className="ml-0.5 hover:text-red-500">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    ref={tagInputRef}
                    type="text"
                    placeholder="Agregar tag (Enter para confirmar)"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTagToForm() }
                    }}
                    className="flex-1 rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={addTagToForm}
                    disabled={!tagInput.trim()}
                    className="rounded-lg border border-purple-200 bg-purple-50 dark:bg-purple-950/30 px-3 text-xs font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50 disabled:opacity-40"
                  >
                    + Tag
                  </button>
                </div>
              </div>
              {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            </div>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => { setShowAdd(false); setError(''); setForm({ name: '', phone: '', email: '', city: '', tags: [] }); setTagInput('') }}
                className="flex-1 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted"
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

      {/* Batch Tag Modal */}
      {showTagModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowTagModal(false)}>
          <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-semibold text-card-foreground">Asignar etiquetas</h3>
            <p className="text-sm text-muted-foreground mb-3">{selectedIds.size} contactos seleccionados</p>
            <div className="space-y-3">
              <div className="flex gap-2">
                <button
                  onClick={() => setBatchTagAction('add')}
                  className={`flex-1 rounded-lg py-2 text-sm font-medium transition-colors ${batchTagAction === 'add' ? 'bg-brand-500 text-white' : 'bg-muted text-muted-foreground'}`}
                >
                  Agregar
                </button>
                <button
                  onClick={() => setBatchTagAction('remove')}
                  className={`flex-1 rounded-lg py-2 text-sm font-medium transition-colors ${batchTagAction === 'remove' ? 'bg-red-500 text-white' : 'bg-muted text-muted-foreground'}`}
                >
                  Quitar
                </button>
              </div>
              <input
                type="text"
                placeholder="etiqueta1, etiqueta2, ..."
                value={batchTagInput}
                onChange={e => setBatchTagInput(e.target.value)}
                className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="mt-5 flex gap-3">
              <button onClick={() => setShowTagModal(false)} className="flex-1 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted">Cancelar</button>
              <button
                onClick={confirmBulkTag}
                disabled={!batchTagInput.trim() || bulkTagMutation.isPending}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
              >
                {bulkTagMutation.isPending ? 'Guardando...' : 'Aplicar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch Status Modal */}
      {showStatusModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowStatusModal(false)}>
          <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-semibold text-card-foreground">Cambiar estado</h3>
            <p className="text-sm text-muted-foreground mb-3">{selectedIds.size} contactos seleccionados</p>
            <select
              value={batchStatus}
              onChange={e => setBatchStatus(e.target.value)}
              className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="active">Activo</option>
              <option value="unsubscribed">Dado de baja</option>
              <option value="blocked">Bloqueado</option>
            </select>
            <div className="mt-5 flex gap-3">
              <button onClick={() => setShowStatusModal(false)} className="flex-1 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted">Cancelar</button>
              <button
                onClick={() => bulkStatusMutation.mutate({ contact_ids: Array.from(selectedIds), status: batchStatus })}
                disabled={bulkStatusMutation.isPending}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
              >
                {bulkStatusMutation.isPending ? 'Guardando...' : 'Cambiar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch Campaign Modal */}
      {showCampaignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowCampaignModal(false)}>
          <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-semibold text-card-foreground">Enviar a campaña</h3>
            <p className="text-sm text-muted-foreground mb-3">{selectedIds.size} contactos seleccionados</p>
            <select
              value={batchCampaignId}
              onChange={e => setBatchCampaignId(e.target.value)}
              className="w-full rounded-lg border border-border px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">Seleccionar campaña...</option>
              {(campaignsQuery.data ?? []).map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <div className="mt-5 flex gap-3">
              <button onClick={() => setShowCampaignModal(false)} className="flex-1 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted">Cancelar</button>
              <button
                onClick={() => bulkCampaignMutation.mutate({ contact_ids: Array.from(selectedIds), campaign_id: batchCampaignId })}
                disabled={!batchCampaignId || bulkCampaignMutation.isPending}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
              >
                {bulkCampaignMutation.isPending ? 'Programando...' : 'Enviar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
    </>
  )
}
