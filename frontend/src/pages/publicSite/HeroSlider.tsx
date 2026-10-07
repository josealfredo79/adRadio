import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

// Carrusel de la portada: fotos a pantalla completa que cambian solas con un
// fundido y un zoom lento (Ken Burns), deslizables con el dedo. Las primeras
// son las del dueño; sin fotos propias, las de stock de su giro.
const SLIDE_MS = 5500

export default function HeroSlider({ photos, alt, children }: { photos: string[]; alt: string; children: React.ReactNode }) {
  const [i, setI] = useState(0)
  const [paused, setPaused] = useState(false)
  const touchX = useRef<number | null>(null)
  const n = photos.length
  const go = (d: number) => setI((v) => (v + d + n) % n)

  useEffect(() => {
    if (n < 2 || paused) return
    const t = setInterval(() => setI((v) => (v + 1) % n), SLIDE_MS)
    return () => clearInterval(t)
  }, [n, paused])

  return (
    <header
      className="psite-hero relative isolate flex overflow-hidden"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={(e) => { touchX.current = e.touches[0].clientX }}
      onTouchEnd={(e) => {
        if (touchX.current === null) return
        const dx = e.changedTouches[0].clientX - touchX.current
        touchX.current = null
        if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1)
      }}
    >
      {photos.map((src, k) => (
        <img
          key={src}
          src={src}
          alt={k === 0 ? alt : ''}
          aria-hidden={k !== i}
          // La primera sale al instante; las demás cuando toca.
          loading={k === 0 ? 'eager' : 'lazy'}
          fetchPriority={k === 0 ? 'high' : 'low'}
          className={`psite-slide absolute inset-0 -z-20 h-full w-full object-cover ${k === i ? 'psite-slide-on' : ''}`}
        />
      ))}
      {/* Velo para que el texto se lea sobre cualquier foto. */}
      <div
        className="absolute inset-0 -z-10"
        style={{ background: 'linear-gradient(180deg, rgba(0,0,0,.35) 0%, rgba(0,0,0,.15) 35%, rgba(0,0,0,.55) 70%, rgba(0,0,0,.85) 100%)' }}
      />
      {children}
      {n > 1 && (
        <>
          <div className="absolute bottom-5 right-5 z-10 flex items-center gap-1.5 sm:bottom-8 sm:right-8">
            {photos.map((src, k) => (
              <button
                key={src}
                onClick={() => setI(k)}
                aria-label={`Foto ${k + 1} de ${n}`}
                className="h-1.5 rounded-full transition-all duration-300"
                style={{ width: k === i ? 22 : 8, background: k === i ? '#fff' : 'rgba(255,255,255,.5)' }}
              />
            ))}
          </div>
          <button
            onClick={() => go(-1)}
            aria-label="Foto anterior"
            className="psite-hero-arrow absolute left-4 top-1/2 z-10 -translate-y-1/2 rounded-full p-2.5 text-white"
          >
            <ChevronLeft size={22} />
          </button>
          <button
            onClick={() => go(1)}
            aria-label="Foto siguiente"
            className="psite-hero-arrow absolute right-4 top-1/2 z-10 -translate-y-1/2 rounded-full p-2.5 text-white"
          >
            <ChevronRight size={22} />
          </button>
        </>
      )}
    </header>
  )
}
