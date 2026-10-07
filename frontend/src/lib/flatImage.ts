// ¿La imagen es un fondo liso (un color, un degradado) y no una foto o un logo
// de verdad? Pasa con "portadas" y "logos" de relleno: la página los trata como
// si no existieran y usa las fotos de su giro. Si el navegador no deja leer los
// píxeles (imagen de otro dominio), se asume que es buena.
// Umbrales (diferencia media entre pixeles vecinos, 0–765): una foto real
// da 45–110; un degradado de relleno ~2. Para logos se usa uno más estricto,
// porque un logo sencillo (una marca chica sobre fondo blanco) tiene poco borde.
export const FLAT_PHOTO = 8
export const FLAT_LOGO = 0.6

export function isFlatImage(img: HTMLImageElement, threshold = FLAT_PHOTO): boolean {
  try {
    const n = 32
    const canvas = document.createElement('canvas')
    canvas.width = n
    canvas.height = n
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx || !img.naturalWidth) return false
    ctx.drawImage(img, 0, 0, n, n)
    const d = ctx.getImageData(0, 0, n, n).data
    // Promedio de la diferencia entre cada pixel y el de al lado: en una foto
    // (o un logo con letras/forma) hay bordes; en un liso o degradado casi no.
    let sum = 0
    let count = 0
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n - 1; x++) {
        const a = (y * n + x) * 4
        const b = a + 4
        sum += Math.abs(d[a] - d[b]) + Math.abs(d[a + 1] - d[b + 1]) + Math.abs(d[a + 2] - d[b + 2])
        count++
      }
    }
    for (let y = 0; y < n - 1; y++) {
      for (let x = 0; x < n; x++) {
        const a = (y * n + x) * 4
        const b = a + n * 4
        sum += Math.abs(d[a] - d[b]) + Math.abs(d[a + 1] - d[b + 1]) + Math.abs(d[a + 2] - d[b + 2])
        count++
      }
    }
    return sum / count < threshold
  } catch {
    return false
  }
}
