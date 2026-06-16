import { useState } from 'react'
import api, { getApiError } from '@/lib/api'
import { CampaignMode, AUDIO_MODES } from '../types'

export function useCampaignForm() {
  const [form, setForm] = useState({ name: '', type: 'promo', message_text: '' })
  const [mode, setMode] = useState<CampaignMode>('regular')
  const [generating, setGenerating] = useState(false)
  const [variants, setVariants] = useState<string[]>([])
  const [multiMessages, setMultiMessages] = useState<string[]>([])
  const [intent, setIntent] = useState('')
  const [productDesc, setProductDesc] = useState('')
  const [protagonist, setProtagonist] = useState('María')
  const [hasCoupon, setHasCoupon] = useState(false)
  const [couponDesc, setCouponDesc] = useState('')
  const [couponHours, setCouponHours] = useState(72)
  const [radioCountry, setRadioCountry] = useState('mx')
  const [radioAudioUrl, setRadioAudioUrl] = useState('')
  const [radioScript, setRadioScript] = useState('')
  const [extraContext, setExtraContext] = useState('')
  const [businessCategory, setBusinessCategory] = useState('')
  const [radioVoiceId, setRadioVoiceId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [error, setError] = useState('')
  const [abEnabled, setAbEnabled] = useState(false)
  const [abVariants, setAbVariants] = useState<string[]>(['', ''])
  const [abSplit, setAbSplit] = useState('50/50')
  const [abMetric, setAbMetric] = useState('response')

  // Banner Visual mode
  const [bannerPromo, setBannerPromo] = useState('')
  const [bannerPalette, setBannerPalette] = useState('promo')
  const [bannerLayout, setBannerLayout] = useState('clasico')
  const [bannerCaption, setBannerCaption] = useState('')
  const [bannerPreviewUrl, setBannerPreviewUrl] = useState<string | null>(null)
  const [bannerPreviewing, setBannerPreviewing] = useState(false)

  // Voces del Barrio
  const [vocesCollectionPrompt, setVocesCollectionPrompt] = useState('')
  const [vocesStories, setVocesStories] = useState<{ id: string; transcription: string; sentiment: string; approved: boolean; contact_name?: string; created_at: string }[]>([])
  const [vocesCapsuleAudioUrl, setVocesCapsuleAudioUrl] = useState('')
  const [vocesCapsuleScript, setVocesCapsuleScript] = useState('')

  const resetForm = () => {
    setForm({ name: '', type: 'promo', message_text: '' })
    setMode('regular')
    setVariants([])
    setMultiMessages([])
    setIntent('')
    setProductDesc('')
    setProtagonist('María')
    setHasCoupon(false)
    setCouponDesc('')
    setCouponHours(72)
    setRadioCountry('mx')
    setRadioAudioUrl('')
    setRadioScript('')
    setExtraContext('')
    setBusinessCategory('')
    setRadioVoiceId('')
    setScheduledAt('')
    setError('')
    setAbEnabled(false)
    setAbVariants(['', ''])
    setAbSplit('50/50')
    setAbMetric('response')
    setBannerPromo('')
    setBannerPalette('promo')
    setBannerLayout('clasico')
    setBannerCaption('')
    setBannerPreviewUrl(null)
    setVocesCollectionPrompt('')
    setVocesStories([])
    setVocesCapsuleAudioUrl('')
    setVocesCapsuleScript('')
  }

  const generateContent = async () => {
    if (!form.name) return
    setGenerating(true)
    setError('')
    try {
      if (mode === 'regular') {
        const { data } = await api.post('/campaigns/generate-content', {
          campaign_type: form.type,
          business_name: form.name,
          intent,
        })
        setVariants(data.variants)
      } else if (mode === 'sequence') {
        const { data } = await api.post('/campaigns/generate-sequence', {
          business_name: form.name,
          intent,
          campaign_type: form.type,
        })
        setMultiMessages(data.messages)
      } else if (mode === 'saga') {
        const { data } = await api.post('/campaigns/generate-saga', {
          business_name: form.name,
          product_description: productDesc,
          protagonist_name: protagonist,
        })
        setMultiMessages(data.messages)
      } else if (AUDIO_MODES.includes(mode)) {
        const { data } = await api.post('/campaigns/generate-radio-ad', {
          business_name: form.name,
          intent,
          country: radioCountry,
          mode: mode === 'radio' ? 'classic' : mode,
          business_category: businessCategory || undefined,
          extra_context: extraContext || undefined,
          voice_id: radioVoiceId || undefined,
        })
        setRadioAudioUrl(data.audio_url)
        setRadioScript(data.script ?? '')
      }
    } catch (err: unknown) {
      setError(getApiError(err, 'Error al generar contenido'))
    } finally {
      setGenerating(false)
    }
  }

  const previewBanner = async (currentUserCategory?: string) => {
    if (!bannerPromo) return
    setBannerPreviewing(true)
    setBannerPreviewUrl(null)
    try {
      const resp = await api.post('/campaigns/banner/preview', {
        promo_description: bannerPromo,
        business_name: form.name || 'Mi negocio',
        contact_name: 'Juan',
        palette: bannerPalette,
        layout: bannerLayout,
        business_category: currentUserCategory || '',
      }, { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data)
      setBannerPreviewUrl(url)
    } catch {
      setError('Error generando preview del banner')
    } finally {
      setBannerPreviewing(false)
    }
  }

  return {
    form,
    setForm,
    mode,
    setMode,
    generating,
    setGenerating,
    variants,
    setVariants,
    multiMessages,
    setMultiMessages,
    intent,
    setIntent,
    productDesc,
    setProductDesc,
    protagonist,
    setProtagonist,
    hasCoupon,
    setHasCoupon,
    couponDesc,
    setCouponDesc,
    couponHours,
    setCouponHours,
    radioCountry,
    setRadioCountry,
    radioAudioUrl,
    setRadioAudioUrl,
    radioScript,
    setRadioScript,
    extraContext,
    setExtraContext,
    businessCategory,
    setBusinessCategory,
    radioVoiceId,
    setRadioVoiceId,
    scheduledAt,
    setScheduledAt,
    error,
    setError,
    abEnabled,
    setAbEnabled,
    abVariants,
    setAbVariants,
    abSplit,
    setAbSplit,
    abMetric,
    setAbMetric,
    bannerPromo,
    setBannerPromo,
    bannerPalette,
    setBannerPalette,
    bannerLayout,
    setBannerLayout,
    bannerCaption,
    setBannerCaption,
    bannerPreviewUrl,
    setBannerPreviewUrl,
    bannerPreviewing,
    setBannerPreviewing,
    vocesCollectionPrompt,
    setVocesCollectionPrompt,
    vocesStories,
    setVocesStories,
    vocesCapsuleAudioUrl,
    setVocesCapsuleAudioUrl,
    vocesCapsuleScript,
    setVocesCapsuleScript,
    resetForm,
    generateContent,
    previewBanner,
  }
}
