import { getApiError } from '@/lib/api'
import ChatAvatar from '@/components/ChatAvatar'
import { chatTime, idlePreview, isUnread, type MyBusiness } from '@/lib/customerChats'

// Los chats del cliente, uno por negocio (último mensaje, hora, no leídos).
// En el celular es la pantalla de /mi; en computadora, el panel izquierdo.
export default function CustomerChatList({
  businesses,
  isLoading,
  error,
  activePath,
  filter = '',
  onOpen,
}: {
  businesses: MyBusiness[] | undefined
  isLoading?: boolean
  error?: unknown
  activePath?: string
  filter?: string
  onOpen: (path: string) => void
}) {
  const q = filter.trim().toLowerCase()
  const list = (businesses ?? []).filter((b) => !q || b.name.toLowerCase().includes(q))
  return (
    <>
      {isLoading && <p className="mt-8 px-4 text-white/50">Cargando…</p>}
      {!!error && <p className="mt-8 px-4 text-rose-400">{getApiError(error, 'No se pudieron cargar tus chats')}</p>}
      {businesses && q && list.length === 0 && <p className="mt-6 px-4 text-sm text-white/50">Ningún chat con "{filter}".</p>}
      <ul>
        {list.map((b) => {
          const active = b.portal_path === activePath
          const unread = !active && isUnread(b)
          const m = b.last_message
          return (
            <li key={b.portal_path}>
              <button
                onClick={() => onOpen(b.portal_path)}
                className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors active:bg-white/[0.06] ${
                  active ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]'
                }`}
              >
                <ChatAvatar name={b.name} logo={b.logo_url} color={b.color} />
                <div className="min-w-0 flex-1 border-b border-white/[0.06] pb-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="truncate font-semibold">{b.name}</p>
                    <span className={`shrink-0 text-xs ${unread ? 'font-semibold text-emerald-400' : 'text-white/40'}`}>
                      {chatTime(m?.at ?? null)}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center justify-between gap-2">
                    <p className={`truncate text-sm ${unread ? 'text-white' : 'text-white/55'}`}>
                      {m ? `${m.from_me ? 'Tú: ' : ''}${m.text}` : idlePreview(b)}
                    </p>
                    {unread && (
                      <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500 px-1.5 text-[11px] font-bold text-black">
                        1
                      </span>
                    )}
                  </div>
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </>
  )
}
