/**
 * Grabadora de voz para el navegador (MediaRecorder + medidor de volumen).
 *
 * El audio se transcribe en el backend (Whisper vía Groq), no con la Web
 * Speech API: esa no existe en Firefox y en iPhone es poco confiable, y aquí
 * necesitamos que funcione en cualquier celular. Patrón tomado de Raíz
 * (Open-Hub-Tec/raiz, utils/audioRecorder.ts), validado en campo.
 */

export interface VoiceRecording {
  blob: Blob
  mimeType: string
  seconds: number
}

export interface VoiceSession {
  stop: () => Promise<VoiceRecording>
  cancel: () => void
}

// En orden de preferencia; iPhone/Safari solo graba audio/mp4.
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

export function canRecordVoice(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
}

/** Mensaje claro para cada forma en que el navegador puede negar el micrófono. */
export function micErrorMessage(err: unknown): string {
  const name = (err as { name?: string })?.name
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Tu navegador no dio permiso al micrófono. Toca el candado 🔒 junto a la dirección, permite el micrófono y vuelve a intentar.'
  }
  if (name === 'NotFoundError') return 'No encontramos un micrófono en este equipo.'
  if (name === 'NotReadableError') return 'Otra app está usando el micrófono. Ciérrala e intenta de nuevo.'
  return 'No pudimos usar el micrófono. Puedes escribirlo en su lugar.'
}

export async function startVoiceRecording(onVolume?: (level: number) => void): Promise<VoiceSession> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m)) ?? ''
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks: Blob[] = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)

  // Medidor de volumen: que el dueño VEA que lo estamos escuchando.
  let ctx: AudioContext | null = null
  let raf = 0
  if (onVolume) {
    try {
      ctx = new AudioContext()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      ctx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => {
        analyser.getByteFrequencyData(data)
        onVolume(Math.min(1, data.reduce((a, b) => a + b, 0) / data.length / 90))
        raf = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      // sin medidor no pasa nada; la grabación sigue
    }
  }

  const started = Date.now()
  recorder.start(1000)

  const cleanup = () => {
    cancelAnimationFrame(raf)
    ctx?.close().catch(() => {})
    stream.getTracks().forEach((t) => t.stop())
  }

  return {
    stop: () =>
      new Promise<VoiceRecording>((resolve) => {
        recorder.onstop = () => {
          cleanup()
          const type = recorder.mimeType || mimeType || 'audio/webm'
          resolve({ blob: new Blob(chunks, { type }), mimeType: type, seconds: Math.round((Date.now() - started) / 1000) })
        }
        recorder.stop()
      }),
    cancel: () => {
      recorder.onstop = cleanup
      if (recorder.state !== 'inactive') recorder.stop()
      else cleanup()
    },
  }
}
