import { speakable } from '@/lib/speakable'
import { useCallback, useEffect, useRef, useState } from 'react'
import api from '@/lib/api'

// La voz de la carita. Primero la voz mexicana del servidor (/voice-setup/speak,
// más natural); si falla, la voz del propio navegador. El botón de silencio se
// recuerda en este dispositivo (en una oficina no siempre se puede hablar).
//
// iPhone/Safari bloquea audio que no arranca dentro de un toque. La respuesta
// de la carita llega segundos después del toque, así que `unlock()` se llama
// en el primer toque del usuario: "despierta" el <audio> que luego se reusa.

const MUTE_KEY = 'iaradio-voice-muted'
const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA='

// Voz de robot para la mascota (Mascot3D): la misma voz del servidor, más
// aguda (se reproduce más rápido sin conservar el tono), con un zumbido
// (modulación en anillo mezclada) y un eco metálico corto (filtro peine).
// Mismos números que las muestras hechas con ffmpeg para escoger el sonido.
const ROBOT = { rate: 1.12, ringHz: 60, ringMix: 0.3, combMs: 6, feedback: 0.5 }

/** source → [zumbido + eco metálico] → salida. Devuelve la salida. */
function robotChain(ctx: AudioContext, source: AudioNode): AudioNode {
  const dry = ctx.createGain()
  dry.gain.value = 1 - ROBOT.ringMix
  const ring = ctx.createGain()
  ring.gain.value = 0
  const osc = ctx.createOscillator()
  osc.frequency.value = ROBOT.ringHz
  const depth = ctx.createGain()
  depth.gain.value = ROBOT.ringMix
  osc.connect(depth).connect(ring.gain)
  osc.start()
  const sum = ctx.createGain()
  source.connect(dry).connect(sum)
  source.connect(ring).connect(sum)
  const delay = ctx.createDelay(0.05)
  delay.delayTime.value = ROBOT.combMs / 1000
  const fb = ctx.createGain()
  fb.gain.value = ROBOT.feedback
  sum.connect(delay).connect(fb).connect(sum)
  // Medido con la voz real: así sale al mismo volumen que sin efecto.
  const out = ctx.createGain()
  out.gain.value = 1.3
  sum.connect(out)
  return out
}

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

// `publicDemo`: la carita de la landing (sin cuenta). Ese endpoint solo
// pronuncia frases firmadas por el servidor; sin firma, voz del navegador.
// `endpoint`: otra ruta que convierte texto en voz (ej. el chat del portal
// del cliente, /public/portal/{token}/speak). `robot`: voz de robot (mascota).
export function useSpeaker({ publicDemo = false, endpoint, robot = false }: { publicDemo?: boolean; endpoint?: string; robot?: boolean } = {}) {
  const [speaking, setSpeaking] = useState(false)
  const [muted, setMutedState] = useState(readMuted)
  const audio = useRef<HTMLAudioElement | null>(null)
  const objectUrl = useRef<string | null>(null)
  const token = useRef(0)
  // Para mover los labios con la voz: un analizador conectado al <audio>.
  const analyser = useRef<AnalyserNode | null>(null)
  const levelData = useRef<Uint8Array<ArrayBuffer> | null>(null)
  const browserSpeaking = useRef(false)
  const robotRef = useRef(robot)
  robotRef.current = robot

  const stop = useCallback(() => {
    token.current += 1
    audio.current?.pause()
    browserSpeaking.current = false
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [])

  useEffect(() => () => {
    stop()
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
  }, [stop])

  // Conecta el <audio> a un analizador (una sola vez por elemento). Se hace
  // dentro de un toque: iPhone solo arranca un AudioContext así.
  const attachAnalyser = (a: HTMLAudioElement) => {
    if (analyser.current || typeof window === 'undefined') return
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return
      const ctx = new Ctx()
      const node = ctx.createAnalyser()
      node.fftSize = 512
      const source = ctx.createMediaElementSource(a)
      ;(robotRef.current ? robotChain(ctx, source) : source).connect(node)
      node.connect(ctx.destination)
      void ctx.resume().catch(() => {})
      analyser.current = node
      levelData.current = new Uint8Array(node.fftSize)
    } catch {
      // sin analizador la voz suena igual; los labios usan un ritmo genérico
    }
  }

  /** Qué tan "abierta" va la boca ahora (0–1), según la voz que suena. */
  const level = useCallback((): number => {
    const node = analyser.current
    const data = levelData.current
    const playing = !!audio.current && !audio.current.paused && !audio.current.ended
    if (playing && node && data) {
      node.getByteTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128
        sum += v * v
      }
      return Math.min(1, Math.sqrt(sum / data.length) * 4.5)
    }
    if (playing || browserSpeaking.current) {
      // Voz del navegador, o audio que empezó antes del primer toque (sin
      // analizador todavía): no se puede medir, así que un ritmo de habla creíble.
      const t = performance.now() / 1000
      return 0.35 + 0.3 * Math.abs(Math.sin(t * 9.1)) * Math.abs(Math.sin(t * 3.3 + 1))
    }
    return 0
  }, [])

  const unlock = useCallback(() => {
    if (!audio.current) audio.current = new Audio()
    const a = audio.current
    attachAnalyser(a)
    if (a.dataset.unlocked) return
    a.src = SILENT_WAV
    // play() regresa una promesa en navegadores actuales; en algunos viejos, nada.
    const started = a.play() as Promise<void> | undefined
    if (started && typeof started.then === 'function') {
      started.then(() => { a.dataset.unlocked = '1' }).catch(() => {})
    }
  }, [])

  const browserVoice = (text: string, mine: number) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      setSpeaking(false)
      return
    }
    // La voz del navegador también leería los emojis por su nombre.
    const u = new SpeechSynthesisUtterance(speakable(text))
    u.lang = 'es-MX'
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith('es'))
    if (voice) u.voice = voice
    if (robotRef.current) u.pitch = 1.6
    browserSpeaking.current = true
    u.onend = u.onerror = () => {
      browserSpeaking.current = false
      if (mine === token.current) setSpeaking(false)
    }
    window.speechSynthesis.speak(u)
  }

  const speak = useCallback(async (text: string, sig?: string) => {
    stop()
    if (!text || readMuted()) return
    const mine = token.current
    setSpeaking(true)
    try {
      if (publicDemo && !sig && !endpoint) throw new Error('frase sin firma')
      const { data } = endpoint
        ? await api.post(endpoint, { text }, { responseType: 'blob' })
        : publicDemo
          ? await api.post('/public/voice-demo/speak', { text, sig }, { responseType: 'blob' })
          : await api.post('/voice-setup/speak', { text }, { responseType: 'blob' })
      if (mine !== token.current) return
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = URL.createObjectURL(data as Blob)
      if (!audio.current) audio.current = new Audio()
      const a = audio.current
      a.src = objectUrl.current
      // Más rápido sin conservar el tono = más agudo (si no, va normal).
      a.preservesPitch = !robotRef.current
      a.playbackRate = robotRef.current ? ROBOT.rate : 1
      a.onended = () => mine === token.current && setSpeaking(false)
      await a.play()
    } catch {
      if (mine === token.current) browserVoice(text, mine)
    }
  }, [stop, publicDemo, endpoint])

  const setMuted = useCallback((value: boolean) => {
    setMutedState(value)
    try {
      localStorage.setItem(MUTE_KEY, value ? '1' : '0')
    } catch {
      // sin almacenamiento: el silencio dura solo esta visita
    }
    if (value) stop()
  }, [stop])

  return { speak, stop, unlock, speaking, muted, setMuted, level }
}
