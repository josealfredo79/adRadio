import { useRef, useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { BookOpen, Upload, Trash2, FileText, FileSpreadsheet, File, Eye, X } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import SEO from '@/components/SEO'
import { useToast } from '@/contexts/ToastContext'

interface KBFile {
  id: string
  filename: string
  file_type: string
  version: number
  processing_status: 'processing' | 'done' | 'error'
  created_at: string
}

const FILE_ICONS: Record<string, typeof File> = {
  docx: FileText,
  pdf: FileText,
  xlsx: FileSpreadsheet,
}

export default function KnowledgeBasePage() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [viewFileId, setViewFileId] = useState<string | null>(null)

  const { data: viewContent } = useQuery<{ id: string; filename: string; file_type: string; raw_text: string }>({
    queryKey: ['knowledge-base', viewFileId, 'content'],
    queryFn: () => api.get(`/knowledge-base/${viewFileId}/content`).then((r) => r.data),
    enabled: !!viewFileId,
  })

  const { data: files, isLoading } = useQuery<KBFile[]>({
    queryKey: ['knowledge-base'],
    queryFn: () => api.get('/knowledge-base').then((r) => r.data),
  })

  // Poll while any file is still processing
  const hasProcessing = files?.some((f) => f.processing_status === 'processing')
  useEffect(() => {
    if (!hasProcessing) return
    const id = setInterval(() => qc.invalidateQueries({ queryKey: ['knowledge-base'] }), 4000)
    return () => clearInterval(id)
  }, [hasProcessing, qc])

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/knowledge-base/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledge-base'] }),
  })

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      await api.post('/knowledge-base/upload', fd)
      qc.invalidateQueries({ queryKey: ['knowledge-base'] })
    } catch (err: unknown) {
      toast({ title: 'Error', description: getApiError(err, 'Error al subir archivo'), variant: 'error' })
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <>
      <SEO title="Base de conocimiento" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Base de conocimiento</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Sube documentos para que tu bot responda con información real de tu negocio
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-brand-500 dark:bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors">
          <Upload className="h-4 w-4" />
          Subir documento
          <input
            ref={fileRef}
            type="file"
            accept=".docx,.pdf,.xlsx,.txt"
            className="hidden"
            onChange={handleUpload}
          />
        </label>
      </div>

      {/* Supported formats */}
      <div className="rounded-xl border border-blue-100 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/30 px-5 py-4">
        <p className="text-sm font-medium text-blue-700 dark:text-blue-300">Formatos soportados</p>
        <p className="mt-1 text-sm text-blue-600 dark:text-blue-400">
          Word (.docx), PDF (.pdf), Excel (.xlsx), Texto (.txt) — Máx. 50MB por archivo
        </p>
      </div>

      {/* Files list */}
      <div className="rounded-xl bg-white dark:bg-gray-950 shadow-sm border border-gray-100 dark:border-gray-800 overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-14 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse" />
            ))}
          </div>
        ) : !files?.length ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500">
            <BookOpen className="h-12 w-12 mb-3" />
            <p className="text-sm">No hay documentos todavía</p>
            <p className="text-xs mt-1">
              Sube tu menú, catálogo, preguntas frecuentes o cualquier información de tu negocio
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {files.map((file) => {
              const Icon = FILE_ICONS[file.file_type] ?? File
              return (
                <div
                  key={file.id}
                  className="flex items-center gap-4 px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-950/30">
                    <Icon className="h-5 w-5 text-brand-500 dark:text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{file.filename}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {file.file_type.toUpperCase()} · Subido {formatDate(file.created_at)}
                    </p>
                  </div>
                  {file.processing_status === 'processing' ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-700 animate-pulse dark:bg-yellow-900/40 dark:text-yellow-300">
                      Procesando…
                    </span>
                  ) : file.processing_status === 'error' ? (
                    <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-600 dark:bg-red-900/40 dark:text-red-400">
                      Error
                    </span>
                  ) : (
                    <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-600 dark:bg-green-900/40 dark:text-green-300">
                      Procesado
                    </span>
                  )}
                  <button
                    onClick={() => setViewFileId(file.id)}
                    className="text-gray-400 dark:text-gray-500 hover:text-brand-500 dark:hover:text-brand-400 transition-colors"
                    title="Ver contenido"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm('¿Eliminar este documento?')) deleteMutation.mutate(file.id)
                    }}
                    className="text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>

    {/* Content viewer modal */}
    {viewFileId && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setViewFileId(null)}>
        <div
          className="relative w-full max-w-3xl max-h-[80vh] rounded-xl bg-white dark:bg-gray-950 shadow-xl border border-gray-200 dark:border-gray-800 flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 truncate">{viewContent?.filename ?? 'Cargando...'}</h2>
              {viewContent && <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">{viewContent.file_type}</p>}
            </div>
            <button
              onClick={() => setViewFileId(null)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="overflow-y-auto p-6">
            {!viewContent ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-4 rounded bg-gray-100 dark:bg-gray-800 animate-pulse" />
                ))}
              </div>
            ) : viewContent.raw_text ? (
              <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 font-sans leading-relaxed">
                {viewContent.raw_text}
              </pre>
            ) : (
              <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-8">
                No hay texto extraído disponible para este documento.
              </p>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  )
}
