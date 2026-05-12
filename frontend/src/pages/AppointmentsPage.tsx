import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { CalendarDays, Plus, Trash2, Check, X, Clock, ExternalLink, Unplug } from 'lucide-react'

interface Appointment {
  id: string
  customer_name: string
  customer_phone: string | null
  service: string
  scheduled_at: string
  duration_min: number
  notes: string | null
  status: string
  google_event_id: string | null
  contact_id: string | null
  created_at: string
}

interface AppointmentStats {
  total: number
  upcoming: number
  today: number
  google_connected: boolean
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  confirmed: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
  no_show: 'bg-red-100 text-red-600',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmada',
  completed: 'Completada',
  cancelled: 'Cancelada',
  no_show: 'No asistió',
}

export default function AppointmentsPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({
    customer_name: '',
    customer_phone: '',
    service: '',
    scheduled_at: '',
    duration_min: 30,
    notes: '',
  })
  const [error, setError] = useState('')

  const { data: stats } = useQuery<AppointmentStats>({
    queryKey: ['appointment-stats'],
    queryFn: () => api.get('/appointments/stats').then((r) => r.data),
  })

  const { data: appointments, isLoading } = useQuery<Appointment[]>({
    queryKey: ['appointments'],
    queryFn: () => api.get('/appointments').then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (body: any) => api.post('/appointments', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['appointment-stats'] })
      setShowCreate(false)
      resetForm()
    },
    onError: (err: any) => setError(err.response?.data?.detail ?? 'Error al crear cita'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...body }: any) => api.patch(`/appointments/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['appointment-stats'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/appointments/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['appointment-stats'] })
    },
  })

  const resetForm = () => {
    setForm({ customer_name: '', customer_phone: '', service: '', scheduled_at: '', duration_min: 30, notes: '' })
    setError('')
  }

  const handleCreate = () => {
    if (!form.customer_name || !form.service || !form.scheduled_at) return
    createMutation.mutate({
      ...form,
      scheduled_at: new Date(form.scheduled_at).toISOString(),
      customer_phone: form.customer_phone || undefined,
      notes: form.notes || undefined,
    })
  }

  const connectGoogle = async () => {
    try {
      const { data } = await api.get('/appointments/google/connect')
      window.open(data.auth_url, '_blank', 'width=500,height=600')
    } catch {
      setError('Google Calendar no configurado en el servidor')
    }
  }

  const disconnectGoogle = async () => {
    if (!confirm('¿Desconectar Google Calendar?')) return
    await api.delete('/appointments/google/disconnect')
    qc.invalidateQueries({ queryKey: ['appointment-stats'] })
  }

  // Group appointments by date
  const grouped = (appointments ?? []).reduce<Record<string, Appointment[]>>((acc, a) => {
    const date = new Date(a.scheduled_at).toLocaleDateString('es-MX', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
    if (!acc[date]) acc[date] = []
    acc[date].push(a)
    return acc
  }, {})

  const now = new Date()
  const isUpcoming = (a: Appointment) => new Date(a.scheduled_at) >= now && ['pending', 'confirmed'].includes(a.status)
  const isPast = (a: Appointment) => !isUpcoming(a)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Citas</h1>
          <p className="mt-1 text-sm text-gray-500">
            {stats?.today ?? 0} hoy · {stats?.upcoming ?? 0} próximas · {stats?.total ?? 0} total
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Google Calendar connection */}
          {stats?.google_connected ? (
            <button
              onClick={disconnectGoogle}
              className="flex items-center gap-1.5 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs font-medium text-green-700 hover:bg-green-100 transition-colors"
            >
              <Check className="h-3.5 w-3.5" />
              Google Calendar
              <Unplug className="h-3 w-3 ml-1 opacity-50" />
            </button>
          ) : (
            <button
              onClick={connectGoogle}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <CalendarDays className="h-3.5 w-3.5" />
              Conectar Google Calendar
            </button>
          )}
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
          >
            <Plus className="h-4 w-4" /> Nueva cita
          </button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl bg-white border border-gray-100 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Hoy</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">{stats?.today ?? 0}</p>
        </div>
        <div className="rounded-xl bg-white border border-gray-100 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Próximas</p>
          <p className="mt-1 text-2xl font-bold text-brand-600">{stats?.upcoming ?? 0}</p>
        </div>
        <div className="rounded-xl bg-white border border-gray-100 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Total</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">{stats?.total ?? 0}</p>
        </div>
      </div>

      {/* Appointments list */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-20 rounded-xl bg-gray-100 animate-pulse" />)}
        </div>
      ) : (appointments?.length ?? 0) === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl bg-white py-16 shadow-sm border border-gray-100 text-gray-400">
          <CalendarDays className="h-12 w-12 mb-3" />
          <p className="text-sm font-medium">No hay citas todavía</p>
          <p className="text-xs mt-1">Crea tu primera cita o espera que un cliente agende por WhatsApp</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([date, appts]) => (
            <div key={date}>
              <h3 className="mb-2 text-sm font-semibold text-gray-600 capitalize">{date}</h3>
              <div className="space-y-2">
                {appts.map((a) => (
                  <div key={a.id} className={`rounded-xl bg-white p-4 shadow-sm border transition-all ${
                    isUpcoming(a) ? 'border-brand-100' : 'border-gray-100 opacity-75'
                  }`}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-gray-900">{a.customer_name}</span>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_COLORS[a.status] ?? 'bg-gray-100 text-gray-600'}`}>
                            {STATUS_LABELS[a.status] ?? a.status}
                          </span>
                          {a.google_event_id && (
                            <span className="text-[10px] text-blue-500">📅 Google</span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-gray-600">{a.service}</p>
                        <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-400">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {new Date(a.scheduled_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                            {' · '}{a.duration_min} min
                          </span>
                          {a.customer_phone && <span>📱 {a.customer_phone}</span>}
                        </div>
                        {a.notes && <p className="mt-1 text-xs text-gray-400 italic">{a.notes}</p>}
                      </div>
                      <div className="flex items-center gap-1 ml-3">
                        {a.status === 'pending' && (
                          <button
                            onClick={() => updateMutation.mutate({ id: a.id, status: 'confirmed' })}
                            className="rounded-lg border border-green-200 bg-green-50 p-1.5 text-green-600 hover:bg-green-100"
                            title="Confirmar"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {['pending', 'confirmed'].includes(a.status) && (
                          <button
                            onClick={() => updateMutation.mutate({ id: a.id, status: 'cancelled' })}
                            className="rounded-lg border border-red-200 bg-red-50 p-1.5 text-red-600 hover:bg-red-100"
                            title="Cancelar"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {a.status === 'confirmed' && isPast(a) && (
                          <button
                            onClick={() => updateMutation.mutate({ id: a.id, status: 'completed' })}
                            className="rounded-lg border border-brand-200 bg-brand-50 p-1.5 text-brand-600 hover:bg-brand-100"
                            title="Marcar completada"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => { if (confirm('¿Eliminar esta cita?')) deleteMutation.mutate(a.id) }}
                          className="text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="mb-5 text-lg font-semibold text-gray-900">Nueva cita</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Nombre del cliente *</label>
                <input type="text" placeholder="Ej: María López"
                  value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Teléfono (WhatsApp)</label>
                <input type="text" placeholder="Ej: +521234567890"
                  value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Servicio *</label>
                <input type="text" placeholder="Ej: Corte de cabello, Consulta dental"
                  value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Fecha y hora *</label>
                  <input type="datetime-local"
                    value={form.scheduled_at}
                    min={new Date().toISOString().slice(0, 16)}
                    onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Duración</label>
                  <select value={form.duration_min} onChange={(e) => setForm({ ...form, duration_min: Number(e.target.value) })}
                    className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none">
                    <option value={15}>15 min</option>
                    <option value={30}>30 min</option>
                    <option value={45}>45 min</option>
                    <option value={60}>1 hora</option>
                    <option value={90}>1.5 horas</option>
                    <option value={120}>2 horas</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Notas (opcional)</label>
                <textarea rows={2} placeholder="Alguna nota sobre la cita..."
                  value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none" />
              </div>

              {stats?.google_connected && (
                <p className="text-xs text-green-600 bg-green-50 rounded-lg px-3 py-2">
                  📅 Esta cita se sincronizará automáticamente con tu Google Calendar
                </p>
              )}

              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>

            <div className="mt-5 flex gap-3">
              <button onClick={() => { setShowCreate(false); resetForm() }}
                className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm text-gray-700 hover:bg-gray-50">
                Cancelar
              </button>
              <button onClick={handleCreate}
                disabled={createMutation.isPending || !form.customer_name || !form.service || !form.scheduled_at}
                className="flex-1 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60">
                {createMutation.isPending ? 'Creando...' : 'Crear cita'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
