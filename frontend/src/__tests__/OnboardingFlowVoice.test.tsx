import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import OnboardingFlow from '@/components/OnboardingFlow'
import { chatPalette } from '@/lib/chatLook'

const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a) },
  getApiError: (_e: unknown, fallback: string) => fallback,
  setAccessToken: vi.fn(),
}))
vi.mock('qrcode', () => ({ default: { toDataURL: () => Promise.resolve('data:image/png;base64,') } }))

let onVolume: ((level: number) => void) | undefined
const startVoiceRecording = vi.fn(async (cb?: (level: number) => void) => {
  onVolume = cb
  return {
    stop: async () => ({ blob: new Blob(['x']), mimeType: 'audio/webm', seconds: 3 }),
    cancel: vi.fn(),
  }
})
vi.mock('@/lib/voiceRecorder', () => ({
  canRecordVoice: () => true,
  startVoiceRecording: (cb?: (level: number) => void) => startVoiceRecording(cb),
}))

const PAL = chatPalette('#25D366', true)
let clock = 1_000_000

function renderFlow(voice: Record<string, unknown>) {
  return render(
    <OnboardingFlow
      pal={PAL}
      brand="#25D366"
      onBrand="#000"
      onActivity={() => {}}
      onExit={() => {}}
      voice={voice as never}
      owner={{ name: 'Barbería Don Pepe' }}
    />,
  )
}

// El dueño habla y se queda callado: la escucha se corta sola y se manda.
async function speakAndGoQuiet() {
  await waitFor(() => expect(onVolume).toBeDefined(), { timeout: 4000 })
  await act(async () => {
    onVolume!(0.6)
    clock += 100
    onVolume!(0)
    clock += 2000
    onVolume!(0)
  })
}

describe('OnboardingFlow por voz', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    onVolume = undefined
    clock = 1_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => clock)
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
      configurable: true,
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('asks one thing at a time out loud, says what is missing, and listens on its own', async () => {
    const voice = { speak: vi.fn(), unlock: vi.fn(), stop: vi.fn(), speaking: false, muted: false }
    post.mockImplementation((url: string, form: FormData) => {
      if (url !== '/public/onboarding/listen') return Promise.resolve({ data: {} })
      if (form.get('yes_no')) return Promise.resolve({ data: { transcript: 's\u00ed', answer: 'yes', profile: {} } })
      return Promise.resolve({
        data: {
          transcript: 'soy barbero',
          profile: { business_name: 'Barber\u00eda Don Pepe', business_category: 'Belleza', city: null, address: null, business_hours: null, services: [] },
        },
      })
    })
    renderFlow(voice)

    fireEvent.click(await screen.findByText('Te lo digo por voz', {}, { timeout: 4000 }))
    // Pregunta lo que falta, hablando, y luego escucha sin que toque nada.
    await waitFor(() => expect(voice.speak).toHaveBeenCalledWith(expect.stringContaining('Me faltan 4 cosas')), { timeout: 4000 })
    expect(voice.speak).toHaveBeenCalledWith(expect.stringContaining('\u00bfA qu\u00e9 te dedicas?'))
    await waitFor(() => expect(startVoiceRecording).toHaveBeenCalledTimes(1), { timeout: 4000 })

    await speakAndGoQuiet()
    // Lo que entendi\u00f3 se lo dice y pregunta si est\u00e1 bien.
    await waitFor(() => expect(voice.speak).toHaveBeenCalledWith('Anot\u00e9. Te dedicas a Belleza. \u00bfEs correcto?'), { timeout: 4000 })
    const first = post.mock.calls.find(([u]) => u === '/public/onboarding/listen')?.[1] as FormData
    expect(first.get('question')).toBe('\u00bfA qu\u00e9 te dedicas?')

    // Contesta "s\u00ed" con la voz: sigue con lo que falta.
    await waitFor(() => expect(startVoiceRecording).toHaveBeenCalledTimes(2), { timeout: 4000 })
    await speakAndGoQuiet()
    const second = post.mock.calls.filter(([u]) => u === '/public/onboarding/listen')[1][1] as FormData
    expect(second.get('yes_no')).toBe('true')
    await waitFor(() => expect(voice.speak).toHaveBeenCalledWith(expect.stringContaining('Me faltan 3 cosas')), { timeout: 4000 })
  })

  it('does not listen on its own while the voice is muted', async () => {
    const voice = { speak: vi.fn(), unlock: vi.fn(), stop: vi.fn(), speaking: false, muted: true }
    renderFlow(voice)
    fireEvent.click(await screen.findByText('Te lo digo por voz', {}, { timeout: 4000 }))
    await screen.findByLabelText('Hablar', {}, { timeout: 4000 })
    expect(startVoiceRecording).not.toHaveBeenCalled()
  })
})
