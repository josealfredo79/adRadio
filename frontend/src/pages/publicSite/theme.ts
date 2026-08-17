export interface SiteThemeDef {
  name: string
  bg: string
  text: string
  muted: string
  cardBg: string
  cardBorder: string
}

export const SITE_THEMES: Record<string, SiteThemeDef> = {
  medianoche: { name: 'Medianoche', bg: '#06060f', text: '#ffffff', muted: 'rgba(255,255,255,.65)', cardBg: 'rgba(255,255,255,.05)', cardBorder: 'rgba(255,255,255,.1)' },
  pizarra: { name: 'Pizarra', bg: '#0f172a', text: '#f1f5f9', muted: 'rgba(241,245,249,.65)', cardBg: 'rgba(255,255,255,.04)', cardBorder: 'rgba(255,255,255,.08)' },
  esmeralda: { name: 'Esmeralda', bg: '#06120d', text: '#eafff5', muted: 'rgba(234,255,245,.65)', cardBg: 'rgba(255,255,255,.05)', cardBorder: 'rgba(255,255,255,.1)' },
  claro: { name: 'Claro', bg: '#f8fafc', text: '#0f172a', muted: '#64748b', cardBg: '#ffffff', cardBorder: '#e2e8f0' },
  crema: { name: 'Crema', bg: '#fdf6ec', text: '#2b2118', muted: '#8a7862', cardBg: '#ffffff', cardBorder: '#eee0cc' },
}

export function getSiteTheme(key: string): SiteThemeDef {
  return SITE_THEMES[key] ?? SITE_THEMES.medianoche
}

export function isDarkTheme(theme: SiteThemeDef): boolean {
  return theme.cardBg.trim().startsWith('rgba')
}
