import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

// El hilo del Copiloto vive aquí, un nivel arriba de las rutas (en Layout,
// envolviendo <Outlet/>) — así cambiar de "menú" (navegar a Contactos,
// Campañas, etc.) y volver a /app/copilot NO reinicia la conversación. Si
// CopilotPage tuviera este estado como useState propio, cada vez que la
// ruta se desmonta React tira el estado y el usuario pierde el contexto.
export interface CopilotAction {
  tool: string
  summary: string
  data?: unknown
}

export interface PendingConfirmation {
  confirmation_id: string
  tool: string
  summary: string
  args?: Record<string, unknown>
}

export type CopilotFormTool = 'schedule_appointment' | 'create_coupon' | 'launch_campaign'

export interface CopilotChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  actions?: CopilotAction[]
  isError?: boolean
  moduleGrid?: boolean
  moduleLink?: { path: string; label: string }
  formTool?: CopilotFormTool
}

interface CopilotContextValue {
  messages: CopilotChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<CopilotChatMessage[]>>
  pendingConfirmation: PendingConfirmation | null
  setPendingConfirmation: (p: PendingConfirmation | null) => void
  resetConversation: () => void
}

export const COPILOT_STORAGE_KEY = 'iaradio_copilot_chat'
const STORAGE_KEY = COPILOT_STORAGE_KEY
// Cap generoso pero acotado — esto es continuidad de sesión, no un
// historial permanente; evita que sessionStorage crezca sin límite en una
// sesión de trabajo muy larga.
const MAX_STORED_MESSAGES = 60

const CopilotContext = createContext<CopilotContextValue | null>(null)

function loadStored(): { messages: CopilotChatMessage[]; pendingConfirmation: PendingConfirmation | null } {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return { messages: [], pendingConfirmation: null }
    const parsed = JSON.parse(raw)
    return {
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      pendingConfirmation: parsed.pendingConfirmation ?? null,
    }
  } catch {
    return { messages: [], pendingConfirmation: null }
  }
}

export function CopilotProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<CopilotChatMessage[]>(() => loadStored().messages)
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(
    () => loadStored().pendingConfirmation
  )

  useEffect(() => {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages: messages.slice(-MAX_STORED_MESSAGES), pendingConfirmation })
      )
    } catch {
      // sessionStorage lleno o bloqueado (modo privado, etc.) — la
      // conversación sigue funcionando en memoria, solo no sobrevive un
      // refresh completo. No es crítico, no interrumpimos al usuario.
    }
  }, [messages, pendingConfirmation])

  const resetConversation = () => {
    setMessages([])
    setPendingConfirmation(null)
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // ver nota arriba
    }
  }

  return (
    <CopilotContext.Provider value={{ messages, setMessages, pendingConfirmation, setPendingConfirmation, resetConversation }}>
      {children}
    </CopilotContext.Provider>
  )
}

export function useCopilot() {
  const ctx = useContext(CopilotContext)
  if (!ctx) throw new Error('useCopilot debe usarse dentro de <CopilotProvider>')
  return ctx
}
