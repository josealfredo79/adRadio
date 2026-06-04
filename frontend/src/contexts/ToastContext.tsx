import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import * as ToastPrimitive from '@radix-ui/react-toast'
import { Toast } from '@/components/Toast'

interface ToastItem {
  id: string
  title?: string
  description?: string
  variant?: 'success' | 'error' | 'info' | 'warning'
}

interface ToastContextType {
  toast: (props: Omit<ToastItem, 'id'>) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback((props: Omit<ToastItem, 'id'>) => {
    const id = Math.random().toString(36).slice(2, 9)
    setToasts((prev) => [...prev, { ...props, id }])
    setTimeout(() => removeToast(id), 4000)
  }, [removeToast])

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map((item) => (
          <Toast key={item.id} toast={item} onClose={() => removeToast(item.id)} />
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] m-0 flex max-h-screen w-full max-w-[420px] flex-col-reverse gap-2 p-4 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
