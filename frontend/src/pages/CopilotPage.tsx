import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Sparkles, Send, AlertTriangle, Bot, ArrowUpRight, LayoutGrid, LayoutDashboard,
  Users, Megaphone, MessageSquare, ShoppingBag, Package, CalendarDays, Kanban,
  BookOpen, FlaskConical, UserCog, FileText, MessageCircle, BarChart3, CreditCard, Settings,
  Ticket, Rocket,
  type LucideIcon,
} from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import SEO from '@/components/SEO'
import { useCopilot, type CopilotAction, type PendingConfirmation, type CopilotFormTool } from '@/contexts/CopilotContext'

// Opciones reales para los selects de las mini-app cards — mismos endpoints
// que ya usan ContactsPage/CampaignsPage, no algo nuevo.
interface ContactOption {
  id: string
  name: string
  phone: string
}

interface CampaignOption {
  id: string
  name: string
  status: string
}

const LAUNCHABLE_STATUSES = new Set(['draft', 'scheduled', 'paused'])

// A la herramienta que ejecutó la acción le corresponde una vista tradicional
// del dashboard donde ver/seguir editando lo mismo — el chat es una puerta
// más a los mismos datos, nunca la única. No apuntamos al registro exacto
// (esas páginas no soportan abrir un id por URL todavía) sino a la sección
// correcta, que es lo que de verdad cierra el puente chat ↔ dashboard.
const TOOL_ROUTES: Record<string, { path: string; label: string }> = {
  list_contacts: { path: '/app/contacts', label: 'Ver en Contactos' },
  create_contact: { path: '/app/contacts', label: 'Ver en Contactos' },
  list_campaigns: { path: '/app/campaigns', label: 'Ver en Campañas' },
  get_campaign_stats: { path: '/app/campaigns', label: 'Ver en Campañas' },
  launch_campaign: { path: '/app/campaigns', label: 'Ver en Campañas' },
  create_coupon: { path: '/app/contacts', label: 'Ver en Contactos' },
  schedule_appointment: { path: '/app/appointments', label: 'Ver en Citas' },
}

// Un módulo por cada sección real del sidebar (mismo set que Layout.tsx) —
// "sobre todo el sistema", no solo las 3 que el Copiloto ya opera. Los que
// traen `prompt` SÍ tienen herramientas reales detrás (ver TOOLS en el
// backend) y tocarlos dispara una operación de verdad dentro del chat; los
// que no lo traen son honestos sobre no estar operables todavía — abren la
// vista tradicional en vez de fingir una acción que no existe.
interface ModuleEntry {
  path: string
  icon: LucideIcon
  label: string
  prompt?: string
}

const MODULES: ModuleEntry[] = [
  { path: '/app/contacts', icon: Users, label: 'Contactos', prompt: 'Muéstrame mis contactos' },
  { path: '/app/campaigns', icon: Megaphone, label: 'Campañas', prompt: 'Muéstrame mis campañas' },
  { path: '/app/appointments', icon: CalendarDays, label: 'Citas', prompt: 'Muéstrame mis próximas citas' },
  { path: '/app/automations', icon: Bot, label: 'Automatizaciones' },
  { path: '/app/inbox', icon: MessageSquare, label: 'Inbox' },
  { path: '/app/orders', icon: ShoppingBag, label: 'Pedidos' },
  { path: '/app/products', icon: Package, label: 'Catálogo' },
  { path: '/app/pipeline', icon: Kanban, label: 'Pipeline' },
  { path: '/app/knowledge-base', icon: BookOpen, label: 'Base de conocimiento' },
  { path: '/app/lab', icon: FlaskConical, label: 'Laboratorio' },
  { path: '/app/team', icon: UserCog, label: 'Equipo' },
  { path: '/app/templates', icon: FileText, label: 'Plantillas' },
  { path: '/app/widget', icon: MessageCircle, label: 'Widget de chat' },
  { path: '/app/analytics', icon: BarChart3, label: 'Analytics' },
  { path: '/app/plans', icon: CreditCard, label: 'Planes' },
  { path: '/app/settings', icon: Settings, label: 'Configuración' },
]

function ModuleGrid({ onSelect, disabled }: { onSelect: (m: ModuleEntry) => void; disabled?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
      {MODULES.map((m) => (
        <button
          key={m.path}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(m)}
          className="flex flex-col items-start gap-2 rounded-xl border border-gray-200 bg-white p-3 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-700 dark:hover:bg-brand-500/10"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-800">
            <m.icon className="h-4 w-4 text-gray-600 dark:text-gray-300" />
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{m.label}</p>
            <p className="text-[11px] text-gray-400 dark:text-gray-500">{m.prompt ? 'Operar aquí' : 'Abrir módulo'}</p>
          </div>
        </button>
      ))}
    </div>
  )
}

interface CopilotChatResponse {
  reply: string
  actions: CopilotAction[]
  pending_confirmation: PendingConfirmation | null
}

interface HistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

function humanizeLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  return String(value)
}

// Renders a single action's `data` payload as label/value rows or a compact
// list — never raw JSON. Handles the common shapes (a flat object, a list of
// objects/primitives) with one level of nesting; anything deeper falls back
// to a short stringified summary so we never dump raw JSON on screen.
function ActionData({ data, depth = 0 }: { data: unknown; depth?: number }) {
  if (data === null || data === undefined) return null

  if (Array.isArray(data)) {
    if (!data.length) return null
    return (
      <ul className="space-y-1">
        {data.slice(0, 8).map((item, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-400">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-gray-400 dark:bg-gray-600" />
            {typeof item === 'object' && item !== null ? (
              depth < 1 ? <ActionData data={item} depth={depth + 1} /> : <span>{JSON.stringify(item)}</span>
            ) : (
              <span>{formatPrimitive(item)}</span>
            )}
          </li>
        ))}
        {data.length > 8 && (
          <li className="text-xs text-gray-400 dark:text-gray-500">+{data.length - 8} más</li>
        )}
      </ul>
    )
  }

  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, unknown>)
    if (!entries.length) return null
    return (
      <div className="space-y-1">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-baseline justify-between gap-3 text-xs">
            <span className="text-gray-400 dark:text-gray-500">{humanizeLabel(key)}</span>
            {Array.isArray(value) || (typeof value === 'object' && value !== null) ? (
              depth < 1 ? (
                <div className="flex-1 text-right">
                  <ActionData data={value} depth={depth + 1} />
                </div>
              ) : (
                <span className="font-medium text-gray-700 dark:text-gray-300 text-right">{JSON.stringify(value)}</span>
              )
            ) : (
              <span className="font-medium text-gray-700 dark:text-gray-300 text-right">{formatPrimitive(value)}</span>
            )}
          </div>
        ))}
      </div>
    )
  }

  return <span className="text-xs text-gray-600 dark:text-gray-400">{formatPrimitive(data)}</span>
}

function ActionsBlock({ actions }: { actions: CopilotAction[] }) {
  if (!actions?.length) return null
  return (
    <div className="mt-2 space-y-2">
      {actions.map((action, i) => {
        const hasError = !!(action.data && typeof action.data === 'object' && 'error' in (action.data as Record<string, unknown>))
        const route = !hasError ? TOOL_ROUTES[action.tool] : undefined
        return (
          <div
            key={i}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/60"
          >
            <p className="text-xs font-semibold text-gray-600 dark:text-gray-300">{action.summary}</p>
            <div className="mt-1.5">
              <ActionData data={action.data} />
            </div>
            {route && (
              <Link
                to={route.path}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                {route.label}
                <ArrowUpRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        )
      })}
    </div>
  )
}

const fieldClass =
  'w-full rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs text-gray-800 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200'

function FormCard({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <div className="w-full max-w-sm space-y-2.5 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      {children}
    </div>
  )
}

// Mini-apps: la parte que faltaba del patrón "chat-first con tarjetas
// interactivas" — un formulario real (selector de contacto, fecha, número)
// en vez de depender de que el texto libre se interprete bien. El submit va
// directo al endpoint de preview (sin pasar por Claude), y de ahí para
// adelante es el mismo flujo de confirmación de siempre.
function AppointmentForm({
  contacts, onSubmit, disabled,
}: { contacts: ContactOption[]; onSubmit: (args: Record<string, unknown>) => void; disabled?: boolean }) {
  const [contactId, setContactId] = useState('')
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [service, setService] = useState('')
  const canSubmit = !!contactId && !!date && !!time

  return (
    <FormCard title="Agendar cita" icon={CalendarDays}>
      <select value={contactId} onChange={(e) => setContactId(e.target.value)} disabled={disabled} className={fieldClass}>
        <option value="">Selecciona un contacto…</option>
        {contacts.map((c) => (
          <option key={c.id} value={c.id}>{c.name} · {c.phone}</option>
        ))}
      </select>
      <div className="flex gap-2">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} disabled={disabled} className={fieldClass} />
        <input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={disabled} className={fieldClass} />
      </div>
      <input
        type="text"
        placeholder="Servicio o motivo (opcional)"
        value={service}
        onChange={(e) => setService(e.target.value)}
        disabled={disabled}
        className={fieldClass}
      />
      <button
        type="button"
        disabled={disabled || !canSubmit}
        onClick={() => onSubmit({ contact_id: contactId, datetime_iso: `${date}T${time}:00`, service: service || undefined })}
        className="w-full rounded-lg bg-brand-500 py-1.5 text-xs font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Ver confirmación
      </button>
    </FormCard>
  )
}

function CouponForm({
  contacts, onSubmit, disabled,
}: { contacts: ContactOption[]; onSubmit: (args: Record<string, unknown>) => void; disabled?: boolean }) {
  const [name, setName] = useState('')
  const [discount, setDiscount] = useState('')
  const [target, setTarget] = useState<'all' | 'segment' | 'contact'>('all')
  const [contactId, setContactId] = useState('')
  const [segmentTag, setSegmentTag] = useState('')

  const discountNum = Number(discount)
  const canSubmit =
    !!name.trim() &&
    discount !== '' &&
    discountNum > 0 &&
    discountNum <= 100 &&
    (target !== 'contact' || !!contactId) &&
    (target !== 'segment' || !!segmentTag.trim())

  return (
    <FormCard title="Crear cupón" icon={Ticket}>
      <input type="text" placeholder="Nombre del cupón" value={name} onChange={(e) => setName(e.target.value)} disabled={disabled} className={fieldClass} />
      <input
        type="number" min={1} max={100} placeholder="% de descuento"
        value={discount} onChange={(e) => setDiscount(e.target.value)} disabled={disabled} className={fieldClass}
      />
      <select value={target} onChange={(e) => setTarget(e.target.value as typeof target)} disabled={disabled} className={fieldClass}>
        <option value="all">Todos mis contactos activos</option>
        <option value="segment">Contactos con una etiqueta</option>
        <option value="contact">Un solo contacto</option>
      </select>
      {target === 'contact' && (
        <select value={contactId} onChange={(e) => setContactId(e.target.value)} disabled={disabled} className={fieldClass}>
          <option value="">Selecciona un contacto…</option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>{c.name} · {c.phone}</option>
          ))}
        </select>
      )}
      {target === 'segment' && (
        <input
          type="text" placeholder="Etiqueta, ej. vip"
          value={segmentTag} onChange={(e) => setSegmentTag(e.target.value)} disabled={disabled} className={fieldClass}
        />
      )}
      <button
        type="button"
        disabled={disabled || !canSubmit}
        onClick={() =>
          onSubmit({
            name: name.trim(),
            discount_percent: discountNum,
            target,
            contact_id: target === 'contact' ? contactId : undefined,
            segment_tag: target === 'segment' ? segmentTag.trim() : undefined,
          })
        }
        className="w-full rounded-lg bg-brand-500 py-1.5 text-xs font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Ver confirmación
      </button>
    </FormCard>
  )
}

function LaunchCampaignForm({
  campaigns, onSubmit, disabled,
}: { campaigns: CampaignOption[]; onSubmit: (args: Record<string, unknown>) => void; disabled?: boolean }) {
  const [campaignId, setCampaignId] = useState('')
  const launchable = campaigns.filter((c) => LAUNCHABLE_STATUSES.has(c.status))

  return (
    <FormCard title="Lanzar campaña" icon={Rocket}>
      {launchable.length ? (
        <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} disabled={disabled} className={fieldClass}>
          <option value="">Selecciona una campaña…</option>
          {launchable.map((c) => (
            <option key={c.id} value={c.id}>{c.name} ({c.status})</option>
          ))}
        </select>
      ) : (
        <p className="text-xs text-gray-400 dark:text-gray-500">No tienes campañas listas para lanzar.</p>
      )}
      <button
        type="button"
        disabled={disabled || !campaignId}
        onClick={() => onSubmit({ campaign_id: campaignId })}
        className="w-full rounded-lg bg-brand-500 py-1.5 text-xs font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Ver confirmación
      </button>
    </FormCard>
  )
}

const QUICK_ACTIONS: { tool: CopilotFormTool; label: string; icon: LucideIcon }[] = [
  { tool: 'schedule_appointment', label: 'Agendar cita', icon: CalendarDays },
  { tool: 'create_coupon', label: 'Crear cupón', icon: Ticket },
  { tool: 'launch_campaign', label: 'Lanzar campaña', icon: Rocket },
]

export default function CopilotPage() {
  const { messages, setMessages, pendingConfirmation, setPendingConfirmation } = useCopilot()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const chatMutation = useMutation({
    // El endpoint puede hacer varias idas y vueltas con Claude (tool-calling
    // en cadena) antes de responder — el timeout global de 10s del cliente
    // axios se queda corto y aborta antes de que el backend termine.
    mutationFn: (payload: { message: string; history: HistoryTurn[] }) =>
      api.post<CopilotChatResponse>('/copilot/chat', payload, { timeout: 45000 }).then((r) => r.data),
  })

  const confirmMutation = useMutation({
    mutationFn: (payload: { confirmation_id: string; approve: boolean }) =>
      api.post<CopilotChatResponse>('/copilot/confirm', payload).then((r) => r.data),
  })

  // Datos reales para los selects de las mini-app cards — mismos endpoints
  // que ContactsPage/CampaignsPage, no una fuente nueva.
  const contactsQuery = useQuery({
    queryKey: ['copilot-contacts-options'],
    queryFn: () =>
      api.get('/contacts', { params: { page_size: 100, status: 'active' } }).then((r) => r.data.items as ContactOption[]),
    staleTime: 60_000,
  })
  const campaignsQuery = useQuery({
    queryKey: ['copilot-campaigns-options'],
    queryFn: () => api.get('/campaigns', { params: { page_size: 100 } }).then((r) => r.data.items as CampaignOption[]),
    staleTime: 60_000,
  })

  const previewMutation = useMutation({
    mutationFn: (payload: { tool: CopilotFormTool; args: Record<string, unknown> }) =>
      api.post<CopilotChatResponse>(`/copilot/tools/${payload.tool}/preview`, { args: payload.args }).then((r) => r.data),
  })

  const isBusy = chatMutation.isPending || confirmMutation.isPending || previewMutation.isPending
  const inputDisabled = isBusy || !!pendingConfirmation

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pendingConfirmation, chatMutation.isPending])

  const appendAssistantReply = (data: CopilotChatResponse) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'assistant', content: data.reply, actions: data.actions },
    ])
    setPendingConfirmation(data.pending_confirmation ?? null)
  }

  const handleSend = (text?: string) => {
    const trimmed = (text ?? input).trim()
    if (!trimmed || isBusy || pendingConfirmation) return

    const history: HistoryTurn[] = messages.map(({ role, content }) => ({ role, content }))
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: trimmed }])
    setInput('')

    chatMutation.mutate(
      { message: trimmed, history },
      {
        onSuccess: appendAssistantReply,
        onError: (err) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: getApiError(err, 'No se pudo procesar tu mensaje. Intenta de nuevo.'),
              isError: true,
            },
          ])
        },
      }
    )
  }

  const handleConfirm = (approve: boolean) => {
    if (!pendingConfirmation || confirmMutation.isPending) return
    confirmMutation.mutate(
      { confirmation_id: pendingConfirmation.confirmation_id, approve },
      {
        onSuccess: appendAssistantReply,
        onError: (err) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: getApiError(err, 'No se pudo procesar la confirmación. Intenta de nuevo.'),
              isError: true,
            },
          ])
          setPendingConfirmation(null)
        },
      }
    )
  }

  const handleShowModules = () => {
    if (isBusy || pendingConfirmation) return
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'assistant', content: 'Elige un módulo:', moduleGrid: true },
    ])
  }

  const handleModuleSelect = (module: ModuleEntry) => {
    if (isBusy || pendingConfirmation) return
    if (module.prompt) {
      handleSend(module.prompt)
      return
    }
    // Sin herramienta real detrás — nunca fingimos operarlo desde el chat,
    // solo abrimos la vista tradicional donde sí se puede.
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `El Copiloto todavía no opera "${module.label}" directamente — ábrelo aquí:`,
        moduleLink: { path: module.path, label: `Ver en ${module.label}` },
      },
    ])
  }

  const openForm = (tool: CopilotFormTool) => {
    if (isBusy || pendingConfirmation) return
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: '', formTool: tool }])
  }

  const handleFormSubmit = (tool: CopilotFormTool, args: Record<string, unknown>) => {
    previewMutation.mutate(
      { tool, args },
      {
        onSuccess: appendAssistantReply,
        onError: (err) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: getApiError(err, 'No se pudo preparar la acción. Intenta de nuevo.'),
              isError: true,
            },
          ])
        },
      }
    )
  }

  return (
    <>
      <SEO title="Copiloto" description="Opera tu CRM de AdRadio conversando en lenguaje natural." noIndex />
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">Copiloto</h1>
              <p className="text-xs text-muted-foreground">Pídele en lenguaje natural que opere tu CRM por ti</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleShowModules}
              disabled={isBusy || !!pendingConfirmation}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Módulos
            </button>
            <Link
              to="/app/dashboard"
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              <LayoutDashboard className="h-3.5 w-3.5" />
              Salir
            </Link>
          </div>
        </div>

        <div className="flex h-[75vh] flex-col rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950">
          {/* Message thread */}
          <div className="flex-1 space-y-3 overflow-y-auto px-5 py-5">
            {!messages.length ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 dark:bg-brand-500/10">
                  <Bot className="h-6 w-6 text-brand-500" />
                </div>
                <div className="max-w-md space-y-1">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Soy tu Copiloto: elige un módulo abajo, o escribe lo que necesitas — puedo ver estadísticas de
                    campaña, agregar contactos, lanzar campañas, crear cupones o agendar citas por ti.
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    Te confirmo antes de hacer cualquier cambio.
                  </p>
                </div>
                <div className="w-full max-w-2xl">
                  <ModuleGrid onSelect={handleModuleSelect} disabled={isBusy || !!pendingConfirmation} />
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div key={msg.id} className={cn('flex', msg.role === 'assistant' ? 'justify-start' : 'justify-end')}>
                  <div className={msg.moduleGrid || msg.formTool ? 'w-full max-w-2xl' : 'max-w-[75%]'}>
                    {!msg.moduleGrid && !msg.formTool && (
                      <div
                        className={cn(
                          'rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap',
                          msg.role === 'assistant'
                            ? msg.isError
                              ? 'rounded-tl-sm bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                              : 'rounded-tl-sm bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
                            : 'rounded-tr-sm bg-brand-500 text-white'
                        )}
                      >
                        {msg.content}
                      </div>
                    )}
                    {msg.role === 'assistant' && !msg.isError && <ActionsBlock actions={msg.actions ?? []} />}
                    {msg.moduleGrid && (
                      <div className="mt-2">
                        <ModuleGrid onSelect={handleModuleSelect} disabled={isBusy || !!pendingConfirmation} />
                      </div>
                    )}
                    {msg.formTool === 'schedule_appointment' && (
                      <AppointmentForm
                        contacts={contactsQuery.data ?? []}
                        disabled={isBusy || !!pendingConfirmation}
                        onSubmit={(args) => handleFormSubmit('schedule_appointment', args)}
                      />
                    )}
                    {msg.formTool === 'create_coupon' && (
                      <CouponForm
                        contacts={contactsQuery.data ?? []}
                        disabled={isBusy || !!pendingConfirmation}
                        onSubmit={(args) => handleFormSubmit('create_coupon', args)}
                      />
                    )}
                    {msg.formTool === 'launch_campaign' && (
                      <LaunchCampaignForm
                        campaigns={campaignsQuery.data ?? []}
                        disabled={isBusy || !!pendingConfirmation}
                        onSubmit={(args) => handleFormSubmit('launch_campaign', args)}
                      />
                    )}
                    {msg.moduleLink && (
                      <Link
                        to={msg.moduleLink.path}
                        className="mt-2 inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-brand-600 transition-colors hover:bg-gray-100 dark:border-gray-800 dark:bg-gray-900 dark:text-brand-400 dark:hover:bg-gray-800"
                      >
                        {msg.moduleLink.label}
                        <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    )}
                  </div>
                </div>
              ))
            )}

            {chatMutation.isPending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-gray-100 px-4 py-3 dark:bg-gray-800">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Pending confirmation card — visually separated from chat bubbles */}
          {pendingConfirmation && (
            <div className="mx-4 mb-3 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-700/60 dark:bg-amber-900/20">
              <div className="flex items-center gap-2 text-sm font-semibold text-amber-800 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Confirmación requerida
              </div>
              <p className="mt-1.5 text-sm text-amber-900 dark:text-amber-200">{pendingConfirmation.summary}</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => handleConfirm(true)}
                  disabled={confirmMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {confirmMutation.isPending && (
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  )}
                  Confirmar
                </button>
                <button
                  onClick={() => handleConfirm(false)}
                  disabled={confirmMutation.isPending}
                  className="rounded-lg border border-amber-300 bg-white px-4 py-1.5 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700 dark:bg-transparent dark:text-amber-300 dark:hover:bg-amber-900/40"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}

          {/* Acciones rápidas — las mini-apps: un formulario real en vez de
              depender de que el texto libre se interprete bien */}
          <div className="flex flex-wrap gap-1.5 border-t border-gray-100 px-4 py-2 dark:border-gray-800/60">
            {QUICK_ACTIONS.map((a) => (
              <button
                key={a.tool}
                type="button"
                onClick={() => openForm(a.tool)}
                disabled={isBusy || !!pendingConfirmation}
                className="flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                <a.icon className="h-3 w-3" />
                {a.label}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                disabled={inputDisabled}
                placeholder={
                  pendingConfirmation
                    ? 'Resuelve la confirmación pendiente para continuar…'
                    : 'Escribe lo que necesitas… (Enter para enviar, Shift+Enter para nueva línea)'
                }
                rows={2}
                className="flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || inputDisabled}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {chatMutation.isPending ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
