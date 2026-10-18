import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Search, Stamp, Undo2, UserPlus, UserX, X } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'
import SEO from '@/components/SEO'

// "Cobré $___" (docs/specs/2026-10-17-cobre.md): el dueño registra lo que
// cobró en el mostrador en segundos. Con cliente, le pone su sello; también
// cliente nuevo o venta sin cliente. Es lo que deja medir si IaRadio le trae
// dinero al negocio.

interface Customer {
  id: string
  name: string
  phone_last4: string
}

interface Today {
  count: number
  total: number
}

interface SaleOut {
  id: string
  amount: number
  customer: Customer | null
  stamped: boolean
  today: Today
}

type Who = { kind: 'customer'; customer: Customer } | { kind: 'new' } | { kind: 'none' } | null

const mxn = (n: number) => formatCurrency(n, 'MXN')

export default function CashierPage() {
  const qc = useQueryClient()
  const [amount, setAmount] = useState('')
  const [who, setWho] = useState<Who>(null)
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [newName, setNewName] = useState('')
  const [newPhone, setNewPhone] = useState('')
  const [last, setLast] = useState<SaleOut | null>(null)
  const amountRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250)
    return () => clearTimeout(t)
  }, [query])

  const { data: today } = useQuery<Today>({
    queryKey: ['sales-today'],
    queryFn: () => api.get('/sales/today').then((r) => r.data),
  })
  // Atajos: los montos que más cobra y los últimos clientes (docs/specs/2026-10-17-cobrar-con-copiloto.md).
  const { data: shortcuts } = useQuery<{ amounts: number[]; recent: Customer[] }>({
    queryKey: ['sales-shortcuts'],
    queryFn: () => api.get('/sales/shortcuts').then((r) => r.data),
  })
  const { data: results, isFetching: searching } = useQuery<Customer[]>({
    queryKey: ['sales-customers', debounced],
    queryFn: () => api.get('/sales/customers', { params: { q: debounced } }).then((r) => r.data),
    enabled: debounced.length >= 2 && who === null,
  })

  const reset = () => {
    setAmount('')
    setWho(null)
    setQuery('')
    setDebounced('')
    setNewName('')
    setNewPhone('')
    amountRef.current?.focus()
  }

  const charge = useMutation({
    mutationFn: () =>
      api
        .post('/sales', {
          amount,
          ...(who?.kind === 'customer' ? { contact_id: who.customer.id } : {}),
          ...(who?.kind === 'new' ? { new_customer: { name: newName, phone: newPhone } } : {}),
        })
        .then((r) => r.data as SaleOut),
    onSuccess: (sale) => {
      qc.setQueryData(['sales-today'], sale.today)
      qc.invalidateQueries({ queryKey: ['sales-shortcuts'] })
      setLast(sale)
      reset()
    },
  })

  const undo = useMutation({
    mutationFn: (id: string) => api.delete(`/sales/${id}`).then((r) => r.data as { today: Today }),
    onSuccess: (out) => {
      qc.setQueryData(['sales-today'], out.today)
      qc.invalidateQueries({ queryKey: ['sales-shortcuts'] })
      setLast(null)
    },
  })

  const ready =
    amount.trim() !== '' &&
    (who?.kind === 'customer' || who?.kind === 'none' || (who?.kind === 'new' && newName.trim() && newPhone.trim()))

  const pill =
    'flex items-center justify-center gap-1.5 rounded-xl border border-border px-3 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors'

  return (
    <div className="mx-auto max-w-md space-y-5">
      <SEO title="Cobrar" />
      <div>
        <h1 className="text-2xl font-bold text-foreground">Cobrar</h1>
        <p className="mt-1 text-sm text-muted-foreground" aria-live="polite">
          Hoy llevas <strong className="text-foreground">{mxn(today?.total ?? 0)}</strong> en{' '}
          {today?.count ?? 0} {today?.count === 1 ? 'venta' : 'ventas'}
        </p>
      </div>

      {last && (
        <div className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 dark:border-green-900 dark:bg-green-950/30">
          <Check className="h-5 w-5 shrink-0 text-green-600" />
          <p className="min-w-0 flex-1 text-sm text-foreground">
            Cobraste <strong>{mxn(last.amount)}</strong>
            {last.customer ? ` a ${last.customer.name}` : ''}
            {last.stamped && (
              <span className="ml-1 inline-flex items-center gap-0.5 text-amber-600">
                · <Stamp className="h-3.5 w-3.5" /> +1 sello
              </span>
            )}
          </p>
          <button
            type="button"
            onClick={() => undo.mutate(last.id)}
            disabled={undo.isPending}
            className="flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <Undo2 className="h-3.5 w-3.5" /> Deshacer
          </button>
        </div>
      )}
      {undo.isError && <p className="text-sm text-red-600">{getApiError(undo.error, 'No se pudo deshacer')}</p>}

      <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-5">
        <label className="block">
          <span className="text-sm font-medium text-foreground">¿Cuánto cobraste?</span>
          <div className="mt-1.5 flex items-center rounded-xl border border-border bg-background px-4 focus-within:border-brand-500">
            <span className="text-2xl text-muted-foreground">$</span>
            <input
              ref={amountRef}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              placeholder="0"
              aria-label="Monto cobrado"
              autoFocus
              className="w-full bg-transparent px-2 py-3 text-3xl font-semibold text-foreground focus:outline-none"
            />
          </div>
        </label>
        {shortcuts && shortcuts.amounts.length > 0 && (
          <div className="-mt-3 grid grid-cols-4 gap-2">
            {shortcuts.amounts.map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setAmount(String(a))}
                className={`rounded-lg border px-2 py-2 text-sm font-semibold tabular-nums transition-colors ${
                  amount === String(a) ? 'border-brand-500 bg-brand-500/10 text-foreground' : 'border-border text-foreground hover:bg-muted'
                }`}
              >
                ${a % 1 === 0 ? a : a.toFixed(2)}
              </button>
            ))}
          </div>
        )}

        <div>
          <span className="text-sm font-medium text-foreground">¿A quién?</span>
          {who === null && (
            <div className="mt-1.5 space-y-2">
              <div className="flex items-center rounded-xl border border-border bg-background px-3 focus-within:border-brand-500">
                <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Nombre o últimos 4 dígitos"
                  aria-label="Buscar cliente"
                  className="w-full bg-transparent px-2 py-3 text-base text-foreground focus:outline-none"
                />
                {searching && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />}
              </div>
              {debounced.length < 2 && (shortcuts?.recent.length ?? 0) > 0 && (
                <div>
                  <p className="mb-1.5 text-xs text-muted-foreground">Recientes</p>
                  <div className="flex flex-wrap gap-2">
                    {shortcuts!.recent.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => setWho({ kind: 'customer', customer: c })}
                        className="max-w-full truncate rounded-full border border-border px-3 py-1.5 text-sm text-foreground hover:bg-muted"
                      >
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {debounced.length >= 2 && results && (
                <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border">
                  {results.length === 0 && (
                    <li className="px-4 py-3 text-sm text-muted-foreground">No encontré a nadie con “{debounced}”.</li>
                  )}
                  {results.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => setWho({ kind: 'customer', customer: c })}
                        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted"
                      >
                        <span className="truncate text-sm font-medium text-foreground">{c.name}</span>
                        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">…{c.phone_last4}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => setWho({ kind: 'new' })} className={pill}>
                  <UserPlus className="h-4 w-4" /> Cliente nuevo
                </button>
                <button type="button" onClick={() => setWho({ kind: 'none' })} className={pill}>
                  <UserX className="h-4 w-4" /> Sin cliente
                </button>
              </div>
            </div>
          )}

          {who !== null && (
            <div className="mt-1.5 rounded-xl border border-border bg-muted/30 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-sm font-medium text-foreground">
                  {who.kind === 'customer' && `${who.customer.name} · …${who.customer.phone_last4}`}
                  {who.kind === 'new' && 'Cliente nuevo'}
                  {who.kind === 'none' && 'Venta sin cliente (no junta sello)'}
                </span>
                <button
                  type="button"
                  onClick={() => setWho(null)}
                  aria-label="Cambiar cliente"
                  className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              {who.kind === 'new' && (
                <div className="mt-3 space-y-2">
                  <input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Nombre"
                    aria-label="Nombre del cliente"
                    autoComplete="off"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base text-foreground focus:border-brand-500 focus:outline-none"
                  />
                  <input
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value)}
                    placeholder="WhatsApp a 10 dígitos"
                    aria-label="Teléfono del cliente"
                    type="tel"
                    inputMode="tel"
                    autoComplete="off"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base text-foreground focus:border-brand-500 focus:outline-none"
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {charge.isError && (
          <p className="text-sm text-red-600">{getApiError(charge.error, 'No se pudo guardar el cobro')}</p>
        )}
        <button
          type="button"
          onClick={() => charge.mutate()}
          disabled={!ready || charge.isPending}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 px-4 py-4 text-lg font-semibold text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {charge.isPending && <Loader2 className="h-5 w-5 animate-spin" />}
          Cobré{amount.trim() ? ` $${amount.trim().replace(/^\$/, '')}` : ''}
        </button>
      </div>
    </div>
  )
}
