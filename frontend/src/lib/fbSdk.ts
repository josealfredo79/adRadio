export interface FbAuthResponse {
  authResponse?: { code?: string; accessToken?: string }
  status?: string
  error?: { message?: string }
}

export interface EmbeddedSignupResult {
  code: string
  wabaId: string
  phoneNumberId: string
  /** El negocio conectó el número de su app WhatsApp Business (coexistencia). */
  coexistence: boolean
}

export interface FbLoginOptions {
  config_id: string
  response_type: 'code'
  override_default_response_type: boolean
  // Embedded Signup v4: los productos se eligen en la configuración de
  // "Inicio de sesión con Facebook para empresas", no aquí.
  extras: {
    setup: Record<string, unknown>
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
        // Set when Meta reports the customer quit or hit an error inside the popup.
        let abortMessage: string | null = null

        // Meta posts the selected WABA + phone number (or why the flow ended)
        // via the sessionInfo message before resolving the login callback.
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
            data?: {
              waba_id?: string | number
              phone_number_id?: string | number
              current_step?: string
              error_message?: string
            }
          }
          if (data.type !== 'WA_EMBEDDED_SIGNUP') return
          const finished = ['FINISH', 'FINISH_ONLY_WABA', 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING']
          if (data.event && finished.includes(data.event) && data.data) {
            // FINISH_ONLY_WABA y la coexistencia (FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING)
            // solo traen el waba_id; el servidor busca el número con el token.
            signup = {
              code: '',
              wabaId: String(data.data.waba_id ?? ''),
              phoneNumberId: String(data.data.phone_number_id ?? ''),
              coexistence: data.event === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING',
            }
          } else if (data.event === 'CANCEL') {
            abortMessage = data.data?.error_message
              ? `Meta reportó un error: ${data.data.error_message}`
              : 'Cerraste la ventana de Meta antes de terminar. Vuelve a intentarlo cuando quieras.'
          }
        }
        window.FB.Event?.subscribe('message', handleMessage)
        // La guía oficial (v4) manda el resultado por window.postMessage desde
        // facebook.com; sin escucharlo, una coexistencia podía tratarse como
        // número nuevo.
        const onWindowMessage = (event: MessageEvent) => {
          if (typeof event.origin === 'string' && event.origin.endsWith('facebook.com')) handleMessage(event.data)
        }
        window.addEventListener('message', onWindowMessage)

        window.FB.login(
          (response) => {
            window.removeEventListener('message', onWindowMessage)
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
              reject(new Error(abortMessage ?? 'Meta no devolvió el código de autorización'))
              return
            }
            if (signup) {
              resolve({ ...signup, code })
            } else {
              // Some flows resolve without the sessionInfo message; the
              // server reads the WABA and number from the token.
              resolve({ code, wabaId: '', phoneNumberId: '', coexistence: false })
            }
          },
          {
            config_id: configId,
            response_type: 'code',
            override_default_response_type: true,
            // v4: la v2 (feature + sessionInfoVersion) se retira el 15-oct-2026.
            extras: { setup: {} },
          },
        )
      })
      .catch(reject)
  })
}
