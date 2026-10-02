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

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

// `publicDemo`: la carita de la landing (sin cuenta). Ese endpoint solo
// pronuncia frases firmadas por el servidor; sin firma, voz del navegador.
export function useSpeaker({ publicDemo = false }: { publicDemo?: boolean } = {}) {
  const [speaking, setSpeaking] = useState(false)
  const [muted, setMutedState] = useState(readMuted)
  const audio = useRef<HTMLAudioElement | null>(null)
  const objectUrl = useRef<string | null>(null)
  const token = useRef(0)

  const stop = useCallback(() => {
    token.current += 1
    audio.current?.pause()
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [])

  useEffect(() => () => {
    stop()
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
  }, [stop])

  const unlock = useCallback(() => {
    if (!audio.current) audio.current = new Audio()
    const a = audio.current
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
    const u = new SpeechSynthesisUtterance(text)
    u.lang = 'es-MX'
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith('es'))
    if (voice) u.voice = voice
    u.onend = u.onerror = () => mine === token.current && setSpeaking(false)
    window.speechSynthesis.speak(u)
  }

  const speak = useCallback(async (text: string, sig?: string) => {
    stop()
    if (!text || readMuted()) return
    const mine = token.current
    setSpeaking(true)
    try {
      if (publicDemo && !sig) throw new Error('frase sin firma')
      const { data } = publicDemo
        ? await api.post('/public/voice-demo/speak', { text, sig }, { responseType: 'blob' })
        : await api.post('/voice-setup/speak', { text }, { responseType: 'blob' })
      if (mine !== token.current) return
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = URL.createObjectURL(data as Blob)
      if (!audio.current) audio.current = new Audio()
      const a = audio.current
      a.src = objectUrl.current
      a.onended = () => mine === token.current && setSpeaking(false)
      await a.play()
    } catch {
      if (mine === token.current) browserVoice(text, mine)
    }
  }, [stop, publicDemo])

  const setMuted = useCallback((value: boolean) => {
    setMutedState(value)
    try {
      localStorage.setItem(MUTE_KEY, value ? '1' : '0')
    } catch {
      // sin almacenamiento: el silencio dura solo esta visita
    }
    if (value) stop()
  }, [stop])

  return { speak, stop, unlock, speaking, muted, setMuted }
}
