import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { Gift, Copy, CheckCheck } from 'lucide-react'

interface ReferralStats {
  code: string | null
  referred_count: number
  paying_referrals: number
}

const SITE_URL = (import.meta.env.VITE_SITE_URL as string | undefined) ?? (typeof window !== 'undefined' ? window.location.origin : '')

export default function ReferralCard() {
  const [copied, setCopied] = useState(false)

  const { data } = useQuery<ReferralStats>({
    queryKey: ['referral-stats'],
    queryFn: () => api.get('/me/referral').then((r) => r.data),
    staleTime: 60_000,
  })

  if (!data?.code) return null

  const referralLink = `${SITE_URL}/register?ref=${data.code}`

  const handleCopy = () => {
    navigator.clipboard.writeText(referralLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-3">
      <div className="flex items-center gap-2 text-base font-semibold text-foreground">
        <Gift size={18} className="text-brand-500" />
        Refiere y gana
      </div>
      <p className="text-sm text-muted-foreground">
        Cuando alguien se registra con tu link y se vuelve cliente de pago, tú y esa persona reciben 1 mes gratis.
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <code className="flex-1 min-w-0 truncate rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground">
          {referralLink}
        </code>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs px-3 py-2 bg-gray-100 dark:bg-gray-900 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 transition"
        >
          {copied ? <CheckCheck size={14} /> : <Copy size={14} />}
          {copied ? 'Copiado' : 'Copiar'}
        </button>
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
        <span><b className="text-foreground">{data.referred_count}</b> registrados con tu link</span>
        <span><b className="text-foreground">{data.paying_referrals}</b> ya son clientes</span>
      </div>
    </div>
  )
}
