import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import PageBuilderModal from '@/components/PageBuilderModal'

// Tarjeta del panel: el dueño sin página la arma con el bot de IaRadio.
export default function PageBuilderCard() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)

  if (!user || user.role !== 'advertiser' || user.slug) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-4 rounded-2xl border border-brand-200 bg-brand-50 p-5 text-left transition-shadow hover:shadow-md dark:border-brand-900 dark:bg-brand-950/30"
      >
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-500 text-white">
          <Sparkles className="h-7 w-7" />
        </span>
        <span>
          <span className="block text-lg font-bold text-foreground">Arma tu página con IaRadio</span>
          <span className="block text-base text-muted-foreground">
            Cuéntale de tu negocio por voz o texto y en unos minutos tienes tu página, tu catálogo y tu bot listos.
          </span>
        </span>
      </button>
      {open && <PageBuilderModal onClose={() => setOpen(false)} />}
    </>
  )
}
