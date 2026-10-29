/** Cuándo sale una promo mandada de noche o en domingo (el envío espera al
 * horario humano, 8 am a 9 pm de lunes a sábado): "mañana a las 8:00 a.m.". */
export function startsAtLabel(iso: string, now: Date = new Date()): string {
  const tz = 'America/Mexico_City'
  const day = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: tz })
  const at = new Date(iso)
  const hour = at.toLocaleTimeString('es-MX', { timeZone: tz, hour: 'numeric', minute: '2-digit' })
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  const when = day(at) === day(now) ? 'hoy'
    : day(at) === day(tomorrow) ? 'mañana'
    : `el ${at.toLocaleDateString('es-MX', { timeZone: tz, weekday: 'long' })}`
  return `${when} a las ${hour}`
}
