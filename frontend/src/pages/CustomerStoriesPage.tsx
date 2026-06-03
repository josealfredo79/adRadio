import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import { Mic, ChevronDown, ChevronUp, Star, Radio } from 'lucide-react'

interface Story {
  id: string
  business_name: string | null
  transcription: string
  media_url: string
  sentiment: string
  created_at: string
}

const SENTIMENT_COLORS: Record<string, string> = {
  positivo: 'bg-green-900/50 text-green-400 border-green-800',
  negativo: 'bg-red-900/50 text-red-400 border-red-800',
  neutro: 'bg-gray-800/50 text-gray-400 border-gray-700',
}

export default function CustomerStoriesPage() {
  const { data: stories, isLoading } = useQuery<Story[]>({
    queryKey: ['public-stories'],
    queryFn: () => api.get('/campaigns/stories/public').then((r) => r.data),
    refetchOnMount: false,
  })

  return (
    <>
      <SEO title="Historias de Clientes" description="Historias reales de clientes que usan IaRadio para hacer crecer su negocio." noIndex />
      <div className="min-h-screen bg-[#06060f] text-white font-sans overflow-x-hidden">
        <style>{`
          @keyframes fadeUp {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes shimmer {
            0% { background-position: -200% center; }
            100% { background-position: 200% center; }
          }
          .text-shimmer {
            background: linear-gradient(90deg, #674CC4, #6366f1, #a855f7, #674CC4);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: shimmer 4s linear infinite;
          }
          .glass {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.08);
          }
          .mesh-bg {
            background:
              radial-gradient(ellipse 80% 50% at 20% 10%, rgba(124,58,237,0.18) 0%, transparent 60%),
              radial-gradient(ellipse 60% 40% at 80% 80%, rgba(99,102,241,0.14) 0%, transparent 60%),
              radial-gradient(ellipse 50% 50% at 50% 50%, rgba(168,85,247,0.08) 0%, transparent 60%);
          }
        `}</style>

        {/* Hero */}
        <section className="relative mesh-bg px-5 py-20 sm:py-28 text-center">
          <div className="mx-auto max-w-3xl relative z-10">
            <div className="inline-flex items-center gap-2 rounded-full glass px-4 py-1.5 mb-6 text-sm text-indigo-300">
              <Mic className="h-3.5 w-3.5" />
              Voces del Barrio
            </div>
            <h1 className="text-4xl sm:text-6xl font-black leading-tight mb-5">
              Historias de <span className="text-shimmer">Clientes</span>
            </h1>
            <p className="text-lg text-gray-400 max-w-xl mx-auto leading-relaxed">
              Descubre cómo los negocios están transformando su comunicación con IaRadio.
              Historias reales, voces auténticas.
            </p>
          </div>
        </section>

        {/* Stories Grid */}
        <section className="mx-auto max-w-6xl px-5 py-16">
          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-2xl glass p-5 space-y-4 animate-pulse">
                  <div className="h-4 w-24 bg-white/10 rounded" />
                  <div className="h-3 w-full bg-white/10 rounded" />
                  <div className="h-3 w-3/4 bg-white/10 rounded" />
                  <div className="h-10 w-full bg-white/10 rounded" />
                  <div className="h-3 w-16 bg-white/10 rounded" />
                </div>
              ))}
            </div>
          ) : !stories || stories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-500">
              <Radio className="h-16 w-16 mb-4 opacity-30" />
              <p className="text-lg font-medium">No hay historias publicadas aún</p>
              <p className="text-sm mt-1">Las historias aprobadas por los negocios aparecerán aquí.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {stories.map((story, idx) => (
                <StoryCard key={story.id} story={story} idx={idx} />
              ))}
            </div>
          )}
        </section>

        {/* Footer */}
        <footer className="border-t border-white/10 py-8 text-center text-sm text-gray-500">
          <p>IaRadio — Radio Publicitaria con IA</p>
        </footer>
      </div>
    </>
  )
}

function StoryCard({ story, idx }: { story: Story; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  const truncated = story.transcription.length > 150

  return (
    <div
      className="glass rounded-2xl p-5 flex flex-col gap-3 hover:border-indigo-500/30 transition-all duration-300"
      style={{ animation: `fadeUp 0.4s ease ${idx * 0.05}s both` }}
    >
      {/* Business name + sentiment */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Star className="h-4 w-4 text-amber-400 shrink-0" />
          <span className="font-semibold text-white truncate">
            {story.business_name || 'Negocio'}
          </span>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] font-medium capitalize ${SENTIMENT_COLORS[story.sentiment] || SENTIMENT_COLORS.neutro}`}>
          {story.sentiment}
        </span>
      </div>

      {/* Transcription */}
      <div className="flex-1">
        <p className="text-sm text-gray-300 leading-relaxed">
          {expanded || !truncated ? story.transcription : story.transcription.slice(0, 150) + '...'}
        </p>
        {truncated && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1 flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            {expanded ? (
              <>Mostrar menos <ChevronUp className="h-3 w-3" /></>
            ) : (
              <>Leer más <ChevronDown className="h-3 w-3" /></>
            )}
          </button>
        )}
      </div>

      {/* Audio player */}
      {story.media_url && (
        <audio controls src={story.media_url} className="w-full h-9 rounded-lg" />
      )}

      {/* Date */}
      <p className="text-[11px] text-gray-500">
        {new Date(story.created_at).toLocaleDateString('es-MX', { year: 'numeric', month: 'long', day: 'numeric' })}
      </p>
    </div>
  )
}
