import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Package, Plus, Trash2, Pencil, ImageUp, ImageOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import SEO from '@/components/SEO'
import { useToast } from '@/contexts/ToastContext'

interface Product {
  id: string
  name: string
  description: string | null
  price: string | null
  category: string | null
  photo_url: string | null
  active: boolean
  created_at: string
}

const EMPTY_FORM = { name: '', description: '', price: '', category: '', active: true }

const formatPrice = (price: string | null) =>
  price === null
    ? 'Cotizar'
    : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(price))

export default function ProductsPage() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const photoInputRefs = useRef<Record<string, HTMLInputElement | null>>({})
  const [uploadingPhotoFor, setUploadingPhotoFor] = useState<string | null>(null)

  const { data: products, isLoading } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products').then(r => r.data),
  })

  const resetForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  const createMutation = useMutation({
    mutationFn: (data: typeof form) =>
      api.post('/products', { ...data, price: data.price ? Number(data.price) : null, category: data.category || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] })
      resetForm()
    },
    onError: (err: unknown) => toast({ title: 'Error', description: getApiError(err, 'No se pudo crear el producto'), variant: 'error' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: typeof form }) =>
      api.patch(`/products/${id}`, { ...data, price: data.price ? Number(data.price) : null, category: data.category || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] })
      resetForm()
    },
    onError: (err: unknown) => toast({ title: 'Error', description: getApiError(err, 'No se pudo editar el producto'), variant: 'error' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/products/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }),
  })

  const startEdit = (p: Product) => {
    setEditingId(p.id)
    setForm({
      name: p.name,
      description: p.description || '',
      price: p.price ?? '',
      category: p.category || '',
      active: p.active,
    })
    setShowForm(true)
  }

  const handlePhotoUpload = async (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    setUploadingPhotoFor(id)
    try {
      await api.post(`/products/${id}/photo`, fd)
      qc.invalidateQueries({ queryKey: ['products'] })
    } catch (err: unknown) {
      toast({ title: 'Error', description: getApiError(err, 'No se pudo subir la foto'), variant: 'error' })
    } finally {
      setUploadingPhotoFor(null)
      const input = photoInputRefs.current[id]
      if (input) input.value = ''
    }
  }

  return (
    <>
      <SEO title="Catálogo" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6 max-w-4xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-brand-50 dark:bg-brand-950/30 p-2.5">
              <Package className="h-5 w-5 text-brand-500" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Catálogo</h1>
              <p className="text-sm text-muted-foreground">Productos y servicios que tu bot puede mostrar a tus clientes</p>
            </div>
          </div>
          <button
            onClick={() => (showForm ? resetForm() : setShowForm(true))}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
          >
            <Plus size={16} />
            Nuevo
          </button>
        </div>

        {showForm && (
          <div className="rounded-xl bg-card border border-border p-5 space-y-4">
            <h2 className="font-semibold text-foreground">{editingId ? 'Editar producto' : 'Nuevo producto'}</h2>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Nombre</label>
              <input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
                placeholder="Ej: Corte de cabello, Pizza Margarita..."
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Precio (MXN)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.price}
                  onChange={e => setForm({ ...form, price: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
                  placeholder="Déjalo vacío para 'Cotizar'"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Categoría</label>
                <input
                  value={form.category}
                  onChange={e => setForm({ ...form, category: e.target.value })}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none"
                  placeholder="Ej: Comida, Bebidas, Servicios..."
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Descripción</label>
              <textarea
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-500 focus:outline-none resize-none"
                rows={2}
                placeholder="Descripción breve (opcional)"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={form.active}
                onChange={e => setForm({ ...form, active: e.target.checked })}
                className="rounded border-border"
              />
              Visible en la landing y el bot
            </label>

            <div className="flex justify-end gap-2 border-t border-border pt-4">
              <button onClick={resetForm} className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted">
                Cancelar
              </button>
              <button
                onClick={() => (editingId ? updateMutation.mutate({ id: editingId, data: form }) : createMutation.mutate(form))}
                disabled={!form.name || createMutation.isPending || updateMutation.isPending}
                className="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
              >
                {createMutation.isPending || updateMutation.isPending ? 'Guardando...' : editingId ? 'Guardar cambios' : 'Crear producto'}
              </button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-xl" />)}
          </div>
        ) : !products?.length ? (
          <div className="rounded-xl bg-muted border border-border p-8 text-center text-sm text-muted-foreground">
            No tienes productos en tu catálogo aún. Agrega uno para que tu bot pueda mostrarlo.
          </div>
        ) : (
          <div className="space-y-3">
            {products.map(p => (
              <div key={p.id} className="rounded-xl bg-card border border-border p-5 flex items-start justify-between gap-4">
                <div className="flex items-start gap-4 min-w-0 flex-1">
                  <div className="shrink-0 h-16 w-16 rounded-lg bg-muted border border-border overflow-hidden flex items-center justify-center">
                    {p.photo_url ? (
                      <img src={p.photo_url} alt={p.name} className="h-full w-full object-cover" />
                    ) : (
                      <ImageOff className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold text-foreground">{p.name}</h3>
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full font-medium',
                        p.active
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                          : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                      )}>
                        {p.active ? 'Visible' : 'Oculto'}
                      </span>
                      {p.category && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                          {p.category}
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-brand-600 dark:text-brand-400">{formatPrice(p.price)}</p>
                    {p.description && <p className="text-sm text-muted-foreground">{p.description}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <input
                    ref={el => { photoInputRefs.current[p.id] = el }}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) handlePhotoUpload(p.id, file)
                    }}
                  />
                  <button
                    onClick={() => photoInputRefs.current[p.id]?.click()}
                    disabled={uploadingPhotoFor === p.id}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
                    title="Subir foto"
                  >
                    <ImageUp size={16} />
                  </button>
                  <button
                    onClick={() => startEdit(p)}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted transition-colors"
                    title="Editar"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => { if (confirm('¿Eliminar este producto?')) deleteMutation.mutate(p.id) }}
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
