import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth, type LoyaltyConfig } from '@/contexts/AuthContext'
import { Check, Loader2, Stamp } from 'lucide-react'
import { LOYALTY_ANCHOR, LOYALTY_DEFAULTS } from '@/lib/loyalty'

const DEFAULTS = LOYALTY_DEFAULTS

// Tarjeta de lealtad del portal del cliente (backend: loyalty_service.py). Es
// el regalo que hace que el cliente prefiera la web a WhatsApp.
export default function LoyaltySettingsCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [cfg, setCfg] = useState<LoyaltyConfig>(DEFAULTS)
  const [saved, setSaved] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // Desde el aviso del Dashboard (/app/settings#tarjeta-lealtad).
  useEffect(() => {
    if (window.location.hash === `#${LOYALTY_ANCHOR}`) rootRef.current?.scrollIntoView({ block: 'start' })
  }, [])

  useEffect(() => {
    if (user?.loyalty_config) setCfg({ ...DEFAULTS, ...user.loyalty_config })
  }, [user])

  const mutation = useMutation({
    mutationFn: (data: LoyaltyConfig) => api.patch('/me', { loyalty_config: data }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const set = <K extends keyof LoyaltyConfig>(k: K, v: LoyaltyConfig[K]) => setCfg({ ...cfg, [k]: v })
  const inputCls =
    'w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none'

  return (
    <div ref={rootRef} id={LOYALTY_ANCHOR} className="scroll-mt-4 rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <Stamp className="h-5 w-5 text-amber-500" />
        <h2 className="text-base font-semibold text-foreground">Tarjeta de lealtad</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Tus clientes juntan sellos en su página personal (la que el bot les manda por WhatsApp) y al llenar la
        tarjeta ganan el premio que tú elijas. Los sellos caen solos: cada cita que marcas como completada y cada
        pedido confirmado. De regalo de bienvenida reciben uno al abrir su tarjeta y otro al activar los avisos —
        y cada aviso por ahí es un WhatsApp que no pagas.
      </p>

      <label className="flex items-center gap-2 text-sm font-medium text-foreground">
        <input type="checkbox" checked={cfg.enabled} onChange={(e) => set('enabled', e.target.checked)} />
        Activar la tarjeta de lealtad
      </label>

      {cfg.enabled && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 border-l-2 border-amber-200 pl-4">
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Sellos para el premio</label>
            <select
              value={cfg.stamps_required}
              onChange={(e) => set('stamps_required', Number(e.target.value))}
              className={inputCls}
            >
              {[5, 6, 8, 10, 12].map((n) => (
                <option key={n} value={n}>
                  {n} sellos
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs text-muted-foreground mb-1">Premio</label>
            <input
              type="text"
              maxLength={120}
              value={cfg.reward}
              onChange={(e) => set('reward', e.target.value)}
              placeholder="Ej: Un corte gratis"
              className={inputCls}
            />
          </div>
          {!cfg.reward.trim() && (
            <p className="sm:col-span-3 text-sm font-medium text-amber-700 dark:text-amber-400">
              Escribe tu premio y guarda: hasta entonces tus clientes no ven la tarjeta.
            </p>
          )}
          <p className="sm:col-span-3 text-xs text-muted-foreground">
            ¿Te compraron en el mostrador? En Contactos puedes ponerle un sello a mano y entregarle su premio.
          </p>
        </div>
      )}

      {mutation.isError && <p className="text-sm text-red-600">{getApiError(mutation.error, 'No se pudo guardar')}</p>}
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
