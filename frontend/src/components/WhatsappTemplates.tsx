import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { Loader2, Plus, RefreshCw, X } from 'lucide-react'
import { useMetaTemplates, type MetaTemplate } from '@/lib/metaTemplates'

// Plantillas de WhatsApp en la cuenta (WABA) del negocio: el estado viene en
// vivo de Meta y se crean desde aquí sin entrar a WhatsApp Manager.

const STATUS: Record<string, { label: string; className: string }> = {
  APPROVED: { label: 'Aprobada', className: 'bg-green-100 text-green-800' },
  PENDING: { label: 'En revisión', className: 'bg-amber-100 text-amber-800' },
  REJECTED: { label: 'Rechazada', className: 'bg-red-100 text-red-800' },
  PAUSED: { label: 'Pausada', className: 'bg-amber-100 text-amber-800' },
  DISABLED: { label: 'Desactivada', className: 'bg-muted text-muted-foreground' },
}

const CATEGORY: Record<string, string> = { MARKETING: 'Marketing', UTILITY: 'Utilidad', AUTHENTICATION: 'Autenticación' }

const inputClass =
  'w-full rounded-lg border border-border bg-background text-foreground px-3 py-2 text-base sm:text-sm focus:border-brand-500 focus:outline-none'

/** Distinct {{n}} numbers in the body, sorted — one example input per variable. */
function variablesIn(body: string): number[] {
  const nums = Array.from(body.matchAll(/\{\{(\d+)\}\}/g), (m) => Number(m[1]))
  return Array.from(new Set(nums)).sort((a, b) => a - b)
}

export default function WhatsappTemplates() {
  const qc = useQueryClient()
  const { data: templates, isLoading, isFetching, error, refetch } = useMetaTemplates(true)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [category, setCategory] = useState<'UTILITY' | 'MARKETING'>('UTILITY')
  const [body, setBody] = useState('')
  const [examples, setExamples] = useState<Record<number, string>>({})
  const [footer, setFooter] = useState('')

  const variables = useMemo(() => variablesIn(body), [body])

  const reset = () => {
    setName('')
    setCategory('UTILITY')
    setBody('')
    setExamples({})
    setFooter('')
  }

  const createMutation = useMutation({
    mutationFn: () =>
      api
        .post('/me/whatsapp-templates/meta', {
          name,
          category,
          language: 'es_MX',
          body,
          examples: variables.map((n) => examples[n] ?? ''),
          footer: footer || null,
        })
        .then((r) => r.data as MetaTemplate),
    onSuccess: (created) => {
      qc.setQueryData<MetaTemplate[]>(['meta-templates'], (prev) => [created, ...(prev ?? [])])
      reset()
      setOpen(false)
    },
  })

  return (
    <div className="border-t border-border pt-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Tus plantillas de WhatsApp</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Actualizar estado"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-40"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
          {!open && (
            <button
              onClick={() => setOpen(true)}
              className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
            >
              <Plus className="h-4 w-4" />
              Nueva plantilla
            </button>
          )}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Las plantillas son los mensajes que puedes mandar fuera de la ventana de 24 h (recordatorios, avisos,
        promociones). Meta revisa cada una antes de aprobarla; normalmente tarda unos minutos.
      </p>

      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
          className="rounded-lg border border-border bg-muted/30 p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">Nueva plantilla</p>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                createMutation.reset()
              }}
              aria-label="Cerrar"
              className="rounded p-1 text-muted-foreground hover:bg-muted"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Nombre</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                placeholder="recordatorio_cita"
                required
                className={`${inputClass} font-mono`}
              />
              <p className="mt-1 text-[11px] text-muted-foreground">Minúsculas, números y guion bajo.</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Tipo</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as 'UTILITY' | 'MARKETING')}
                className={inputClass}
              >
                <option value="UTILITY">Utilidad (avisos, recordatorios, pedidos)</option>
                <option value="MARKETING">Marketing (promociones, ofertas)</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">Mensaje</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              maxLength={1024}
              required
              placeholder="Hola {{1}}, te recordamos tu cita del {{2}}. ¡Te esperamos!"
              className={inputClass}
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Usa {'{{1}}'}, {'{{2}}'}… para lo que cambia en cada envío (nombre, fecha). No empieces ni termines con
              una variable (aunque lleve punto).
            </p>
          </div>
          {variables.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-foreground">Ejemplos (Meta los usa para revisarla)</p>
              {variables.map((n) => (
                <div key={n} className="flex items-center gap-2">
                  <span className="w-10 shrink-0 font-mono text-xs text-muted-foreground">{`{{${n}}}`}</span>
                  <input
                    value={examples[n] ?? ''}
                    onChange={(e) => setExamples((prev) => ({ ...prev, [n]: e.target.value }))}
                    placeholder={n === 1 ? 'Ana' : 'lunes 10:00 am'}
                    required
                    className={inputClass}
                  />
                </div>
              ))}
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">Pie (opcional)</label>
            <input
              value={footer}
              onChange={(e) => setFooter(e.target.value)}
              maxLength={60}
              placeholder="Responde BAJA para no recibir más avisos"
              className={inputClass}
            />
          </div>
          {createMutation.isError && (
            <p className="text-sm text-red-600">
              {getApiError(createMutation.error, 'No se pudo enviar la plantilla a Meta')}
            </p>
          )}
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-40"
          >
            {createMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Enviar a revisión de Meta
          </button>
        </form>
      )}

      {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      {error && <p className="text-sm text-red-600">{getApiError(error, 'No se pudieron cargar las plantillas')}</p>}
      {templates && templates.length === 0 && !open && (
        <p className="text-sm text-muted-foreground">Aún no tienes plantillas. Crea la primera con “Nueva plantilla”.</p>
      )}
      {templates && templates.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {templates.map((t) => {
            const status = STATUS[t.status] ?? { label: t.status, className: 'bg-muted text-muted-foreground' }
            return (
              <li key={t.id || `${t.name}-${t.language}`} className="px-3 py-2.5 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm text-foreground break-all">{t.name}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${status.className}`}>
                    {status.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {CATEGORY[t.category] ?? t.category} · {t.language}
                  </span>
                </div>
                {t.body && <p className="text-xs text-muted-foreground whitespace-pre-line break-words">{t.body}</p>}
                {t.rejected_reason && (
                  <p className="text-xs text-red-600">Motivo de Meta: {t.rejected_reason}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
