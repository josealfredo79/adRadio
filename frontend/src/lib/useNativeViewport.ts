import { useEffect } from 'react'

// Páginas que el cliente abre en su celular (portal, página del negocio, /mi,
// QR): que se sientan app instalada (skill mobile-native). Mientras la página
// está abierta:
// - viewport-fit=cover: la página llega bajo la muesca y la barra de inicio, y
//   cada pieza se aleja con env(safe-area-inset-*) — sin esto esos valores son 0.
// - interactive-widget=resizes-content: en Android el teclado encoge la página
//   igual que en iPhone, así el chat no queda tapado.
// - theme-color: la barra de estado con el color de arriba de la página.
// Al salir se restaura todo (el panel del dueño sigue como estaba).
const NATIVE_VIEWPORT =
  'width=device-width, initial-scale=1.0, viewport-fit=cover, interactive-widget=resizes-content'

export function useNativeViewport(themeColor?: string) {
  useEffect(() => {
    const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    const theme = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    const prevViewport = viewport?.content
    const prevTheme = theme?.content
    if (viewport) viewport.content = NATIVE_VIEWPORT
    if (theme && themeColor) theme.content = themeColor
    document.documentElement.classList.add('native-viewport')
    return () => {
      if (viewport && prevViewport) viewport.content = prevViewport
      if (theme && prevTheme) theme.content = prevTheme
      document.documentElement.classList.remove('native-viewport')
    }
  }, [themeColor])
}
