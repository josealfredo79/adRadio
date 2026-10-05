import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Plus, Trash2, Users } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'

// Personal que atiende citas (users.staff). Con personal, a la misma hora
// caben tantas citas como personas libres, y el cliente puede pedir "con
// Lupita"; si no pide a nadie, el agente asigna a quien esté libre.
type Person = { name: string; services: string[] }

export default function StaffCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Person[]>(() => user?.staff ?? [])
  const [saved, setSaved] = useState(false)
  const services = (user?.appointment_services ?? []).map((s) => s.name)

  const save = useMutation({
    mutationFn: () =>
      api
        .patch('/me', { staff: rows.map((r) => ({ ...r, name: r.name.trim() })).filter((r) => r.name) })
        .then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      setRows(updated.staff ?? [])
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const update = (i: number, patch: Partial<Person>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const toggle = (i: number, service: string) =>
    update(i, {
      services: rows[i].services.includes(service)
        ? rows[i].services.filter((s) => s !== service)
        : [...rows[i].services, service],
    })

  return (
    <div className="rounded-xl bg-white border border-gray-100 shadow-sm dark:bg-gray-950 dark:border-gray-800">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between p-4 text-left">
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
          <Users className="h-4 w-4" />
          Personal que atiende
          {rows.length > 0 && <span className="text-xs font-normal text-gray-400">({rows.length})</span>}
        </span>
        <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-gray-100 p-4 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Con personal, a la misma hora caben tantas citas como personas libres y tus clientes pueden pedir con quién.
            Si no marcas servicios, esa persona hace todos. Sin personal, se agenda una cita a la vez.
          </p>
          {rows.map((r, i) => (
            <div key={i} className="space-y-2 rounded-lg border border-gray-100 p-3 dark:border-gray-800">
              <div className="flex items-center gap-2">
                <input
                  value={r.name}
                  maxLength={80}
                  placeholder="Ej. Lupita"
                  onChange={(e) => update(i, { name: e.target.value })}
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-700 dark:bg-gray-950"
                />
                <button
                  onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                  aria-label={`Quitar ${r.name || 'persona'}`}
                  className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              {services.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {services.map((s) => {
                    const on = r.services.includes(s)
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() => toggle(i, s)}
                        aria-pressed={on}
                        className={`rounded-full border px-2.5 py-1 text-xs ${
                          on
                            ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300'
                            : 'border-gray-200 text-gray-500 dark:border-gray-800 dark:text-gray-400'
                        }`}
                      >
                        {s}
                      </button>
                    )
                  })}
                  <span className="self-center text-xs text-gray-400">
                    {r.services.length ? '' : '· hace todos'}
                  </span>
                </div>
              )}
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setRows((rs) => [...rs, { name: '', services: [] }])}
              disabled={rows.length >= 30}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-900"
            >
              <Plus className="h-4 w-4" /> Agregar persona
            </button>
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 dark:bg-brand-600 dark:hover:bg-brand-700"
            >
              {save.isPending ? 'Guardando…' : saved ? 'Guardado ✓' : 'Guardar personal'}
            </button>
          </div>
          {save.isError && <p className="text-sm text-red-600">{getApiError(save.error, 'No se pudo guardar')}</p>}
        </div>
      )}
    </div>
  )
}
