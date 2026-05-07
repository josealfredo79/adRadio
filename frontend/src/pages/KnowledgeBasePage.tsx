import { useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { BookOpen, Upload, Trash2, FileText, FileSpreadsheet, File } from 'lucide-react'
import { formatDate } from '@/lib/utils'

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
  const fileRef = useRef<HTMLInputElement>(null)

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
    } catch (err: any) {
      alert(err.response?.data?.detail ?? 'Error al subir archivo')
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Base de conocimiento</h1>
          <p className="mt-1 text-sm text-gray-500">
            Sube documentos para que tu bot responda con información real de tu negocio
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors">
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
      <div className="rounded-xl border border-blue-100 bg-blue-50 px-5 py-4">
        <p className="text-sm font-medium text-blue-700">Formatos soportados</p>
        <p className="mt-1 text-sm text-blue-600">
          Word (.docx), PDF (.pdf), Excel (.xlsx), Texto (.txt) — Máx. 50MB por archivo
        </p>
      </div>

      {/* Files list */}
      <div className="rounded-xl bg-white shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-14 rounded-lg bg-gray-100 animate-pulse" />
            ))}
          </div>
        ) : !files?.length ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <BookOpen className="h-12 w-12 mb-3" />
            <p className="text-sm">No hay documentos todavía</p>
            <p className="text-xs mt-1">
              Sube tu menú, catálogo, preguntas frecuentes o cualquier información de tu negocio
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {files.map((file) => {
              const Icon = FILE_ICONS[file.file_type] ?? File
              return (
                <div
                  key={file.id}
                  className="flex items-center gap-4 px-6 py-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50">
                    <Icon className="h-5 w-5 text-brand-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{file.filename}</p>
                    <p className="text-xs text-gray-500">
                      {file.file_type.toUpperCase()} · Subido {formatDate(file.created_at)}
                    </p>
                  </div>
                  {file.processing_status === 'processing' ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-700 animate-pulse">
                      Procesando…
                    </span>
                  ) : file.processing_status === 'error' ? (
                    <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-600">
                      Error
                    </span>
                  ) : (
                    <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-600">
                      Procesado
                    </span>
                  )}
                  <button
                    onClick={() => {
                      if (confirm('¿Eliminar este documento?')) deleteMutation.mutate(file.id)
                    }}
                    className="text-gray-400 hover:text-red-500 transition-colors"
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
  )
}
