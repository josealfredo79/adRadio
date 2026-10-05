import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { formatNumber } from '@/lib/utils'

// Prueba A/B de la mascota en /sitio/{slug} (backend: services/mascot_ab.py):
// 3D animada contra la misma mascota en imagen fija.
type VariantResult = {
  counts: Record<'view' | 'chat_open' | 'message' | 'confirmed' | 'whatsapp', number>
  chat_open_pct: number
  message_pct: number
  confirmed_pct: number
  whatsapp_pct: number
}
type AbResults = { since: string | null; variants: Record<'3d' | 'static', VariantResult> }

const ROWS: { key: keyof Omit<VariantResult, 'counts'>; count: keyof VariantResult['counts']; label: string }[] = [
  { key: 'chat_open_pct', count: 'chat_open', label: 'Abrieron el chat' },
  { key: 'message_pct', count: 'message', label: 'Escribieron' },
  { key: 'confirmed_pct', count: 'confirmed', label: 'Cita o pedido confirmado' },
  { key: 'whatsapp_pct', count: 'whatsapp', label: 'Se fueron a WhatsApp' },
]
// Por debajo de esto la diferencia es ruido: no se declara ganador.
const MIN_VIEWS = 300

export default function MascotAbCard() {
  const { data, isLoading, isError } = useQuery<AbResults>({
    queryKey: ['admin', 'ab', 'mascot'],
    queryFn: () => api.get('/admin/ab/mascot').then((r) => r.data),
  })
  if (isLoading) return <div className="h-40 animate-pulse rounded-xl bg-muted" />
  if (isError || !data) return null
  const a = data.variants['3d']
  const b = data.variants.static
  const enough = a.counts.view >= MIN_VIEWS && b.counts.view >= MIN_VIEWS

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <h2 className="text-base font-semibold text-foreground">Prueba A/B: mascota 3D vs. imagen fija</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Páginas públicas de los negocios{data.since ? `, desde el ${data.since}` : ''}. Cada visitante cuenta una vez
        por acción.{' '}
        {enough
          ? 'Ya hay suficientes visitas para comparar.'
          : `Faltan visitas para concluir (mínimo ${MIN_VIEWS} por variante).`}
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Visitantes que…</th>
              <th className="py-2 pr-4 font-medium">3D animada</th>
              <th className="py-2 font-medium">Imagen fija</th>
            </tr>
          </thead>
          <tbody className="text-foreground">
            <tr className="border-t border-border">
              <td className="py-2 pr-4">Vieron la página</td>
              <td className="py-2 pr-4">{formatNumber(a.counts.view)}</td>
              <td className="py-2">{formatNumber(b.counts.view)}</td>
            </tr>
            {ROWS.map((row) => (
              <tr key={row.key} className="border-t border-border">
                <td className="py-2 pr-4">{row.label}</td>
                <td className="py-2 pr-4">
                  {a[row.key]}% <span className="text-muted-foreground">({formatNumber(a.counts[row.count])})</span>
                </td>
                <td className="py-2">
                  {b[row.key]}% <span className="text-muted-foreground">({formatNumber(b.counts[row.count])})</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
