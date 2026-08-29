import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth, type CloserConfig } from '@/contexts/AuthContext'
import { Check, Flame, Loader2 } from 'lucide-react'

const DEFAULTS: CloserConfig = {
  enabled: false,
  hold_hours: 2,
  discount_type: 'percentage',
  discount_value: 15,
  label: 'Apartado especial',
  message: null,
}

export default function CloserCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [cfg, setCfg] = useState<CloserConfig>(DEFAULTS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (user?.closer_config) setCfg({ ...DEFAULTS, ...user.closer_config })
  }, [user])

  const mutation = useMutation({
    mutationFn: (data: CloserConfig) =>
      api.patch('/me', { closer_config: data }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const set = <K extends keyof CloserConfig>(k: K, v: CloserConfig[K]) => setCfg({ ...cfg, [k]: v })
  const inputCls =
    'w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none'

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <Flame className="h-5 w-5 text-orange-500" />
        <h2 className="text-base font-semibold text-foreground">Bot Closer</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Cuando el bot detecta intención de compra alta, cierra con una oferta que{' '}
        <span className="font-medium">de verdad caduca</span>: un cupón para ese cliente con hora de
        vencimiento real, y un recordatorio antes de que expire. Nada de escasez inventada.
      </p>

      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input type="checkbox" checked={cfg.enabled} onChange={(e) => set('enabled', e.target.checked)} />
        Activar el Bot Closer
      </label>

      {cfg.enabled && (
        <div className="space-y-3 border-l-2 border-orange-200 pl-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Vigencia del apartado</label>
              <select
                value={cfg.hold_hours}
                onChange={(e) => set('hold_hours', Number(e.target.value))}
                className={inputCls}
              >
                <option value={1}>1 hora</option>
                <option value={2}>2 horas</option>
                <option value={4}>4 horas</option>
                <option value={24}>24 horas</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Etiqueta de la oferta</label>
              <input
                type="text"
                value={cfg.label}
                onChange={(e) => set('label', e.target.value)}
                placeholder="Apartado especial"
                className={inputCls}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Descuento</label>
              <select
                value={cfg.discount_value > 0 ? cfg.discount_type : 'none'}
                onChange={(e) => {
                  if (e.target.value === 'none') set('discount_value', 0)
                  else set('discount_type', e.target.value as CloserConfig['discount_type'])
                }}
                className={inputCls}
              >
                <option value="none">Sin descuento (solo apartar el precio)</option>
                <option value="percentage">Porcentaje</option>
                <option value="fixed">Monto fijo</option>
              </select>
            </div>
            {cfg.discount_value > 0 || cfg.discount_type !== 'percentage' ? (
              <div>
                <label className="block text-xs text-muted-foreground mb-1">
                  {cfg.discount_type === 'fixed' ? 'Monto ($)' : 'Porcentaje (%)'}
                </label>
                <input
                  type="number"
                  min={0}
                  value={cfg.discount_value}
                  onChange={(e) => set('discount_value', Number(e.target.value))}
                  className={inputCls}
                />
              </div>
            ) : null}
          </div>

          <div>
            <label className="block text-xs text-muted-foreground mb-1">
              Mensaje de la oferta (opcional)
            </label>
            <textarea
              rows={2}
              value={cfg.message ?? ''}
              onChange={(e) => set('message', e.target.value || null)}
              placeholder="Ej: Te aparto el precio y tu lugar por 2 horas."
              className={`${inputCls} resize-none`}
            />
          </div>

          <p className="text-xs text-muted-foreground">
            Si tienes horarios configurados y quedan pocos lugares, el bot lo menciona con el número
            real. En negocios de producto la oferta es solo por tiempo.
          </p>
        </div>
      )}

      {mutation.isError && (
        <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>
      )}
      <button
        onClick={() => mutation.mutate(cfg)}
        disabled={mutation.isPending}
        className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
      >
        {mutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {saved ? <><Check className="h-3.5 w-3.5" /> Guardado</> : 'Guardar'}
      </button>
    </div>
  )
}
