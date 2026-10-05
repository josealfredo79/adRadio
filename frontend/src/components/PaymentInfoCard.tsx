import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CreditCard } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'

// Cómo te pagan los pedidos (users.payment_link / payment_transfer). Al
// confirmar un pedido con tarjeta o transferencia, el bot le manda al
// cliente tu link o tus datos. IaRadio no toca el dinero ni cobra comisión.
export default function PaymentInfoCard() {
  const { user, setUser } = useAuth()
  const qc = useQueryClient()
  const [link, setLink] = useState(user?.payment_link ?? '')
  const [transfer, setTransfer] = useState(user?.payment_transfer ?? '')
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api.patch('/me', { payment_link: link.trim(), payment_transfer: transfer.trim() }).then((r) => r.data),
    onSuccess: (updated) => {
      setUser?.(updated)
      qc.invalidateQueries({ queryKey: ['me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-3">
      <div className="flex items-center gap-2">
        <CreditCard className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">Cómo te pagan</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Cuando un cliente confirma un pedido con tarjeta o transferencia, el bot le manda estos datos. El dinero te llega
        directo a ti; tú marcas el pedido cuando lo recibas.
      </p>
      <label className="block text-sm font-medium text-foreground">
        Link de cobro (Mercado Pago, Stripe, Clip…)
        <input
          type="url"
          inputMode="url"
          value={link}
          maxLength={500}
          placeholder="https://mpago.la/…"
          onChange={(e) => setLink(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-normal focus:border-brand-500 focus:outline-none dark:border-gray-700 dark:bg-gray-950"
        />
      </label>
      <label className="block text-sm font-medium text-foreground">
        Datos para transferencia
        <textarea
          value={transfer}
          maxLength={500}
          rows={2}
          placeholder="Banco, CLABE y a nombre de quién"
          onChange={(e) => setTransfer(e.target.value)}
          className="mt-1 w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm font-normal focus:border-brand-500 focus:outline-none dark:border-gray-700 dark:bg-gray-950"
        />
      </label>
      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 dark:bg-brand-600 dark:hover:bg-brand-700"
      >
        {save.isPending ? 'Guardando…' : saved ? 'Guardado ✓' : 'Guardar'}
      </button>
      {save.isError && <p className="text-sm text-red-600">{getApiError(save.error, 'No se pudo guardar')}</p>}
    </div>
  )
}
