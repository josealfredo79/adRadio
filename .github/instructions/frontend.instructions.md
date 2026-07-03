---
applyTo: "frontend/**"
---

# Frontend — Convenciones IaRadio

## Reglas fundamentales

### Estado del servidor: TanStack Query v5 SIEMPRE
```tsx
// ✅ Correcto — React Query para datos del servidor
const { data: campaigns, isLoading } = useQuery({
  queryKey: ['campaigns'],
  queryFn: () => api.get('/campaigns').then(r => r.data),
})

// ❌ NUNCA — useEffect + fetch
useEffect(() => {
  fetch('/api/campaigns').then(r => r.json()).then(setData)
}, [])
```

### Mutations con invalidación de cache
```tsx
const mutation = useMutation({
  mutationFn: (data: CampaignCreate) => api.post('/campaigns', data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['campaigns'] })
    toast({ title: 'Campaña creada' })
  },
})
```

### Formularios: react-hook-form + Zod
```tsx
const schema = z.object({
  name: z.string().min(1, 'Nombre requerido'),
  phone: z.string().regex(/^\+[1-9]\d{7,14}$/, 'Formato: +521234567890'),
})

const form = useForm<z.infer<typeof schema>>({
  resolver: zodResolver(schema),
})
```

### Estilos: Tailwind directo — sin CSS modules
```tsx
// ✅ Correcto
<div className="flex items-center gap-4 p-6 rounded-lg bg-card border">

// ❌ No usar
import styles from './Component.module.css'
```

### Componentes UI: solo @radix-ui + shadcn
```tsx
// ✅ Usar primitivos disponibles en el proyecto
import { Dialog, DialogContent, DialogHeader } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem } from '@/components/ui/select'

// ❌ NO instalar nuevas librerías UI (MUI, Ant Design, Chakra, etc.)
```

## Estructura de una nueva página

```tsx
// frontend/src/pages/MiPagina.tsx
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/axios'

export default function MiPagina() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['mi-recurso'],
    queryFn: () => api.get('/mi-recurso').then(r => r.data),
  })

  if (isLoading) return <div className="p-6">Cargando...</div>
  if (error) return <div className="p-6 text-destructive">Error al cargar</div>

  return (
    <div className="p-6 space-y-4">
      {/* contenido */}
    </div>
  )
}
```

Registrar la ruta en `frontend/src/App.tsx`:
```tsx
const MiPagina = lazy(() => import('./pages/MiPagina'))
// Dentro del Router:
<Route path="/mi-pagina" element={<MiPagina />} />
```

## Cliente HTTP
```tsx
// Usar siempre la instancia configurada — tiene interceptors para JWT
import { api } from '@/lib/axios'

// El token se inyecta automáticamente desde AuthContext
const data = await api.get('/endpoint')
const result = await api.post('/endpoint', payload)
```

## Autenticación
```tsx
import { useAuth } from '@/contexts/AuthContext'

const { user, logout, isLoading } = useAuth()
// user.role: 'admin' | 'advertiser'
// user.plan_status: 'trial' | 'active' | 'suspended' | 'churned'
```

## Iconos — solo Lucide React
```tsx
import { Plus, Trash2, Edit, Send, Phone, User } from 'lucide-react'
// NO instalar heroicons, phosphor, material icons, etc.
```

## Patrones de componentes reutilizables

### Loading skeleton
```tsx
{isLoading ? (
  <div className="animate-pulse space-y-2">
    <div className="h-4 bg-muted rounded w-3/4" />
    <div className="h-4 bg-muted rounded w-1/2" />
  </div>
) : (
  <>{/* contenido */}</>
)}
```

### Empty state
```tsx
{data?.length === 0 && (
  <div className="text-center py-12 text-muted-foreground">
    <IconName className="mx-auto h-12 w-12 mb-4 opacity-30" />
    <p>No hay elementos todavía</p>
  </div>
)}
```

## Tests frontend
- Unitarios: `cd frontend && npm test` (Vitest)
- E2E: `cd frontend && npm run test:e2e` (Playwright)
- Ubicación unitarios: `frontend/src/__tests__/`
- Ubicación e2e: `frontend/e2e/`
- Mockear llamadas API con `vi.mock('@/lib/axios')`

## Variables de entorno frontend
```
VITE_API_URL          # URL del backend (ej: http://localhost:8000)
VITE_SENTRY_DSN       # Sentry frontend
VITE_POSTHOG_KEY      # PostHog analytics
```
Acceder con `import.meta.env.VITE_*`
