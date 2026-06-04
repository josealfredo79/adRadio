import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { CheckCircle2, Upload, Users, Megaphone, X, ChevronRight, Loader2 } from 'lucide-react'

interface Props {
  onClose: () => void
}

const STEPS = [
  { id: 1, icon: Upload, label: 'Base de conocimiento', desc: 'Sube un documento para que tu bot responda preguntas' },
  { id: 2, icon: Users, label: 'Primer contacto', desc: 'Agrega un número de WhatsApp a tu lista' },
  { id: 3, icon: Megaphone, label: 'Primera campaña', desc: 'Envía tu primer mensaje masivo' },
]

export default function OnboardingWizard({ onClose }: Props) {
  const [step, setStep] = useState(1)
  const [completed, setCompleted] = useState<number[]>([])
  const navigate = useNavigate()
  const qc = useQueryClient()

  // Step 1 — KB upload
  const [kbFile, setKbFile] = useState<File | null>(null)
  const [kbName, setKbName] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const uploadKbMutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData()
      fd.append('file', kbFile!)
      fd.append('name', kbName || kbFile!.name)
      return api.post('/knowledge-base/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge-base'] })
      setCompleted((p) => [...p, 1])
      setStep(2)
    },
  })

  // Step 2 — Add contact
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [phoneError, setPhoneError] = useState('')

  const formatE164 = (raw: string): string => {
    const digits = raw.replace(/\D/g, '')
    if (raw.startsWith('+')) return `+${digits}`
    return `+${digits}`
  }

  const addContactMutation = useMutation({
    mutationFn: () => api.post('/contacts', { name: contactName, phone: formatE164(contactPhone) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contacts'] })
      setCompleted((p) => [...p, 2])
      setStep(3)
    },
  })

  function finish() {
    onClose()
    navigate('/app/campaigns')
  }

  const stepError = (uploadKbMutation.error as any)?.response?.data?.detail
    || (addContactMutation.error as any)?.response?.data?.detail

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 dark:bg-black/80">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl overflow-hidden dark:bg-gray-950">
        {/* Header */}
        <div className="bg-gradient-to-r from-brand-600 to-brand-500 px-6 py-5 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold">¡Bienvenido a IaRadio! 🎙️</h2>
              <p className="mt-0.5 text-sm text-brand-100">Configura tu cuenta en 3 pasos</p>
            </div>
            <button onClick={onClose} className="text-brand-200 hover:text-white dark:text-brand-300"><X className="h-5 w-5" /></button>
          </div>
          {/* Progress */}
          <div className="mt-4 flex items-center gap-2">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center gap-2">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-all ${
                  completed.includes(s.id) ? 'bg-white text-brand-600 dark:text-brand-400' :
                  step === s.id ? 'bg-brand-400 text-white ring-2 ring-white dark:bg-brand-500' :
                  'bg-brand-700/50 text-brand-200 dark:bg-brand-600/50 dark:text-brand-300'
                }`}>
                  {completed.includes(s.id) ? <CheckCircle2 className="h-4 w-4" /> : s.id}
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`h-0.5 w-10 transition-all ${completed.includes(s.id) ? 'bg-white' : 'bg-brand-700/50 dark:bg-brand-600/50'}`} />
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="p-6">
          {stepError && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/30 dark:text-red-400">{stepError}</p>}

          {/* Step 1: Knowledge Base */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-gray-100">Sube tu base de conocimiento</h3>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Un PDF, TXT o DOCX con info de tu negocio. El bot la usará para responder clientes.</p>
              </div>
              <div
                className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-6 py-8 hover:border-brand-400 hover:bg-brand-50 transition-colors dark:border-gray-600 dark:hover:bg-brand-950/30"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="h-8 w-8 text-gray-400 dark:text-gray-500" />
                <p className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">{kbFile ? kbFile.name : 'Haz clic para seleccionar archivo'}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">PDF, TXT, DOCX — máx. 10MB</p>
                <input ref={fileRef} type="file" accept=".pdf,.txt,.docx" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) { setKbFile(f); setKbName(f.name.replace(/\.[^.]+$/, '')) } }} />
              </div>
              {kbFile && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre del documento</label>
                  <input value={kbName} onChange={(e) => setKbName(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-700" />
                </div>
              )}
              <div className="flex items-center justify-between pt-1">
                <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-400">Omitir por ahora</button>
                <div className="flex gap-2">
                  {!kbFile && (
                    <button onClick={() => { setCompleted((p) => [...p, 1]); setStep(2) }}
                      className="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800">
                      Saltar <ChevronRight className="h-4 w-4" />
                    </button>
                  )}
                  {kbFile && (
                    <button onClick={() => uploadKbMutation.mutate()} disabled={uploadKbMutation.isPending}
                      className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60 dark:bg-brand-500 dark:hover:bg-brand-600">
                      {uploadKbMutation.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Subiendo...</> : <>Subir y continuar <ChevronRight className="h-4 w-4" /></>}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Add contact */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-gray-100">Agrega tu primer contacto</h3>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Ingresa un número de WhatsApp para comenzar a enviar mensajes.</p>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Nombre</label>
                <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="Ej: María García"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-700" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Teléfono (con código de país)</label>
                <input value={contactPhone} onChange={(e) => { setContactPhone(e.target.value); setPhoneError('') }} placeholder="Ej: 521234567890"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-700" />
                {phoneError && <p className="mt-1 text-xs text-red-500">{phoneError}</p>}
              </div>
              <div className="flex items-center justify-between pt-1">
                <button onClick={() => setStep(1)} className="text-sm text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-400">← Atrás</button>
                <div className="flex gap-2">
                  <button onClick={() => { setCompleted((p) => [...p, 2]); setStep(3) }}
                    className="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800">
                    Saltar <ChevronRight className="h-4 w-4" />
                  </button>
                  <button onClick={() => {
                    const formatted = formatE164(contactPhone)
                    if (formatted.length < 8) { setPhoneError('El número debe tener al menos 8 dígitos'); return }
                    if (!formatted.startsWith('+')) { setPhoneError('Debe incluir código de país'); return }
                    addContactMutation.mutate()
                  }} disabled={!contactName || !contactPhone || addContactMutation.isPending}
                    className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60 dark:bg-brand-500 dark:hover:bg-brand-600">
                    {addContactMutation.isPending ? <><Loader2 className="h-4 w-4 animate-spin" /> Guardando...</> : <>Agregar y continuar <ChevronRight className="h-4 w-4" /></>}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Create campaign */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="text-center py-4">
                <CheckCircle2 className="mx-auto h-12 w-12 text-green-500 dark:text-green-400" />
                <h3 className="mt-3 font-semibold text-gray-900 dark:text-gray-100">¡Todo listo para tu primera campaña!</h3>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Ahora puedes crear y enviar campañas de WhatsApp a tus contactos.</p>
              </div>
              <div className="flex flex-col gap-3">
                <button onClick={finish}
                  className="flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-6 py-3 font-medium text-white hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-600">
                  <Megaphone className="h-5 w-5" /> Crear mi primera campaña
                </button>
                <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-400 text-center">
                  Explorar primero el panel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
