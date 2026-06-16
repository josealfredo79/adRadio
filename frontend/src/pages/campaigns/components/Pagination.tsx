import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaginationProps {
  page: number
  totalPages: number
  totalCampaigns: number
  onPageChange: (page: number) => void
}

export function Pagination({
  page,
  totalPages,
  totalCampaigns,
  onPageChange,
}: PaginationProps) {
  if (totalPages <= 1) return null

  function getPageNumbers() {
    const pages: (number | string)[] = [1]
    const delta = 1
    const rangeStart = Math.max(2, page - delta)
    const rangeEnd = Math.min(totalPages - 1, page + delta)
    if (rangeStart > 2) pages.push('...')
    for (let i = rangeStart; i <= rangeEnd; i++) pages.push(i)
    if (rangeEnd < totalPages - 1) pages.push('...')
    if (totalPages > 1) pages.push(totalPages)
    return pages
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-1">
      <p className="text-sm text-muted-foreground">
        Mostrando {Math.min((page - 1) * 20 + 1, totalCampaigns)}-{Math.min(page * 20, totalCampaigns)} de {totalCampaigns} campañas
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-gray-800 dark:hover:bg-gray-900"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        {getPageNumbers().map((p, i) =>
          p === '...' ? (
            <span key={`ellipsis-${i}`} className="px-2 text-sm text-muted-foreground">
              ...
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                page === p
                  ? 'bg-brand-500 text-white'
                  : 'text-muted-foreground hover:bg-muted dark:hover:bg-gray-900'
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-gray-800 dark:hover:bg-gray-900"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
