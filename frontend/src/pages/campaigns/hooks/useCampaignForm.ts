import { useReducer, useCallback, useEffect } from 'react'
import api, { getApiError } from '@/lib/api'
import { CampaignMode, AUDIO_MODES } from '../types'

// ─── State Shape ──────────────────────────────────────────────────────────────

interface FormState {
  name: string
  type: string
  message_text: string
}

interface AudioState {
  radioCountry: string
  radioAudioUrl: string
  radioScript: string
  radioVoiceId: string
  extraContext: string
  businessCategory: string
  includeSfx: boolean
}

interface BannerState {
  bannerPromo: string
  bannerPalette: string
  bannerLayout: string
  bannerCaption: string
  bannerPreviewUrl: string | null
  bannerPreviewing: boolean
}

interface VocesState {
  vocesCollectionPrompt: string
  vocesStories: {
    id: string
    transcription: string
    sentiment: string
    approved: boolean
    contact_name?: string
    created_at: string
  }[]
  vocesCapsuleAudioUrl: string
  vocesCapsuleScript: string
}

interface AbState {
  abEnabled: boolean
  abVariants: string[]
  abSplit: string
  abMetric: string
}

interface CampaignFormState {
  form: FormState
  mode: CampaignMode
  generating: boolean
  variants: string[]
  multiMessages: string[]
  intent: string
  productDesc: string
  protagonist: string
  hasCoupon: boolean
  couponDesc: string
  couponHours: number
  scheduledAt: string
  error: string
  audio: AudioState
  banner: BannerState
  voces: VocesState
  ab: AbState
}

// ─── Initial State ────────────────────────────────────────────────────────────

const INITIAL_STATE: CampaignFormState = {
  form: { name: '', type: 'promo', message_text: '' },
  mode: 'regular',
  generating: false,
  variants: [],
  multiMessages: [],
  intent: '',
  productDesc: '',
  protagonist: 'María',
  hasCoupon: false,
  couponDesc: '',
  couponHours: 72,
  scheduledAt: '',
  error: '',
  audio: {
    radioCountry: 'mx',
    radioAudioUrl: '',
    radioScript: '',
    radioVoiceId: '',
    extraContext: '',
    businessCategory: '',
    includeSfx: false,
  },
  banner: {
    bannerPromo: '',
    bannerPalette: 'promo',
    bannerLayout: 'clasico',
    bannerCaption: '',
    bannerPreviewUrl: null,
    bannerPreviewing: false,
  },
  voces: {
    vocesCollectionPrompt: '',
    vocesStories: [],
    vocesCapsuleAudioUrl: '',
    vocesCapsuleScript: '',
  },
  ab: {
    abEnabled: false,
    abVariants: ['', ''],
    abSplit: '50/50',
    abMetric: 'response',
  },
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

type Action =
  | { type: 'SET_FORM'; payload: Partial<FormState> }
  | { type: 'SET_MODE'; payload: CampaignMode }
  | { type: 'SET_GENERATING'; payload: boolean }
  | { type: 'SET_VARIANTS'; payload: string[] }
  | { type: 'SET_MULTI_MESSAGES'; payload: string[] }
  | { type: 'SET_INTENT'; payload: string }
  | { type: 'SET_PRODUCT_DESC'; payload: string }
  | { type: 'SET_PROTAGONIST'; payload: string }
  | { type: 'SET_HAS_COUPON'; payload: boolean }
  | { type: 'SET_COUPON_DESC'; payload: string }
  | { type: 'SET_COUPON_HOURS'; payload: number }
  | { type: 'SET_SCHEDULED_AT'; payload: string }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'SET_AUDIO'; payload: Partial<AudioState> }
  | { type: 'SET_BANNER'; payload: Partial<BannerState> }
  | { type: 'SET_VOCES'; payload: Partial<VocesState> }
  | { type: 'SET_AB'; payload: Partial<AbState> }
  | { type: 'RESET' }

function reducer(state: CampaignFormState, action: Action): CampaignFormState {
  switch (action.type) {
    case 'SET_FORM': return { ...state, form: { ...state.form, ...action.payload } }
    case 'SET_MODE': return { ...state, mode: action.payload }
    case 'SET_GENERATING': return { ...state, generating: action.payload }
    case 'SET_VARIANTS': return { ...state, variants: action.payload }
    case 'SET_MULTI_MESSAGES': return { ...state, multiMessages: action.payload }
    case 'SET_INTENT': return { ...state, intent: action.payload }
    case 'SET_PRODUCT_DESC': return { ...state, productDesc: action.payload }
    case 'SET_PROTAGONIST': return { ...state, protagonist: action.payload }
    case 'SET_HAS_COUPON': return { ...state, hasCoupon: action.payload }
    case 'SET_COUPON_DESC': return { ...state, couponDesc: action.payload }
    case 'SET_COUPON_HOURS': return { ...state, couponHours: action.payload }
    case 'SET_SCHEDULED_AT': return { ...state, scheduledAt: action.payload }
    case 'SET_ERROR': return { ...state, error: action.payload }
    case 'SET_AUDIO': return { ...state, audio: { ...state.audio, ...action.payload } }
    case 'SET_BANNER': return { ...state, banner: { ...state.banner, ...action.payload } }
    case 'SET_VOCES': return { ...state, voces: { ...state.voces, ...action.payload } }
    case 'SET_AB': return { ...state, ab: { ...state.ab, ...action.payload } }
    case 'RESET': return INITIAL_STATE
    default: return state
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useCampaignForm() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)

  // Cleanup banner object URL on unmount to prevent memory leak
  useEffect(() => {
    return () => {
      if (state.banner.bannerPreviewUrl) {
        URL.revokeObjectURL(state.banner.bannerPreviewUrl)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const resetForm = useCallback(() => dispatch({ type: 'RESET' }), [])

  const generateContent = useCallback(async () => {
    if (!state.form.name) return
    dispatch({ type: 'SET_GENERATING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: '' })
    try {
      const { mode, form, intent, productDesc, protagonist, audio } = state
      if (mode === 'regular') {
        const { data } = await api.post('/campaigns/generate-content', {
          campaign_type: form.type,
          business_name: form.name,
          intent,
        })
        dispatch({ type: 'SET_VARIANTS', payload: data.variants })
      } else if (mode === 'sequence') {
        const { data } = await api.post('/campaigns/generate-sequence', {
          business_name: form.name,
          intent,
          campaign_type: form.type,
        })
        dispatch({ type: 'SET_MULTI_MESSAGES', payload: data.messages })
      } else if (mode === 'saga') {
        const { data } = await api.post('/campaigns/generate-saga', {
          business_name: form.name,
          product_description: productDesc,
          protagonist_name: protagonist,
        })
        dispatch({ type: 'SET_MULTI_MESSAGES', payload: data.messages })
      } else if (AUDIO_MODES.includes(mode)) {
        const { data } = await api.post('/campaigns/generate-radio-ad', {
          business_name: form.name,
          intent,
          country: audio.radioCountry,
          mode: mode === 'radio' ? 'classic' : mode,
          business_category: audio.businessCategory || undefined,
          extra_context: audio.extraContext || undefined,
          voice_id: audio.radioVoiceId || undefined,
          include_sfx: audio.includeSfx,
        }, { timeout: 90000 })
        dispatch({ type: 'SET_AUDIO', payload: { radioAudioUrl: data.audio_url, radioScript: data.script ?? '' } })
      }
    } catch (err: unknown) {
      dispatch({ type: 'SET_ERROR', payload: getApiError(err, 'Error al generar contenido') })
    } finally {
      dispatch({ type: 'SET_GENERATING', payload: false })
    }
  }, [state])

  const previewBanner = useCallback(async (currentUserCategory?: string) => {
    if (!state.banner.bannerPromo) return
    // Revoke previous object URL before creating new one
    if (state.banner.bannerPreviewUrl) {
      URL.revokeObjectURL(state.banner.bannerPreviewUrl)
    }
    dispatch({ type: 'SET_BANNER', payload: { bannerPreviewing: true, bannerPreviewUrl: null } })
    try {
      const resp = await api.post('/campaigns/banner/preview', {
        promo_description: state.banner.bannerPromo,
        business_name: state.form.name || 'Mi negocio',
        contact_name: 'Juan',
        palette: state.banner.bannerPalette,
        layout: state.banner.bannerLayout,
        business_category: currentUserCategory || '',
      }, { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data)
      dispatch({ type: 'SET_BANNER', payload: { bannerPreviewUrl: url } })
    } catch {
      dispatch({ type: 'SET_ERROR', payload: 'Error generando preview del banner' })
    } finally {
      dispatch({ type: 'SET_BANNER', payload: { bannerPreviewing: false } })
    }
  }, [state.banner, state.form.name])

  // ─── Flatten state for backward-compatible API ────────────────────────────
  return {
    // form
    form: state.form,
    setForm: (payload: Partial<FormState>) => dispatch({ type: 'SET_FORM', payload }),
    // mode
    mode: state.mode,
    setMode: (payload: CampaignMode) => dispatch({ type: 'SET_MODE', payload }),
    // generating
    generating: state.generating,
    setGenerating: (payload: boolean) => dispatch({ type: 'SET_GENERATING', payload }),
    // variants / messages
    variants: state.variants,
    setVariants: (payload: string[]) => dispatch({ type: 'SET_VARIANTS', payload }),
    multiMessages: state.multiMessages,
    setMultiMessages: (payload: string[]) => dispatch({ type: 'SET_MULTI_MESSAGES', payload }),
    // text inputs
    intent: state.intent,
    setIntent: (payload: string) => dispatch({ type: 'SET_INTENT', payload }),
    productDesc: state.productDesc,
    setProductDesc: (payload: string) => dispatch({ type: 'SET_PRODUCT_DESC', payload }),
    protagonist: state.protagonist,
    setProtagonist: (payload: string) => dispatch({ type: 'SET_PROTAGONIST', payload }),
    // coupon
    hasCoupon: state.hasCoupon,
    setHasCoupon: (payload: boolean) => dispatch({ type: 'SET_HAS_COUPON', payload }),
    couponDesc: state.couponDesc,
    setCouponDesc: (payload: string) => dispatch({ type: 'SET_COUPON_DESC', payload }),
    couponHours: state.couponHours,
    setCouponHours: (payload: number) => dispatch({ type: 'SET_COUPON_HOURS', payload }),
    // schedule
    scheduledAt: state.scheduledAt,
    setScheduledAt: (payload: string) => dispatch({ type: 'SET_SCHEDULED_AT', payload }),
    // error
    error: state.error,
    setError: (payload: string) => dispatch({ type: 'SET_ERROR', payload }),
    // audio (flat for consumers)
    radioCountry: state.audio.radioCountry,
    setRadioCountry: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { radioCountry: payload } }),
    radioAudioUrl: state.audio.radioAudioUrl,
    setRadioAudioUrl: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { radioAudioUrl: payload } }),
    radioScript: state.audio.radioScript,
    setRadioScript: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { radioScript: payload } }),
    radioVoiceId: state.audio.radioVoiceId,
    setRadioVoiceId: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { radioVoiceId: payload } }),
    extraContext: state.audio.extraContext,
    setExtraContext: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { extraContext: payload } }),
    businessCategory: state.audio.businessCategory,
    setBusinessCategory: (payload: string) => dispatch({ type: 'SET_AUDIO', payload: { businessCategory: payload } }),
    includeSfx: state.audio.includeSfx,
    setIncludeSfx: (payload: boolean) => dispatch({ type: 'SET_AUDIO', payload: { includeSfx: payload } }),
    // banner (flat)
    bannerPromo: state.banner.bannerPromo,
    setBannerPromo: (payload: string) => dispatch({ type: 'SET_BANNER', payload: { bannerPromo: payload } }),
    bannerPalette: state.banner.bannerPalette,
    setBannerPalette: (payload: string) => dispatch({ type: 'SET_BANNER', payload: { bannerPalette: payload } }),
    bannerLayout: state.banner.bannerLayout,
    setBannerLayout: (payload: string) => dispatch({ type: 'SET_BANNER', payload: { bannerLayout: payload } }),
    bannerCaption: state.banner.bannerCaption,
    setBannerCaption: (payload: string) => dispatch({ type: 'SET_BANNER', payload: { bannerCaption: payload } }),
    bannerPreviewUrl: state.banner.bannerPreviewUrl,
    setBannerPreviewUrl: (payload: string | null) => dispatch({ type: 'SET_BANNER', payload: { bannerPreviewUrl: payload } }),
    bannerPreviewing: state.banner.bannerPreviewing,
    setBannerPreviewing: (payload: boolean) => dispatch({ type: 'SET_BANNER', payload: { bannerPreviewing: payload } }),
    // voces (flat)
    vocesCollectionPrompt: state.voces.vocesCollectionPrompt,
    setVocesCollectionPrompt: (payload: string) => dispatch({ type: 'SET_VOCES', payload: { vocesCollectionPrompt: payload } }),
    vocesStories: state.voces.vocesStories,
    setVocesStories: (payload: VocesState['vocesStories']) => dispatch({ type: 'SET_VOCES', payload: { vocesStories: payload } }),
    vocesCapsuleAudioUrl: state.voces.vocesCapsuleAudioUrl,
    setVocesCapsuleAudioUrl: (payload: string) => dispatch({ type: 'SET_VOCES', payload: { vocesCapsuleAudioUrl: payload } }),
    vocesCapsuleScript: state.voces.vocesCapsuleScript,
    setVocesCapsuleScript: (payload: string) => dispatch({ type: 'SET_VOCES', payload: { vocesCapsuleScript: payload } }),
    // ab (flat)
    abEnabled: state.ab.abEnabled,
    setAbEnabled: (payload: boolean) => dispatch({ type: 'SET_AB', payload: { abEnabled: payload } }),
    abVariants: state.ab.abVariants,
    setAbVariants: (payload: string[]) => dispatch({ type: 'SET_AB', payload: { abVariants: payload } }),
    abSplit: state.ab.abSplit,
    setAbSplit: (payload: string) => dispatch({ type: 'SET_AB', payload: { abSplit: payload } }),
    abMetric: state.ab.abMetric,
    setAbMetric: (payload: string) => dispatch({ type: 'SET_AB', payload: { abMetric: payload } }),
    // actions
    resetForm,
    generateContent,
    previewBanner,
  }
}
