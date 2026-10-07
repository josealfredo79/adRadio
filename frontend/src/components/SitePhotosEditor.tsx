import { useRef, useState } from 'react'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { ChevronLeft, ChevronRight, ImagePlus, Loader2, Trash2 } from 'lucide-react'
import { stockPhotos } from '@/pages/publicSite/utils'

const MAX = 8

// Fotos del carrusel de la portada de /sitio/{slug}. Se guardan al momento
// (como el logo): subir, mover y quitar. Sin fotos, la página usa las de stock de su giro.
export default function SitePhotosEditor() {
  const { user, setUser } = useAuth()
  // La portada única de antes (hero_image_url) cuenta como la primera foto.
  const photos = user?.site_photos?.length ? user.site_photos : user?.hero_image_url ? [user.hero_image_url] : []
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')

  const upload = async (files: FileList) => {
    setError('')
    const room = MAX - photos.length
    const list = Array.from(files).slice(0, room)
    if (files.length > room) setError(`Caben ${MAX} fotos; subí las primeras ${room}.`)
    for (let k = 0; k < list.length; k++) {
      setBusy(`Subiendo ${k + 1} de ${list.length}…`)
      const fd = new FormData()
      fd.append('file', list[k])
      try {
        const r = await api.post('/me/site-photos', fd, { timeout: 60000 })
        setUser?.(r.data)
      } catch (err) {
        setError(getApiError(err, 'No se pudo subir la foto'))
        break
      }
    }
    setBusy(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const save = async (next: string[]) => {
    setError('')
    setBusy('Guardando…')
    try {
      const r = await api.put('/me/site-photos', { photos: next })
      setUser?.(r.data)
    } catch (err) {
      setError(getApiError(err, 'No se pudo guardar'))
    } finally {
      setBusy(null)
    }
  }

  const move = (k: number, d: number) => {
    const next = [...photos]
    ;[next[k], next[k + d]] = [next[k + d], next[k]]
    void save(next)
  }

  const btn = 'rounded-full bg-black/60 p-1 text-white hover:bg-black/80 disabled:opacity-40'

  return (
    <div className="space-y-2">
      <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
        Fotos de tu negocio (portada y galería) · {photos.length}/{MAX}
      </label>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        La primera es la portada. Sube fotos reales: tu local, tus productos, tu equipo.
        {!photos.length && ' Mientras no subas, mostramos fotos de ejemplo de tu giro.'}
      </p>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {photos.map((src, k) => (
          <div key={src} className="group relative aspect-[4/3] overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
            <img src={src} alt={`Foto ${k + 1}`} className="h-full w-full object-cover" />
            {k === 0 && (
              <span className="absolute left-1 top-1 rounded bg-brand-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">Portada</span>
            )}
            <div className="absolute inset-x-1 bottom-1 flex justify-between">
              <span className="flex gap-1">
                <button type="button" aria-label="Mover a la izquierda" disabled={!!busy || k === 0} onClick={() => move(k, -1)} className={btn}>
                  <ChevronLeft size={14} />
                </button>
                <button type="button" aria-label="Mover a la derecha" disabled={!!busy || k === photos.length - 1} onClick={() => move(k, 1)} className={btn}>
                  <ChevronRight size={14} />
                </button>
              </span>
              <button type="button" aria-label="Quitar foto" disabled={!!busy} onClick={() => void save(photos.filter((p) => p !== src))} className={btn}>
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {photos.length < MAX && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={!!busy}
            className="flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-gray-300 text-xs font-medium text-gray-500 transition-colors hover:border-brand-400 hover:text-brand-500 disabled:opacity-50 dark:border-gray-700"
          >
            {busy ? <Loader2 size={18} className="animate-spin" /> : <ImagePlus size={20} />}
            {busy ?? 'Agregar fotos'}
          </button>
        )}
      </div>
      {!photos.length && (
        <div className="flex gap-1.5 overflow-hidden rounded-lg opacity-70">
          {stockPhotos(user?.business_category ?? '').slice(0, 4).map((src) => (
            <img key={src} src={src} alt="" className="h-10 w-16 rounded object-cover" />
          ))}
          <span className="self-center text-[11px] text-gray-500">← fotos de ejemplo de tu giro</span>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        className="hidden"
        onChange={(e) => e.target.files?.length && void upload(e.target.files)}
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
