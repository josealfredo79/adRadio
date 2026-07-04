import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { Plus, Trash2, X, Phone } from 'lucide-react'

interface PoolNumber {
  number: string
  label: string | null
  assigned_to: string | null
  active: boolean
}

interface NumbersResponse {
  numbers: PoolNumber[]
}

export default function AdminNumbersPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newNumber, setNewNumber] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const { data, isLoading } = useQuery<NumbersResponse>({
    queryKey: ['admin-numbers'],
    queryFn: () => api.get('/admin/number-pool?include_inactive=true').then((r) => r.data),
    staleTime: 1000 * 60,
  })

  const addMutation = useMutation({
    mutationFn: (body: { number: string; label?: string }) =>
      api.post('/admin/number-pool', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-numbers'] })
      setShowAdd(false)
      setNewNumber('')
      setNewLabel('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (number: string) =>
      api.delete(`/admin/number-pool/${encodeURIComponent(number)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-numbers'] }),
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newNumber.trim()) return
    const body: { number: string; label?: string } = { number: newNumber.trim() }
    if (newLabel.trim()) body.label = newLabel.trim()
    addMutation.mutate(body)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pool de Números</h1>
          <p className="text-sm text-muted-foreground">Gestiona los números WhatsApp disponibles</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600 transition-colors"
        >
          <Plus className="h-4 w-4" /> Agregar número
        </button>
      </div>

      {/* Numbers list */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-muted-foreground">Cargando...</div>
        ) : !data?.numbers.length ? (
          <div className="p-8 text-center text-muted-foreground">
            <Phone className="h-12 w-12 mx-auto mb-3 text-muted-foreground/50" />
            <p>No hay números en el pool</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Número</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Etiqueta</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Asignado a</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Estado</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.numbers.map((n) => (
                  <tr key={n.number} className="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-foreground">{n.number}</td>
                    <td className="px-4 py-3 text-muted-foreground">{n.label || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{n.assigned_to || 'Disponible'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${n.active ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300'}`}>
                        {n.active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {n.active && !n.assigned_to && (
                        <button
                          onClick={() => deleteMutation.mutate(n.number)}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-muted-foreground hover:text-red-600 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-2xl bg-card p-6 shadow-2xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-foreground">Agregar Número</h2>
              <button onClick={() => setShowAdd(false)} className="p-1 rounded-lg hover:bg-muted">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Número WhatsApp</label>
                <input
                  type="text"
                  value={newNumber}
                  onChange={(e) => setNewNumber(e.target.value)}
                  placeholder="+525511111111"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Etiqueta (opcional)</label>
                <input
                  type="text"
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  placeholder="Ej: Línea principal"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  className="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={addMutation.isPending || !newNumber.trim()}
                  className="px-4 py-2 rounded-lg text-sm bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
                >
                  {addMutation.isPending ? 'Agregando...' : 'Agregar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
