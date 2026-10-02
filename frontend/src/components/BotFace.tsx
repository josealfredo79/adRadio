// La carita de IaRadio: el personaje con el que el dueño "platica" al
// configurar su bot. Una cara redonda con la antena de radio de la marca.
// Sin imágenes ni librerías: SVG + CSS, así pesa casi nada y se ve nítida.
//
// Estados (como una persona en una plática):
//   idle      sonríe, parpadea y flota suave — "aquí estoy"
//   listening ojos atentos; la boca y las ondas siguen tu voz — "te oigo"
//   thinking  mira hacia arriba con puntitos — "déjame pensar"
//   speaking  mueve la boca y la antena transmite — "te estoy hablando"
//   happy     ojos sonrientes, cachetes rosas — "¡quedó!"
//   confused  ceja levantada, boca chueca — "no te entendí"

export type FaceMood = 'idle' | 'listening' | 'thinking' | 'speaking' | 'happy' | 'confused'

const STYLES = `
.bf-float { animation: bf-float 3.2s ease-in-out infinite; transform-origin: 50% 60%; }
@keyframes bf-float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-4px) } }
.bf-blink { animation: bf-blink 4.6s infinite; transform-box: fill-box; transform-origin: center; }
@keyframes bf-blink { 0%,94%,100% { transform: scaleY(1) } 96% { transform: scaleY(0.1) } }
.bf-talk { animation: bf-talk 0.32s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center top; }
@keyframes bf-talk { from { transform: scaleY(0.35) } to { transform: scaleY(1.15) } }
.bf-wave { opacity: 0; animation: bf-wave 1.4s ease-out infinite; }
.bf-wave-2 { animation-delay: 0.45s; }
@keyframes bf-wave { 0% { opacity: 0.9 } 100% { opacity: 0 } }
.bf-dot { animation: bf-dot 1.2s ease-in-out infinite; }
.bf-dot-2 { animation-delay: 0.2s } .bf-dot-3 { animation-delay: 0.4s }
@keyframes bf-dot { 0%,100% { opacity: .25; transform: translateY(0) } 50% { opacity: 1; transform: translateY(-3px) } }
.bf-tilt { animation: bf-tilt 2.4s ease-in-out infinite; transform-origin: 50% 70%; }
@keyframes bf-tilt { 0%,100% { transform: rotate(-3deg) } 50% { transform: rotate(3deg) } }
.bf-pop { animation: bf-pop .5s cubic-bezier(.34,1.56,.64,1); transform-origin: 50% 60%; }
@keyframes bf-pop { from { transform: scale(.85) } to { transform: scale(1) } }
@media (prefers-reduced-motion: reduce) {
  .bf-float, .bf-blink, .bf-talk, .bf-wave, .bf-dot, .bf-tilt, .bf-pop { animation: none !important; }
  .bf-wave { opacity: .6; }
}
`

export default function BotFace({ mood, volume = 0, size = 168 }: { mood: FaceMood; volume?: number; size?: number }) {
  const broadcasting = mood === 'speaking' || mood === 'listening'
  const bodyClass =
    mood === 'thinking' || mood === 'confused' ? 'bf-tilt' : mood === 'happy' ? 'bf-pop' : 'bf-float'
  // Ojos: dirección de la mirada según el estado.
  const look = mood === 'thinking' ? { x: 4, y: -5 } : mood === 'listening' ? { x: 0, y: 1 } : { x: 0, y: 0 }
  const eyeRy = mood === 'listening' ? 15 : 13

  return (
    <svg
      viewBox="0 0 200 210"
      width={size}
      height={size * 1.05}
      role="img"
      aria-label={LABELS[mood]}
      className="select-none overflow-visible"
    >
      <style>{STYLES}</style>
      <defs>
        <linearGradient id="bf-head" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#6d28d9" />
        </linearGradient>
      </defs>

      <g className={bodyClass} key={mood}>
        {/* Antena de radio — la "i" de IaRadio */}
        <line x1="100" y1="44" x2="100" y2="20" stroke="#6d28d9" strokeWidth="5" strokeLinecap="round" />
        <circle cx="100" cy="16" r="8" fill="#f97316" />
        {broadcasting && (
          <g fill="none" stroke="#f97316" strokeWidth="4" strokeLinecap="round">
            <path className="bf-wave" d="M82 8 Q78 16 82 24" />
            <path className="bf-wave" d="M118 8 Q122 16 118 24" />
            <path className="bf-wave bf-wave-2" d="M72 2 Q65 16 72 30" />
            <path className="bf-wave bf-wave-2" d="M128 2 Q135 16 128 30" />
          </g>
        )}

        {/* Cabeza */}
        <circle cx="100" cy="120" r="78" fill="url(#bf-head)" />
        <ellipse cx="78" cy="78" rx="26" ry="13" fill="white" opacity="0.18" />

        {/* Cachetes */}
        {(mood === 'happy' || mood === 'speaking' || mood === 'idle') && (
          <g fill="#fb7185" opacity={mood === 'happy' ? 0.7 : 0.35}>
            <ellipse cx="50" cy="138" rx="12" ry="7" />
            <ellipse cx="150" cy="138" rx="12" ry="7" />
          </g>
        )}

        {/* Ojos */}
        {mood === 'happy' ? (
          <g fill="none" stroke="white" strokeWidth="7" strokeLinecap="round">
            <path d="M58 112 Q72 96 86 112" />
            <path d="M114 112 Q128 96 142 112" />
          </g>
        ) : (
          <g>
            <g className="bf-blink">
              <ellipse cx="72" cy="110" rx="13" ry={eyeRy} fill="white" />
              <ellipse cx="128" cy="110" rx="13" ry={eyeRy} fill="white" />
            </g>
            <circle cx={74 + look.x} cy={112 + look.y} r="6.5" fill="#1e1b4b" />
            <circle cx={130 + look.x} cy={112 + look.y} r="6.5" fill="#1e1b4b" />
            <circle cx={76 + look.x} cy={109 + look.y} r="2" fill="white" />
            <circle cx={132 + look.x} cy={109 + look.y} r="2" fill="white" />
          </g>
        )}

        {/* Cejas */}
        {mood === 'confused' && (
          <g stroke="white" strokeWidth="5" strokeLinecap="round">
            <line x1="60" y1="88" x2="84" y2="92" />
            <line x1="116" y1="84" x2="142" y2="78" />
          </g>
        )}

        {/* Boca */}
        <Mouth mood={mood} volume={volume} />

        {/* Puntitos de "pensando" */}
        {mood === 'thinking' && (
          <g fill="white">
            <circle className="bf-dot" cx="152" cy="50" r="5" />
            <circle className="bf-dot bf-dot-2" cx="166" cy="40" r="6" />
            <circle className="bf-dot bf-dot-3" cx="182" cy="28" r="7" />
          </g>
        )}
      </g>
    </svg>
  )
}

const LABELS: Record<FaceMood, string> = {
  idle: 'Asistente sonriendo',
  listening: 'Asistente escuchando',
  thinking: 'Asistente pensando',
  speaking: 'Asistente hablando',
  happy: 'Asistente contento',
  confused: 'Asistente con duda',
}

function Mouth({ mood, volume }: { mood: FaceMood; volume: number }) {
  switch (mood) {
    case 'listening': {
      // La boquita sigue el volumen de tu voz: ves que te está oyendo.
      const ry = 4 + Math.min(1, volume) * 12
      return <ellipse cx="100" cy="152" rx="11" ry={ry} fill="#1e1b4b" />
    }
    case 'speaking':
      return (
        <g className="bf-talk">
          <ellipse cx="100" cy="150" rx="18" ry="11" fill="#1e1b4b" />
          <ellipse cx="100" cy="156" rx="9" ry="4" fill="#fb7185" />
        </g>
      )
    case 'thinking':
      return <path d="M86 152 L114 152" stroke="#1e1b4b" strokeWidth="6" strokeLinecap="round" />
    case 'confused':
      return <path d="M80 154 Q90 146 100 154 T120 152" fill="none" stroke="#1e1b4b" strokeWidth="6" strokeLinecap="round" />
    case 'happy':
      return <path d="M70 142 Q100 178 130 142 Z" fill="#1e1b4b" stroke="#1e1b4b" strokeWidth="4" strokeLinejoin="round" />
    default:
      return <path d="M76 144 Q100 166 124 144" fill="none" stroke="#1e1b4b" strokeWidth="6" strokeLinecap="round" />
  }
}
