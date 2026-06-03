import { useState, useEffect } from 'react'

type Consent = 'all' | 'necessary' | null

export default function CookieConsent() {
  const [consent, setConsent] = useState<Consent>(null)

  useEffect(() => {
    const stored = localStorage.getItem('cookie_consent') as Consent | null
    if (stored === 'all' || stored === 'necessary') {
      setConsent(stored)
    }
  }, [])

  const accept = (value: 'all' | 'necessary') => {
    localStorage.setItem('cookie_consent', value)
    setConsent(value)
  }

  if (consent) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[100]">
      <div className="mx-auto max-w-5xl px-4 pb-4">
        <div className="rounded-t-2xl bg-white/90 backdrop-blur-md border border-gray-200 shadow-lg px-6 py-4 flex flex-col sm:flex-row items-center gap-4">
          <p className="text-sm text-gray-600 flex-1 text-center sm:text-left">
            🍪 Usamos cookies propias y de terceros para mejorar tu experiencia. Al continuar navegando, aceptas su uso.
          </p>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => accept('necessary')}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Solo necesarias
            </button>
            <button
              onClick={() => accept('all')}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
            >
              Aceptar todas
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
