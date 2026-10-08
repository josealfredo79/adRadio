import { useEffect, useState } from 'react'

// Pantalla de computadora: la app del cliente se ve como WhatsApp Web (lista
// de chats a la izquierda, conversación a la derecha). En el celular, una cosa a la vez.
const QUERY = '(min-width: 1024px)'

export function useIsDesktop(): boolean {
  const [desktop, setDesktop] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.(QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia?.(QUERY)
    if (!mq) return
    const on = () => setDesktop(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return desktop
}
