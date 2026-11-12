// Las fotos de un celular nuevo pesan 3–8 MB y el servidor acepta hasta 5 MB.
// Antes de subirlas se achican a 1600 px por lado en JPEG: pesan ~300 KB, suben
// rápido con mala señal y se ven igual en un cartel de 1080 px.
// Si el navegador no puede (o la foto ya es chica), se sube tal cual.

const MAX_SIDE = 1600
const SMALL_ENOUGH = 1.5 * 1024 * 1024

export async function shrinkPhoto(file: File): Promise<File> {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height))
    if (k === 1 && file.size <= SMALL_ENOUGH) {
      bmp.close()
      return file
    }
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bmp.width * k)
    canvas.height = Math.round(bmp.height * k)
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height)
    bmp.close()
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/jpeg', 0.85))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' })
  } catch {
    return file
  }
}
