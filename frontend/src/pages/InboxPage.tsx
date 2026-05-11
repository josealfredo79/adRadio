import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { MessageSquare, User, Clock, Flame, Thermometer, Snowflake, CheckCircle, AlertCircle, X, Image, Volume2, FileText, Search, Send } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'

// Detect and render WhatsApp media stored as [media:type]url
function MediaMessage({ content }: { content: string }) {
  const match = content.match(/^\[media:([^\]]+)\](.+)$/)
  if (!match) return <span>{content}</span>

  const [, mimeType, url] = match
  if (mimeType.startsWith('image/')) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer">
        <img src={url} alt="Imagen adjunta" className="max-w-[220px] rounded-lg border border-gray-200" />
      </a>
    )
  }
  if (mimeType.startsWith('audio/') || url.endsWith('.ogg') || url.endsWith('.mp3')) {
    return <audio controls src={url} className="max-w-[260px]" />
  }
  if (mimeType.startsWith('video/')) {
    return <video controls src={url} className="max-w-[260px] rounded-lg" />
  }
  // Fallback: document link
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className="flex items-center gap-1.5 text-brand-600 underline text-xs">
      <FileText className="h-4 w-4" />
      Archivo adjunto ({mimeType})
    </a>
  )
}

interface ConvContact {
  id: string | null
  name: string
  phone: string | null
  engagement_score: number
}

interface ConvSummary {
  id: string
  status: 'active' | 'escalated' | 'closed'
  lead_score: 'hot' | 'warm' | 'cold' | null
  tags: string[]
  last_activity: string
  message_count: number
  last_message: { role: string; content: string } | null
  contact: ConvContact
}

interface ConvDetail extends ConvSummary {
  messages: { role: string; content: string }[]
}

const LEAD_ICON = {
  hot: { icon: Flame, color: 'text-red-500', label: 'Caliente' },
  warm: { icon: Thermometer, color: 'text-orange-400', label: 'Tibio' },
  cold: { icon: Snowflake, color: 'text-blue-400', label: 'Frío' },
}

const STATUS_STYLE = {
  active: 'bg-green-100 text-green-700',
  escalated: 'bg-orange-100 text-orange-700',
  closed: 'bg-gray-100 text-gray-500',
}

const STATUS_LABEL = {
  active: 'Activa',
  escalated: 'Escalada',
  closed: 'Cerrada',
}

export default function InboxPage() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [search, setSearch] = useState('')
  const [replyText, setReplyText] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const { data: conversations, isLoading } = useQuery<ConvSummary[]>({
    queryKey: ['conversations', statusFilter],
    queryFn: () =>
      api.get('/conversations', { params: { status: statusFilter || undefined, page_size: 50 } }).then((r) => r.data),
    refetchInterval: 30_000,
  })

  const { data: detail } = useQuery<ConvDetail>({
    queryKey: ['conversation', selectedId],
    queryFn: () => api.get(`/conversations/${selectedId}`).then((r) => r.data),
    enabled: !!selectedId,
    refetchInterval: selectedId ? 10_000 : false,
  })

  const filtered = conversations?.filter((c) => {
    if (!search.trim()) return true
    const q = search.toLowerCase()
    return c.contact.name.toLowerCase().includes(q) || (c.contact.phone ?? '').toLowerCase().includes(q)
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/conversations/${id}/status`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: ['conversation', selectedId] })
    },
  })

  const replyMutation = useMutation({
    mutationFn: (text: string) =>
      api.post(`/conversations/${selectedId}/reply`, { text }),
    onSuccess: () => {
      setReplyText('')
      qc.invalidateQueries({ queryKey: ['conversation', selectedId] })
      qc.invalidateQueries({ queryKey: ['conversations', statusFilter] })
    },
  })

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [detail?.messages])

  const handleSend = () => {
    const text = replyText.trim()
    if (!text || replyMutation.isPending) return
    replyMutation.mutate(text)
  }

  return (
    <div className="flex h-full gap-0 -m-6 overflow-hidden">
      {/* Left panel — conversation list */}
      <div className="flex w-80 flex-shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-4 py-4">
          <h1 className="text-lg font-bold text-gray-900">Inbox</h1>
          <div className="mt-3 relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar por nombre o teléfono…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-gray-50 py-1.5 pl-8 pr-3 text-xs text-gray-700 placeholder-gray-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
            />
          </div>
          <div className="mt-2 flex gap-1.5">
            {(['active', 'escalated', 'closed', ''] as const).map((s) => (
              <button
                key={s}
                onClick={() => { setStatusFilter(s); setSelectedId(null) }}
                className={cn(
                  'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                  statusFilter === s
                    ? 'bg-brand-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                {s === '' ? 'Todas' : STATUS_LABEL[s as keyof typeof STATUS_LABEL]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 rounded-lg bg-gray-100 animate-pulse" />
              ))}
            </div>
          ) : !filtered?.length ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <MessageSquare className="mb-3 h-10 w-10" />
              <p className="text-sm">{search ? 'Sin resultados' : 'Sin conversaciones'}</p>
            </div>
          ) : (
            filtered.map((conv) => {
              const lead = conv.lead_score ? LEAD_ICON[conv.lead_score] : null
              const LeadIcon = lead?.icon
              return (
                <button
                  key={conv.id}
                  onClick={() => setSelectedId(conv.id)}
                  className={cn(
                    'w-full border-b border-gray-50 px-4 py-3 text-left transition-colors hover:bg-gray-50',
                    selectedId === conv.id && 'bg-brand-50 border-l-2 border-l-brand-500'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 truncate text-sm font-medium text-gray-900">
                      <User className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
                      {conv.contact.name}
                    </span>
                    {LeadIcon && (
                      <LeadIcon className={cn('h-3.5 w-3.5 flex-shrink-0', lead?.color)} />
                    )}
                  </div>
                  {conv.last_message && (
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      {conv.last_message.role === 'assistant' ? '🤖 ' : '👤 '}
                      {conv.last_message.content.startsWith('[media:')
                        ? '📎 Archivo adjunto'
                        : conv.last_message.content}
                    </p>
                  )}
                  <div className="mt-1 flex items-center gap-2">
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', STATUS_STYLE[conv.status])}>
                      {STATUS_LABEL[conv.status]}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-gray-400">
                      <Clock className="h-3 w-3" />
                      {formatDate(conv.last_activity)}
                    </span>
                  </div>
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* Right panel — conversation detail */}
      <div className="flex flex-1 flex-col bg-gray-50">
        {!selectedId ? (
          <div className="flex h-full flex-col items-center justify-center text-gray-400">
            <MessageSquare className="mb-3 h-12 w-12" />
            <p className="text-sm">Selecciona una conversación</p>
          </div>
        ) : !detail ? (
          <div className="flex h-full items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
              <div>
                <p className="font-semibold text-gray-900">{detail.contact.name}</p>
                <p className="text-xs text-gray-500">{detail.contact.phone}</p>
              </div>
              <div className="flex items-center gap-2">
                {detail.status !== 'escalated' && (
                  <button
                    onClick={() => statusMutation.mutate({ id: detail.id, status: 'escalated' })}
                    className="flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-600 hover:bg-orange-100 transition-colors"
                  >
                    <AlertCircle className="h-3.5 w-3.5" />
                    Escalar
                  </button>
                )}
                {detail.status !== 'closed' && (
                  <button
                    onClick={() => statusMutation.mutate({ id: detail.id, status: 'closed' })}
                    className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                  >
                    <CheckCircle className="h-3.5 w-3.5" />
                    Cerrar
                  </button>
                )}
                <button
                  onClick={() => setSelectedId(null)}
                  className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
              {!detail.messages.length ? (
                <p className="text-center text-sm text-gray-400">Sin mensajes registrados</p>
              ) : (
                detail.messages.map((msg, i) => (
                  <div
                    key={i}
                    className={cn(
                      'flex',
                      msg.role === 'assistant' ? 'justify-start' : 'justify-end'
                    )}
                  >
                    <div
                      className={cn(
                        'max-w-[70%] rounded-2xl px-4 py-2.5 text-sm',
                        msg.role === 'assistant'
                          ? 'rounded-tl-sm bg-white text-gray-800 shadow-sm'
                          : 'rounded-tr-sm bg-brand-500 text-white'
                      )}
                    >
                      <MediaMessage content={msg.content} />
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Reply input */}
            {detail.status !== 'closed' && (
              <div className="border-t border-gray-200 bg-white px-4 py-3">
                <div className="flex items-end gap-2">
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        handleSend()
                      }
                    }}
                    placeholder="Escribe un mensaje… (Enter para enviar, Shift+Enter para nueva línea)"
                    rows={2}
                    className="flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400"
                  />
                  <button
                    onClick={handleSend}
                    disabled={!replyText.trim() || replyMutation.isPending}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {replyMutation.isPending
                      ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      : <Send className="h-4 w-4" />}
                  </button>
                </div>
                {replyMutation.isError && (
                  <p className="mt-1 text-xs text-red-500">Error al enviar. Intenta de nuevo.</p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
