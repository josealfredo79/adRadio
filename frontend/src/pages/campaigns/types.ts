// ─── Types ────────────────────────────────────────────────────────────────────

export interface CampaignAbTest {
  campaign_mode?: string
  has_coupon?: boolean
  coupon_description?: string
  coupon_hours?: number
  messages?: unknown[]
  enabled?: boolean
  variants?: string[]
  split?: string
  metric?: string
  audio_url?: string
  radio_script?: string
  promo_description?: string
  banner_palette?: string
  banner_layout?: string
  banner_caption?: string
  // Voces del Barrio
  consent_line?: string
  reward_coupon?: boolean
  reward_coupon_desc?: string
  reward_coupon_hours?: number
  reward_discount_type?: string
  reward_discount_value?: number
  stats_a?: { sent: number; replied: number }
  stats_b?: { sent: number; replied: number }
  stats_c?: { sent: number; replied: number }
}

export interface Campaign {
  id: string
  name: string
  type: string
  message_text: string
  status: string
  stats: Record<string, number>
  message_counts: Record<string, number>
  pause_reason?: CampaignPauseReason | null
  ab_test: CampaignAbTest
  created_at: string
  schedule?: { start_date?: string; end_date?: string } | null
}

export interface CampaignPauseReason {
  reason: string
  message: string
  retry_after?: string | null
  blocked_at?: string | null
}

export type CampaignMode =
  | 'regular' | 'banner' | 'sequence' | 'saga'
  | 'radio' | 'comunitaria' | 'capsula' | 'trivia'
  | 'historia' | 'alerta' | 'estacional' | 'voces'

// ─── Constants ────────────────────────────────────────────────────────────────

export const CAMPAIGN_TYPES = [
  { value: 'promo', label: '🎁 Promoción' },
  { value: 'reminder', label: '⏰ Recordatorio' },
  { value: 'launch', label: '🚀 Lanzamiento' },
  { value: 'event', label: '🎉 Evento' },
  { value: 'voces', label: '🎤 Voces del Barrio' },
]

export const CAMPAIGN_MODES = [
  { value: 'regular', label: '📢 Regular', desc: 'Un mensaje personalizado con nombre y ciudad' },
  { value: 'banner', label: '🖼️ Banner Visual', desc: 'Imagen personalizada con el nombre del contacto — IA genera el diseño' },
  { value: 'sequence', label: '📻 Secuencia', desc: '3 mensajes en días 1, 3 y 5 — como un programa de radio' },
  { value: 'saga', label: '🎭 Saga', desc: '4 episodios semanales — radionovela de tu negocio' },
  { value: 'radio', label: '🎙️ Cuña clásica', desc: 'Audio estilo radio AM/FM de los 80s con voz de locutor' },
  { value: 'comunitaria', label: '🌿 Radio Comunitaria', desc: 'Primero un consejo genuino, luego tu negocio' },
  { value: 'capsula', label: '💡 Cápsula del Día', desc: 'Dato sorprendente + mención natural del negocio' },
  { value: 'trivia', label: '🧠 Trivia del Día', desc: 'Pregunta curiosa + respuesta + negocio — perfecto para interacción' },
  { value: 'historia', label: '📖 Mini Historia', desc: 'Radionovela de 30s: personaje → problema → tu negocio como solución' },
  { value: 'alerta', label: '🚨 Alerta de Servicio', desc: 'Info contextual oportuna (clima, fecha) + tu negocio' },
  { value: 'estacional', label: '🗓️ Cuña Estacional', desc: 'Conecta tu negocio con el momento exacto del año' },
  { value: 'voces', label: '🎤 Voces del Barrio', desc: 'Colecciona audios reales de clientes y genera una cápsula narrativa con IA' },
]

export const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  scheduled: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-300',
  running: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-300',
  paused: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/50 dark:text-yellow-300',
  completed: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-300',
}

export const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador', scheduled: 'Programada',
  running: 'Activa', paused: 'Pausada', completed: 'Completada',
}

export const MODE_BADGE: Record<string, string> = {
  sequence: '📻 Secuencia',
  saga: '🎭 Saga',
  radio: '🎙️ Cuña de radio',
  comunitaria: '🌿 Radio Comunitaria',
  capsula: '💡 Cápsula',
  trivia: '🧠 Trivia',
  historia: '📖 Historia',
  alerta: '🚨 Alerta',
  estacional: '🗓️ Estacional',
  banner: '🖼️ Banner Visual',
  voces: '🎤 Voces del Barrio',
}

export const AUDIO_MODES: CampaignMode[] = [
  'radio', 'comunitaria', 'capsula', 'trivia', 'historia', 'alerta', 'estacional',
]

export interface Template { id: string; name: string; content: string; category: string | null }
export interface Voice { id: string; name: string; lang: string; gender: string; provider: string }
