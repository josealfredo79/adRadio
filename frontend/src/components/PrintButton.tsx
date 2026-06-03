import { Printer } from 'lucide-react'

interface PrintButtonProps {
  label?: string
  className?: string
}

export default function PrintButton({ label = 'Imprimir / PDF', className = '' }: PrintButtonProps) {
  return (
    <button
      onClick={() => window.print()}
      className={`flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors ${className}`}
    >
      <Printer className="h-4 w-4" />
      {label}
    </button>
  )
}
