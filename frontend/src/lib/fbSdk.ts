export interface FbAuthResponse {
  authResponse?: { code?: string; accessToken?: string }
  status?: string
  error?: { message?: string }
}

export interface EmbeddedSignupResult {
  code: string
  wabaId: string
  phoneNumberId: string
}

export interface FbLoginOptions {
  config_id: string
  response_type: 'code'
  override_default_response_type: boolean
  extras: {
    feature: string
    sessionInfoVersion?: number
    setup?: Record<string, unknown>
  }
}

declare global {
  interface Window {
    FB?: {
      init: (params: { appId: string; version: string; cookie: boolean; xfbml: boolean }) => void
      login: (callback: (response: FbAuthResponse) => void, options?: FbLoginOptions) => void
      logout: (callback?: () => void) => void
      getLoginStatus: (callback: (response: FbAuthResponse) => void) => void
      Event?: { subscribe: (event: string, handler: (payload: unknown) => void) => void }
      AppEvents: { logPageView: () => void }
    }
    fbAsyncInit?: () => void
    FB_SIGNUP_RESULT?: unknown
  }
}

let _loadPromise: Promise<void> | null = null

function loadFbSdk(): Promise<void> {
  if (_loadPromise) return _loadPromise
  _loadPromise = new Promise((resolve, reject) => {
    if (window.FB) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://connect.facebook.net/en_US/sdk.js'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => {
      _loadPromise = null
      reject(new Error('No se pudo cargar el SDK de Facebook'))
    }
    document.head.appendChild(script)
  })
  return _loadPromise
}

export async function initFbSdk(appId: string): Promise<void> {
  await loadFbSdk()
  if (window.FB) {
    window.FB.init({ appId, version: 'v21.0', cookie: true, xfbml: true })
  }
}

export function launchEmbeddedSignup(appId: string, configId: string): Promise<EmbeddedSignupResult> {
  return new Promise((resolve, reject) => {
    loadFbSdk()
      .then(() => {
        if (!window.FB) throw new Error('SDK de Facebook no disponible')
        window.FB.init({ appId, version: 'v21.0', cookie: true, xfbml: true })

        let signup: EmbeddedSignupResult | null = null

        // Meta posts the selected WABA + phone number via the sessionInfo
        // message before resolving the login callback — capture it here.
        const handleMessage = (raw: unknown) => {
          let payload: unknown = raw
          if (typeof raw === 'string') {
            try {
              payload = JSON.parse(raw)
            } catch {
              return
            }
          }
          const data = (payload ?? {}) as {
            type?: string
            event?: string
            data?: { waba_id?: string | number; phone_number_id?: string | number }
          }
          if (data.type !== 'WA_EMBEDDED_SIGNUP') return
          if (data.event === 'FINISH' && data.data) {
            signup = {
              code: '',
              wabaId: String(data.data.waba_id ?? ''),
              phoneNumberId: String(data.data.phone_number_id ?? ''),
            }
          }
        }
        window.FB.Event?.subscribe('message', handleMessage)

        window.FB.login(
          (response) => {
            if (response.status === 'not_authorized') {
              reject(new Error('Cancelaste la autorización con Meta'))
              return
            }
            if (response.error?.message) {
              reject(new Error(response.error.message))
              return
            }
            const code = response.authResponse?.code
            if (!code) {
              reject(new Error('Meta no devolvió el código de autorización'))
              return
            }
            if (signup) {
              resolve({ ...signup, code })
            } else {
              // Fallback: some flows resolve without the sessionInfo message.
              resolve({ code, wabaId: '', phoneNumberId: '' })
            }
          },
          {
            config_id: configId,
            response_type: 'code',
            override_default_response_type: true,
            extras: { feature: 'whatsapp_embedded_signup', sessionInfoVersion: 2 },
          },
        )
      })
      .catch(reject)
  })
}
