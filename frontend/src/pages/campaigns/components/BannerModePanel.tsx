interface BannerModePanelProps {
  bannerPromo: string
  setBannerPromo: (val: string) => void
  bannerPalette: string
  setBannerPalette: (val: string) => void
  bannerLayout: string
  setBannerLayout: (val: string) => void
  bannerCaption: string
  setBannerCaption: (val: string) => void
  bannerPreviewUrl: string | null
  bannerPreviewing: boolean
  onPreview: () => void
}

export function BannerModePanel({
  bannerPromo,
  setBannerPromo,
  bannerPalette,
  setBannerPalette,
  bannerLayout,
  setBannerLayout,
  bannerCaption,
  setBannerCaption,
  bannerPreviewUrl,
  bannerPreviewing,
  onPreview,
}: BannerModePanelProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">¿Qué quieres promocionar?</label>
        <textarea
          rows={2}
          placeholder="Ej: 20% de descuento esta semana en todos los productos, solo por tiempo limitado"
          value={bannerPromo}
          onChange={(e) => setBannerPromo(e.target.value)}
          className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none resize-none"
        />
        <p className="mt-1 text-xs text-indigo-700 bg-indigo-50 dark:bg-indigo-950/30 rounded-lg px-3 py-2">
          🎨 La IA generará el copy del banner y diseñará la imagen. Cada contacto recibirá su nombre dentro de la foto.
        </p>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Paleta de colores</label>
        <div className="grid grid-cols-4 gap-2">
          {[
            { key: 'promo', label: 'Azul/Rojo', colors: ['#1d3557', '#e63946'] },
            { key: 'verde', label: 'Verde', colors: ['#1b5e20', '#388e3c'] },
            { key: 'oscuro', label: 'Negro/Neón', colors: ['#121212', '#00e676'] },
            { key: 'elegante', label: 'Dorado', colors: ['#1a1a2e', '#e8c547'] },
            { key: 'naranja', label: 'Naranja', colors: ['#e65100', '#ff8f00'] },
            { key: 'morado', label: 'Morado', colors: ['#4a148c', '#7b1fa2'] },
            { key: 'azul', label: 'Azul vivo', colors: ['#0d47a1', '#1565c0'] },
            { key: 'rojo', label: 'Rojo', colors: ['#b71c1c', '#e53935'] },
          ].map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setBannerPalette(p.key)}
              className={`flex items-center gap-2 rounded-lg border-2 px-2 py-1.5 text-xs font-medium transition ${
                bannerPalette === p.key
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-border hover:border-brand-300'
              }`}
            >
              <span className="flex gap-0.5">
                {p.colors.map((c, i) => (
                  <span key={i} className="w-3 h-3 rounded-full inline-block" style={{ background: c }} />
                ))}
              </span>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Diseño del banner</label>
        <div className="grid grid-cols-4 gap-2">
          {[
            { key: 'clasico', label: 'Clásico', desc: 'Izquierda, CTA abajo' },
            { key: 'centrado', label: 'Centrado', desc: 'Todo al centro' },
            { key: 'split', label: 'Split', desc: 'Mitad y mitad' },
            { key: 'minimal', label: 'Minimal', desc: 'Elegante, sutil' },
          ].map((l) => (
            <button
              key={l.key}
              type="button"
              onClick={() => setBannerLayout(l.key)}
              className={`rounded-lg border-2 px-2 py-2 text-xs font-medium transition ${
                bannerLayout === l.key
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-border hover:border-brand-300'
              }`}
            >
              <div className="font-semibold">{l.label}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">{l.desc}</div>
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Se usa automáticamente según tu categoría de negocio si no eliges uno.</p>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Texto del mensaje (opcional)</label>
        <input
          type="text"
          placeholder="Ej: ¡Hola! Mira lo que tenemos para ti 👆"
          value={bannerCaption}
          onChange={(e) => setBannerCaption(e.target.value)}
          className="w-full rounded-lg border border-border bg-background text-foreground px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
        />
        <p className="mt-1 text-xs text-muted-foreground">Este texto se envía junto con la imagen. Si lo dejas vacío se genera automáticamente.</p>
      </div>

      {/* Preview */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={onPreview}
          disabled={!bannerPromo || bannerPreviewing}
          className="flex items-center gap-2 rounded-lg border border-indigo-300 bg-indigo-50 dark:bg-indigo-950/30 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 transition"
        >
          {bannerPreviewing ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
              Generando preview...
            </>
          ) : (
            <>🖼️ Ver preview del banner</>
          )}
        </button>
        {bannerPreviewUrl && (
          <div className="rounded-xl overflow-hidden border border-border shadow-sm">
            <img src={bannerPreviewUrl} alt="Preview banner" className="w-full max-h-80 object-cover" />
            <p className="text-center text-xs text-muted-foreground py-2 bg-muted">
              Preview con nombre "Juan" — cada contacto verá su propio nombre
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
