import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Banknote, Check, Gift, Loader2, Plus, Stamp, X } from 'lucide-react'

export interface LoyaltyCard {
  stamps: number
  required: number
  reward: string
  rewards_ready: number
  history: { label: string; at: string | null }[]
}

// Tarjeta de lealtad de un cliente desde Contactos: el dueño registra lo que
// le cobró ("Cobré $___", que también le pone el sello — docs/specs/2026-10-17-cobre.md),
// le pone un sello suelto o le entrega el premio. No aparece si el negocio no
// activó la tarjeta en Configuración (cobrar sigue en /app/cobrar).
export default function LoyaltyContactButton({
  contactId,
  contactName,
  className,
}: {
  contactId: string
  contactName: string
  className: string
}) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  if (!user?.loyalty_config?.enabled) return null
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Tarjeta de lealtad"
        aria-label={`Tarjeta de lealtad de ${contactName}`}
        className={className}
      >
        <Stamp className="h-4 w-4" />
      </button>
      {open && <LoyaltyModal contactId={contactId} contactName={contactName} onClose={() => setOpen(false)} />}
    </>
  )
}

function LoyaltyModal({ contactId, contactName, onClose }: { contactId: string; contactName: string; onClose: () => void }) {
  const qc = useQueryClient()
  const key = ['contact-loyalty', contactId]
  const { data, isLoading } = useQuery<{ card: LoyaltyCard | null }>({
    queryKey: key,
    queryFn: () => api.get(`/contacts/${contactId}/loyalty`).then((r) => r.data),
  })
  const action = useMutation({
    mutationFn: (what: 'stamp' | 'redeem') => api.post(`/contacts/${contactId}/loyalty/${what}`).then((r) => r.data),
    onSuccess: (out) => qc.setQueryData(key, out),
  })
  const card = data?.card
  const [amount, setAmount] = useState('')
  const charge = useMutation({
    mutationFn: () => api.post('/sales', { amount, contact_id: contactId }).then((r) => r.data as { amount: number }),
    onSuccess: () => {
      setAmount('')
      qc.invalidateQueries({ queryKey: key })
      qc.invalidateQueries({ queryKey: ['sales-today'] })
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl bg-card p-6 shadow-xl border border-border" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-foreground">Tarjeta de {contactName}</h3>
            {card && <p className="text-sm text-muted-foreground">Premio: {card.reward}</p>}
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : !card ? (
          <p className="mt-4 text-sm text-muted-foreground">Activa la tarjeta de lealtad en Configuración.</p>
        ) : (
          <>
            <div className="mt-5 grid grid-cols-5 gap-2">
              {Array.from({ length: card.required }, (_, i) => {
                const filled = card.rewards_ready > 0 || i < card.stamps
                return (
                  <div
                    key={i}
                    className={`aspect-square rounded-full flex items-center justify-center border-2 ${
                      filled ? 'bg-amber-400 border-amber-400 text-white' : 'border-dashed border-border text-muted-foreground'
                    }`}
                  >
                    {filled ? <Stamp className="h-4 w-4" /> : <span className="text-xs">{i + 1}</span>}
                  </div>
                )
              })}
            </div>
            <p className="mt-3 text-sm text-foreground">
              {card.rewards_ready > 0
                ? `🎁 Llenó su tarjeta${card.rewards_ready > 1 ? ` (${card.rewards_ready} premios)` : ''}: entrégale su premio.`
                : `${card.stamps} de ${card.required} sellos`}
            </p>

            <div className="mt-5 flex gap-2">
              <label className="flex min-w-0 flex-1 items-center rounded-lg border border-border bg-background px-2.5 focus-within:border-brand-500">
                <span className="text-sm text-muted-foreground">$</span>
                <input
                  value={amount}
                  onChange={(e) => { setAmount(e.target.value); charge.reset() }}
                  inputMode="decimal"
                  placeholder="¿Cuánto le cobraste?"
                  aria-label={`Monto cobrado a ${contactName}`}
                  className="w-full min-w-0 bg-transparent px-1.5 py-2 text-base text-foreground focus:outline-none"
                />
              </label>
              <button
                onClick={() => charge.mutate()}
                disabled={!amount.trim() || charge.isPending}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40"
              >
                {charge.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Banknote className="h-4 w-4" />} Cobré
              </button>
            </div>
            {charge.isSuccess && (
              <p className="mt-2 flex items-center gap-1 text-sm text-green-700">
                <Check className="h-4 w-4" /> Cobro de ${charge.data.amount} guardado, con su sello.
              </p>
            )}
            {charge.isError && <p className="mt-2 text-sm text-red-600">{getApiError(charge.error, 'No se pudo guardar el cobro')}</p>}
            {action.isError && <p className="mt-2 text-sm text-red-600">{getApiError(action.error, 'No se pudo guardar')}</p>}
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => action.mutate('stamp')}
                disabled={action.isPending}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50"
              >
                <Plus className="h-4 w-4" /> Poner sello
              </button>
              <button
                onClick={() => {
                  if (confirm(`¿Ya le entregaste "${card.reward}" a ${contactName}?`)) action.mutate('redeem')
                }}
                disabled={action.isPending || card.rewards_ready === 0}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-40"
              >
                <Gift className="h-4 w-4" /> Entregar premio
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
