import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Plus, Scissors, Trash2 } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'

// Servicios que se agendan y cuánto duran (users.appointment_services). El
// agente inteligente aparta ese tiempo: un tinte de 2 h no se empalma con el
// corte de las 11. Sin servicios, cada cita dura 30 min como siempre.
type Service = { name: string; minutes: number }

const DURATIONS = Array.from({ length: 32 }, (_, i) => (i + 1) * 15)

function label(min: number) {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (!h) return `${m} min`
  return m ? `${h} h ${m} min` : `${h} h`
}

export default function AppointmentServicesCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Service[]>(() => user?.appointment_services ?? [])
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api
        .patch('/me', { appointment_services: rows.map((r) => ({ ...r, name: r.name.trim() })).filter((r) => r.name) })
        .then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      setRows(updated.appointment_services ?? [])
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const update = (i: number, patch: Partial<Service>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  return (
    <div className="rounded-xl bg-white border border-gray-100 shadow-sm dark:bg-gray-950 dark:border-gray-800">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between p-4 text-left">
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
          <Scissors className="h-4 w-4" />
          Servicios y cuánto duran
          {rows.length > 0 && <span className="text-xs font-normal text-gray-400">({rows.length})</span>}
        </span>
        <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-gray-100 p-4 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            El agente inteligente aparta el tiempo de cada servicio y solo ofrece horarios donde cabe completo. Si no
            agregas servicios, cada cita dura 30 min.
          </p>
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={r.name}
                maxLength={80}
                placeholder="Ej. Tinte completo"
                onChange={(e) => update(i, { name: e.target.value })}
                className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-700 dark:bg-gray-950"
              />
              <select
                value={r.minutes}
                onChange={(e) => update(i, { minutes: Number(e.target.value) })}
                aria-label={`Duración de ${r.name || 'servicio'}`}
                className="rounded-lg border border-gray-300 px-2 py-2 text-sm dark:border-gray-700 dark:bg-gray-950"
              >
                {DURATIONS.map((d) => (
                  <option key={d} value={d}>{label(d)}</option>
                ))}
              </select>
              <button
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                aria-label={`Quitar ${r.name || 'servicio'}`}
                className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setRows((rs) => [...rs, { name: '', minutes: 30 }])}
              disabled={rows.length >= 40}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-900"
            >
              <Plus className="h-4 w-4" /> Agregar servicio
            </button>
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 dark:bg-brand-600 dark:hover:bg-brand-700"
            >
              {save.isPending ? 'Guardando…' : saved ? 'Guardado ✓' : 'Guardar servicios'}
            </button>
          </div>
          {save.isError && <p className="text-sm text-red-600">{getApiError(save.error, 'No se pudo guardar')}</p>}
        </div>
      )}
    </div>
  )
}
