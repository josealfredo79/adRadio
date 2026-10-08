import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MessageCircle, Search } from 'lucide-react'
import CustomerChatList from '@/components/CustomerChatList'
import { readAccountToken, readRecentChats } from '@/lib/customerAccount'
import { useMyBusinesses, type MyBusiness } from '@/lib/customerChats'

// La app del cliente en computadora, como WhatsApp Web: la lista de chats a la
// izquierda (todos sus negocios si entró con su número; si no, los que abrió en
// este navegador) y el chat o la info a la derecha (children).
export default function CustomerDesktopShell({ activePath, children }: { activePath?: string; children?: React.ReactNode }) {
  const navigate = useNavigate()
  const [token] = useState(readAccountToken)
  const [filter, setFilter] = useState('')
  const { data, isLoading, error } = useMyBusinesses(token)
  const businesses: MyBusiness[] | undefined = token
    ? data?.businesses
    : readRecentChats().map((c) => ({
        portal_path: c.portal_path, name: c.name, logo_url: c.logo_url, color: c.color, city: '',
        loyalty: null, next_appointment: null, coupons: 0, last_message: null,
      }))

  return (
    <div className="fixed inset-0 flex bg-[#0b141a] text-white">
      <aside className="flex w-[400px] shrink-0 flex-col border-r border-white/10 bg-[#111b21]">
        <div className="flex items-center justify-between px-4 pb-2 pt-4">
          <h1 className="text-xl font-bold">Chats</h1>
          <span className="text-sm font-semibold text-emerald-400">IaRadio</span>
        </div>
        <div className="px-3 pb-2">
          <label className="flex items-center gap-2 rounded-lg bg-[#202c33] px-3 py-2 text-sm text-white/60">
            <Search size={16} />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Buscar un negocio"
              className="min-w-0 flex-1 bg-transparent text-white outline-none placeholder:text-white/40"
            />
          </label>
        </div>
        <div className="flex-1 overflow-y-auto">
          <CustomerChatList
            businesses={businesses}
            isLoading={!!token && isLoading}
            error={token ? error : null}
            activePath={activePath}
            filter={filter}
            onOpen={(path) => navigate(path)}
          />
          {!token && (
            <Link to="/mi" className="m-4 block rounded-xl border border-white/10 px-4 py-3 text-sm text-white/70 hover:bg-white/[0.04]">
              <span className="font-semibold text-white">¿Eres cliente de más negocios?</span>
              <br />
              Entra con tu número y ve todos tus chats aquí.
            </Link>
          )}
        </div>
      </aside>
      <main className="relative min-w-0 flex-1">
        {children ?? (
          <div className="flex h-full flex-col items-center justify-center gap-3 border-b-[6px] border-emerald-500 text-center text-white/60">
            <MessageCircle size={56} className="text-white/25" />
            <p className="text-2xl font-light text-white/80">IaRadio para clientes</p>
            <p className="max-w-sm text-sm">Elige un chat de la izquierda para platicar con el negocio. Te contesta al instante, gratis.</p>
          </div>
        )}
      </main>
    </div>
  )
}
