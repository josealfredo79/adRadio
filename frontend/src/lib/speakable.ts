// Lo que dice en voz alta el agente: sin emojis ("cohete", "cara sonriente"),
// links ni marcas de formato. El servidor limpia igual (services/speech_text.py);
// esto cubre la voz del navegador cuando la del servidor falla.
const URL_RE = /https?:\/\/\S+/g
const EMOJI_RE = /(?:\p{Extended_Pictographic}|\p{Emoji_Modifier}|\p{Regional_Indicator}|\u{FE0E}|\u{FE0F}|\u{200D}|\u{20E3})+/gu
const MARKS_RE = /[*_~`#>|]+/g

export function speakable(text: string): string {
  return text.replace(URL_RE, '').replace(EMOJI_RE, ' ').replace(MARKS_RE, '').replace(/\s+/g, ' ').trim()
}
