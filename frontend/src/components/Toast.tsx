import { useState } from 'react'
import * as ToastPrimitive from '@radix-ui/react-toast'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToastData {
  id: string
  title?: string
  description?: string
  variant?: 'success' | 'error' | 'info' | 'warning'
}

interface ToastProps {
  toast: ToastData
  onClose: () => void
}

const variantBorder: Record<string, string> = {
  success: 'border-l-green-500',
  error: 'border-l-red-500',
  info: 'border-l-blue-500',
  warning: 'border-l-yellow-500',
}

const variantAccent: Record<string, string> = {
  success: 'bg-green-50 dark:bg-green-950/20',
  error: 'bg-red-50 dark:bg-red-950/20',
  info: 'bg-blue-50 dark:bg-blue-950/20',
  warning: 'bg-yellow-50 dark:bg-yellow-950/20',
}

export function Toast({ toast, onClose }: ToastProps) {
  const [open, setOpen] = useState(true)
  const variant = toast.variant ?? 'info'

  return (
    <ToastPrimitive.Root
      open={open}
      onOpenChange={(val) => { if (!val) { setOpen(false); onClose() } }}
      className={cn(
        'pointer-events-auto flex w-full items-start gap-3 rounded-lg border bg-white p-4 shadow-lg backdrop-blur-sm',
        'border-l-4',
        variantBorder[variant],
        variantAccent[variant],
        'dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-80 data-[state=open]:slide-in-from-top-full',
        'data-[state=open]:sm:slide-in-from-bottom-full',
        'data-[state=closed]:slide-out-to-right-full',
        'data-[swipe=end]:animate-out',
        'data-[swipe-direction=right]:translate-x-[var(--radix-toast-swipe-end-x)]',
      )}
    >
      <div className="flex-1 space-y-1">
        {toast.title && (
          <ToastPrimitive.Title className="text-sm font-semibold">
            {toast.title}
          </ToastPrimitive.Title>
        )}
        {toast.description && (
          <ToastPrimitive.Description className="text-sm text-gray-500 dark:text-gray-400">
            {toast.description}
          </ToastPrimitive.Description>
        )}
      </div>
      <ToastPrimitive.Close className="shrink-0 rounded-md p-1 text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:hover:text-gray-300">
        <X className="h-4 w-4" />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  )
}
