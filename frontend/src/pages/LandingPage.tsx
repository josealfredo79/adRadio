import { Link } from 'react-router-dom'
import {
  Radio, MessageCircle, Users, TrendingUp, Star,
  CheckCircle, ArrowRight, Gift, Bot, Mic, ChevronDown,
  Sparkles, Shield, Clock, PhoneCall, BarChart3, Zap
} from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import RadioSphere3D from '../components/RadioSphere3D'
import { LANDING_PLANS } from '@/lib/plans'

function useCountUp(target: number, duration = 1800, start = false) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!start) return
    let startTime: number | null = null
    const step = (ts: number) => {
      if (!startTime) startTime = ts
      const progress = Math.min((ts - startTime) / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setCount(Math.round(eased * target))
      if (progress < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [target, duration, start])
  return count
}

function AnimatedStat({ n, label, suffix = '' }: { n: number; label: string; suffix?: string }) {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true) }, { threshold: 0.4 })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  const count = useCountUp(n, 1800, visible)
  return (
    <div ref={ref} className="glass rounded-2xl p-5 text-center">
      <div className="text-3xl font-black text-shimmer mb-1">
        {count.toLocaleString()}{suffix}
      </div>
      <div className="text-xs text-gray-500 leading-tight">{label}</div>
    </div>
  )
}

// PLANS ahora viene de src/lib/plans.ts — fuente de verdad única.
// Quitamos el array local para evitar desincronización.

const CHAT_MESSAGES = [
  { from: 'bot', text: '👋 Hola! Soy el asistente de *Pizzería El Fogón*. ¿En qué te puedo ayudar?' },
  { from: 'user', text: '¿Tienen pizza familiar de pepperoni?' },
  { from: 'bot', text: '🍕 ¡Claro! La familiar de pepperoni cuesta $189. Incluye 8 rebanadas. También tenemos 2x1 los martes 🔥' },
  { from: 'user', text: 'Qué bien! ¿Hacen domicilio?' },
  { from: 'bot', text: '🛵 Sí, a todo Oaxaca centro. Tiempo estimado: 30-40 min. ¿Te mando el menú completo?' },
]

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="border-b border-white/10 py-5 cursor-pointer"
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center justify-between gap-4">
        <span className="font-semibold text-white">{q}</span>
        <ChevronDown className={`h-4 w-4 text-indigo-400 shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </div>
      <div className={`overflow-hidden transition-all duration-300 ${open ? 'max-h-40 mt-3' : 'max-h-0'}`}>
        <p className="text-sm text-gray-400 leading-relaxed">{a}</p>
      </div>
    </div>
  )
}

function WhatsAppMockup() {
  const [visible, setVisible] = useState(0)
  useEffect(() => {
    if (visible >= CHAT_MESSAGES.length) return
    const t = setTimeout(() => setVisible(v => v + 1), visible === 0 ? 600 : 1200)
    return () => clearTimeout(t)
  }, [visible])

  return (
    <div className="relative mx-auto w-72">
      {/* Phone frame */}
      <div className="relative rounded-[2.5rem] border-4 border-white/20 bg-[#0a0a0a] shadow-2xl shadow-black/60 overflow-hidden">
        {/* Status bar */}
        <div className="flex items-center justify-between bg-[#128C7E] px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-white/20 flex items-center justify-center">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-xs font-semibold text-white">Pizzería El Fogón</div>
              <div className="text-[10px] text-green-200">● en línea</div>
            </div>
          </div>
          <PhoneCall className="h-4 w-4 text-white/70" />
        </div>
        {/* Chat */}
        <div className="bg-[#ECE5DD] px-3 py-3 space-y-2 min-h-[320px]" style={{backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'20\' height=\'20\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3C/svg%3E")'}}>
          {CHAT_MESSAGES.slice(0, visible).map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'}`}
              style={{ animation: 'fadeUp 0.3s ease' }}
            >
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-xs shadow-sm ${
                  msg.from === 'user'
                    ? 'rounded-tr-none bg-[#DCF8C6] text-gray-800'
                    : 'rounded-tl-none bg-white text-gray-800'
                }`}
                dangerouslySetInnerHTML={{
                  __html: msg.text.replace(/\*(.*?)\*/g, '<strong>$1</strong>')
                }}
              />
            </div>
          ))}
          {visible < CHAT_MESSAGES.length && (
            <div className="flex justify-start">
              <div className="rounded-xl rounded-tl-none bg-white px-3 py-2 shadow-sm flex gap-1 items-center">
                <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'0ms'}}></span>
                <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'150ms'}}></span>
                <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'300ms'}}></span>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* Floating badges */}
      <div className="absolute -left-10 top-16 rounded-xl bg-white px-3 py-2 shadow-xl text-xs font-semibold text-gray-800 flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></span>
        Bot activo 24/7
      </div>
      <div className="absolute -right-10 bottom-20 rounded-xl bg-white px-3 py-2 shadow-xl text-xs font-semibold text-gray-800 flex items-center gap-1.5">
        <TrendingUp className="h-3 w-3 text-indigo-500" />
        +340% ventas
      </div>
    </div>
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#06060f] text-white font-sans overflow-x-hidden">
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-12px); }
        }
        @keyframes shimmer {
          0% { background-position: -200% center; }
          100% { background-position: 200% center; }
        }
        .text-shimmer {
          background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899, #6366f1);
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: shimmer 4s linear infinite;
        }
        .float-anim { animation: float 4s ease-in-out infinite; }
        .glow-indigo { box-shadow: 0 0 60px rgba(99,102,241,0.3); }
        .glow-green { box-shadow: 0 0 40px rgba(34,197,94,0.2); }
        .glass {
          background: rgba(255,255,255,0.04);
          backdrop-filter: blur(12px);
          border: 1px solid rgba(255,255,255,0.08);
        }
        .mesh-bg {
          background:
            radial-gradient(ellipse 80% 50% at 20% 10%, rgba(99,102,241,0.15) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 80%, rgba(168,85,247,0.12) 0%, transparent 60%),
            radial-gradient(ellipse 50% 50% at 50% 50%, rgba(16,185,129,0.05) 0%, transparent 60%);
        }
      `}</style>

      {/* ─── NAV ─── */}
      <nav className="sticky top-0 z-50 glass">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/30">
              <Radio className="h-4.5 w-4.5 text-white" />
            </div>
            <span className="text-lg font-black tracking-tight">IaRadio</span>
          </div>
          <div className="hidden items-center gap-7 text-sm text-gray-400 sm:flex">
            <a href="#como-funciona" className="hover:text-white transition-colors">Cómo funciona</a>
            <a href="#precios" className="hover:text-white transition-colors">Precios</a>
            <a href="#faq" className="hover:text-white transition-colors">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
              Iniciar sesión
            </Link>
            <Link
              to="/register"
              className="rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 px-5 py-2 text-sm font-bold text-white shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:scale-105 transition-all"
            >
              Prueba gratis →
            </Link>
          </div>
        </div>
      </nav>

      {/* ─── HERO ─── */}
      <section className="relative mesh-bg px-5 pt-20 pb-28 overflow-hidden">
        {/* 3D Radio sphere background */}
        <RadioSphere3D />

        {/* Dot grid bg */}
        <div className="pointer-events-none absolute inset-0 opacity-20"
          style={{backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.4) 1px, transparent 1px)', backgroundSize: '32px 32px'}} />

        <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-16 lg:grid-cols-2">
          {/* Left */}
          <div>
            {/* Badge */}
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300">
              <Sparkles className="h-3.5 w-3.5" />
              Impulsado por Claude IA · Twilio · pgvector
            </div>

            <h1 className="mb-6 text-5xl font-black leading-[1.05] tracking-tight sm:text-6xl">
              Tu negocio en<br />
              <span className="text-shimmer">la radio del futuro</span>
            </h1>

            <p className="mb-8 text-lg text-gray-400 leading-relaxed max-w-lg">
              Campañas masivas por WhatsApp, bot IA que conoce tu negocio,
              cuñas de radio generadas en segundos. <strong className="text-white">Todo en una plataforma.</strong>
            </p>

            <div className="flex flex-wrap gap-3 mb-10">
              <Link
                to="/register"
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 px-7 py-3.5 text-base font-black text-white shadow-xl shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:scale-105 transition-all glow-indigo"
              >
                Empieza gratis
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="#como-funciona"
                className="flex items-center gap-2 rounded-xl glass px-6 py-3.5 text-base font-semibold text-gray-300 hover:text-white hover:border-white/20 transition-all"
              >
                Ver demo
              </a>
            </div>

            {/* Trust strip */}
            <div className="flex flex-wrap gap-5 text-sm text-gray-500">
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Sin tarjeta de crédito</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Cancela cuando quieras</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Configuración en 10 min</span>
            </div>
          </div>

          {/* Right — phone mockup */}
          <div className="flex justify-center float-anim">
            <WhatsAppMockup />
          </div>
        </div>

        {/* Stats row */}
        <div className="mx-auto mt-20 max-w-4xl grid grid-cols-2 sm:grid-cols-4 gap-4">
          <AnimatedStat n={2840} suffix="+" label="Negocios activos en México" />
          <AnimatedStat n={10} suffix=" min" label="Para lanzar tu primera campaña" />
          <AnimatedStat n={60} suffix="%" label="Cupones canjeados en promedio" />
          <AnimatedStat n={1200000} suffix="" label="Mensajes enviados este mes" />
        </div>
        {/* Live social proof ticker */}
        <div className="mx-auto mt-5 max-w-4xl flex items-center justify-center gap-2 text-xs text-gray-600">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          <span><strong className="text-green-400">24</strong> negocios se registraron hoy · Actualizado en vivo</span>
        </div>
      </section>

      {/* ─── PROBLEMA / ANTES–DESPUÉS ─── */}
      <section className="px-5 py-24">
        <div className="mx-auto max-w-5xl">
          <div className="mb-14 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">El problema real</p>
            <h2 className="text-4xl font-black text-white sm:text-5xl">
              Cada mensaje sin respuesta<br />es dinero que se va
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {/* Before */}
            <div className="rounded-3xl border border-red-500/20 bg-red-500/5 p-8">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-red-500/15 px-3 py-1 text-xs font-bold text-red-400 uppercase tracking-widest">
                ✗ Sin IaRadio
              </div>
              <ul className="space-y-4 text-gray-400 text-sm">
                {[
                  'Contestas WhatsApp uno a uno, todo el día',
                  'Olvidas contactar a clientes y pierdes ventas',
                  'No tienes tiempo para pensar en publicidad',
                  'Mandas el mismo mensaje a todos, sin personalizar',
                  'No sabes cuántos clientes leyeron tu mensaje',
                ].map(t => (
                  <li key={t} className="flex items-start gap-3">
                    <span className="mt-0.5 h-5 w-5 rounded-full bg-red-500/20 flex items-center justify-center shrink-0 text-red-400 text-xs">✗</span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            {/* After */}
            <div className="rounded-3xl border border-indigo-500/30 bg-gradient-to-br from-indigo-500/10 to-purple-500/5 p-8">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-bold text-indigo-300 uppercase tracking-widest">
                ✓ Con IaRadio
              </div>
              <ul className="space-y-4 text-gray-300 text-sm">
                {[
                  'El bot responde automáticamente las 24 horas',
                  'Campañas programadas llegan a todos tus contactos',
                  'Claude IA escribe el texto publicitario por ti',
                  'Cada mensaje tiene el nombre del cliente',
                  'Dashboard en tiempo real: enviados, leídos, canjeados',
                ].map(t => (
                  <li key={t} className="flex items-start gap-3">
                    <span className="mt-0.5 h-5 w-5 rounded-full bg-indigo-500/20 flex items-center justify-center shrink-0 text-indigo-400 text-xs">✓</span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CÓMO FUNCIONA ─── */}
      <section id="como-funciona" className="px-5 py-24 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 mesh-bg opacity-60" />
        <div className="relative mx-auto max-w-5xl">
          <div className="mb-16 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Así de fácil</p>
            <h2 className="text-4xl font-black text-white sm:text-5xl">En 3 pasos tienes clientes</h2>
          </div>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            {[
              {
                n: '01', icon: <Users className="h-6 w-6 text-indigo-400" />,
                title: 'Sube tu info y contactos',
                desc: 'Importa tu lista de clientes en CSV y sube tu menú, catálogo o descripción de servicios. La IA lo aprende todo.',
                color: 'from-indigo-500/20 to-indigo-500/5',
              },
              {
                n: '02', icon: <Sparkles className="h-6 w-6 text-purple-400" />,
                title: 'La IA crea tu campaña',
                desc: 'Escribe tu intención ("Ofrecer 20% de descuento") y Claude genera 3 variantes de mensaje profesionales al instante.',
                color: 'from-purple-500/20 to-purple-500/5',
              },
              {
                n: '03', icon: <MessageCircle className="h-6 w-6 text-green-400" />,
                title: 'Lanza y el bot atiende',
                desc: 'Con un clic envías a todos tus contactos. El bot IA responde las preguntas en automático mientras tú descansas.',
                color: 'from-green-500/20 to-green-500/5',
              },
            ].map(s => (
              <div key={s.n} className={`relative glass rounded-3xl p-7 bg-gradient-to-br ${s.color}`}>
                <div className="absolute top-5 right-5 text-5xl font-black text-white/5">{s.n}</div>
                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl glass">
                  {s.icon}
                </div>
                <h3 className="mb-2 text-lg font-bold text-white">{s.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FEATURES GRID ─── */}
      <section className="px-5 py-24">
        <div className="mx-auto max-w-5xl">
          <div className="mb-16 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Funcionalidades</p>
            <h2 className="text-4xl font-black text-white sm:text-5xl">Una plataforma. Todo incluido.</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: <Bot className="h-5 w-5 text-indigo-400" />,
                title: 'Bot IA con tu conocimiento',
                desc: 'Responde preguntas 24/7 usando tu catálogo, menú o lista de precios. Entiende contexto, no solo palabras clave.',
                badge: 'IA',
              },
              {
                icon: <MessageCircle className="h-5 w-5 text-green-400" />,
                title: 'Campañas masivas WhatsApp',
                desc: 'Envía a cientos de contactos personalizando nombre, ciudad y producto. Anti-ban automático.',
                badge: null,
              },
              {
                icon: <Mic className="h-5 w-5 text-purple-400" />,
                title: 'Cuñas de radio con IA',
                desc: 'Genera spots de audio profesionales en segundos y envíalos como notas de voz en WhatsApp.',
                badge: 'NUEVO',
              },
              {
                icon: <Gift className="h-5 w-5 text-orange-400" />,
                title: 'Cupones automáticos',
                desc: 'Código único por contacto. Se canjea respondiendo "CANJEAR". Rastreo de redención en tiempo real.',
                badge: null,
              },
              {
                icon: <BarChart3 className="h-5 w-5 text-blue-400" />,
                title: 'Analytics en tiempo real',
                desc: 'Enviados, entregados, leídos, respondidos y cupones canjeados en un dashboard limpio.',
                badge: null,
              },
              {
                icon: <Shield className="h-5 w-5 text-emerald-400" />,
                title: 'Seguro y confiable',
                desc: 'Validación de firma Twilio, rate limiting, bcrypt cost 12, JWT con rotación automática.',
                badge: null,
              },
            ].map(f => (
              <div key={f.title} className="group glass rounded-2xl p-6 hover:border-indigo-500/30 hover:bg-indigo-500/5 transition-all">
                <div className="mb-4 flex items-start justify-between">
                  <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/5">
                    {f.icon}
                  </div>
                  {f.badge && (
                    <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300 uppercase tracking-wider">
                      {f.badge}
                    </span>
                  )}
                </div>
                <h3 className="mb-2 font-bold text-white">{f.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── TESTIMONIALS ─── */}
      <section className="px-5 py-24 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 mesh-bg opacity-40" />
        <div className="relative mx-auto max-w-5xl">
          <div className="mb-14 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Historias reales</p>
            <h2 className="text-4xl font-black text-white sm:text-5xl">Negocios que ya triunfan</h2>
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            {[
              {
                emoji: '🍽️', name: 'Restaurante El Fogón', loc: 'Oaxaca, México',
                rating: 5,
                text: '"Mandamos una campaña del menú del día y en 20 minutos teníamos 15 reservaciones. Antes tardábamos horas llamando uno a uno."',
                result: '+340% reservaciones',
              },
              {
                emoji: '💊', name: 'Farmacia Salud Plus', loc: 'Puebla, México',
                rating: 5,
                text: '"El bot responde disponibilidad de medicamentos a las 2am. Mis clientes están encantados y ya no pierdo ventas nocturnas."',
                result: 'Atención 24/7',
              },
              {
                emoji: '💇', name: 'Estética Glamour', loc: 'CDMX, México',
                rating: 5,
                text: '"Los cupones de WhatsApp tienen 60% de canje. Nunca pensé que captar clientes nuevas pudiera ser tan barato y efectivo."',
                result: '60% cupones canjeados',
              },
            ].map(t => (
              <div key={t.name} className="glass rounded-3xl p-7 flex flex-col">
                <div className="flex gap-0.5 mb-4">
                  {[...Array(t.rating)].map((_, i) => (
                    <Star key={i} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-sm text-gray-300 leading-relaxed italic flex-1 mb-5">{t.text}</p>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{t.emoji}</span>
                      <div>
                        <div className="text-sm font-bold text-white">{t.name}</div>
                        <div className="text-xs text-gray-500">{t.loc}</div>
                      </div>
                    </div>
                  </div>
                  <div className="rounded-xl bg-green-500/15 px-3 py-1.5 text-xs font-bold text-green-400">
                    {t.result}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── PRECIOS ─── */}
      <section id="precios" className="px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-14 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Precios</p>
            <h2 className="text-4xl font-black text-white sm:text-5xl">Invierte lo que vendes en un día</h2>
            <p className="mt-4 text-gray-500">Sin contratos. Cancela cuando quieras.</p>
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4 items-start">
            {LANDING_PLANS.map(plan => (
              <div
                key={plan.key}
                className={`relative rounded-3xl p-7 flex flex-col transition-all ${
                  plan.popular
                    ? 'bg-gradient-to-br from-indigo-600/30 to-purple-600/20 border-2 border-indigo-500/60 shadow-2xl shadow-indigo-500/20 scale-[1.03]'
                    : 'glass'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 px-5 py-1.5 text-xs font-black text-white shadow-lg shadow-indigo-500/30">
                    {plan.badge ?? '⭐ Más popular'}
                  </div>
                )}
                <div className="mb-1 text-sm font-bold text-gray-400 uppercase tracking-widest">{plan.name}</div>
                <div className="mb-1 text-4xl font-black text-white">
                  ${plan.price_mxn.toLocaleString()}
                  <span className="text-base font-normal text-gray-500"> MXN/mes</span>
                </div>
                <div className="mb-1 text-xs text-gray-600">≈ ${plan.price_usd} USD</div>
                <p className="mb-5 text-xs text-gray-500 italic">{plan.tagline}</p>
                <ul className="mb-7 space-y-3 flex-1">
                  {plan.features.map(f => {
                    const isHighlight = plan.highlightFeatures?.includes(f)
                    return (
                      <li key={f} className="flex items-center gap-2.5 text-sm">
                        {isHighlight
                          ? <Sparkles className="h-4 w-4 text-indigo-400 shrink-0" />
                          : <CheckCircle className="h-4 w-4 text-indigo-400 shrink-0" />
                        }
                        <span className={isHighlight ? 'text-white font-medium' : 'text-gray-300'}>{f}</span>
                      </li>
                    )
                  })}
                </ul>
                <Link
                  to="/register"
                  className={`block w-full rounded-xl py-3 text-center text-sm font-black transition-all hover:scale-105 ${
                    plan.popular
                      ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50'
                      : 'glass text-gray-300 hover:text-white hover:border-indigo-500/40'
                  }`}
                >
                  Empezar con {plan.name} →
                </Link>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-sm text-gray-600">
            ¿Más de 10,000 mensajes/mes?{' '}
            <Link to="/register" className="text-indigo-400 hover:text-indigo-300">Contáctanos para Enterprise</Link>
          </p>
        </div>
      </section>

      {/* ─── INTEGRACIONES ─── */}
      <section className="px-5 py-16 border-y border-white/5">
        <div className="mx-auto max-w-4xl text-center">
          <p className="mb-8 text-sm font-semibold uppercase tracking-widest text-gray-600">Integrado con las mejores herramientas</p>
          <div className="flex flex-wrap items-center justify-center gap-6">
            {[
              { label: 'WhatsApp Business', color: 'text-green-400', emoji: '🟢' },
              { label: 'Claude IA (Anthropic)', color: 'text-orange-400', emoji: '🤖' },
              { label: 'Twilio', color: 'text-red-400', emoji: '📞' },
              { label: 'Stripe', color: 'text-blue-400', emoji: '💳' },
              { label: 'Voyage AI', color: 'text-purple-400', emoji: '🧠' },
              { label: 'Cloudflare R2', color: 'text-orange-300', emoji: '☁️' },
            ].map(i => (
              <div key={i.label} className="glass rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm font-medium text-gray-400">
                <span>{i.emoji}</span> {i.label}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section id="faq" className="px-5 py-24">
        <div className="mx-auto max-w-2xl">
          <div className="mb-12 text-center">
            <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">FAQ</p>
            <h2 className="text-4xl font-black text-white">Preguntas frecuentes</h2>
          </div>
          <div className="glass rounded-3xl p-8">
            <FaqItem q="¿Necesito saber programar?" a="No. Si sabes mandar un WhatsApp, sabes usar IaRadio. Todo está diseñado para dueños de negocio, no para ingenieros." />
            <FaqItem q="¿Cómo aprende el bot sobre mi negocio?" a="Subes tu menú, catálogo o descripción de servicios (PDF o texto). El sistema genera embeddings vectoriales y el bot responde solo con esa información, nunca inventa cosas." />
            <FaqItem q="¿El número de WhatsApp es el mío?" a="Para campañas outbound usamos un número compartido de Twilio (sandbox). Para bot inbound con número propio incluimos configuración de número dedicado en los planes Pro y Business." />
            <FaqItem q="¿Qué pasa si me quedo sin mensajes?" a="Puedes subir de plan en cualquier momento desde tu dashboard. Tus contactos, campañas y base de conocimiento se mantienen intactos." />
            <FaqItem q="¿Puedo cancelar en cualquier momento?" a="Sí, sin penalizaciones ni contratos. Cancelas desde Configuración → Suscripción en menos de 1 minuto." />
            <FaqItem q="¿Funciona para cualquier tipo de negocio?" a="Sí. Restaurantes, farmacias, estéticas, tiendas de ropa, clínicas, servicios profesionales... cualquier negocio que use WhatsApp para comunicarse con clientes." />
          </div>
        </div>
      </section>

      {/* ─── CTA FINAL ─── */}
      <section className="px-5 py-28 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 mesh-bg" />
        <div className="pointer-events-none absolute inset-0" style={{background: 'radial-gradient(ellipse 60% 60% at 50% 50%, rgba(99,102,241,0.15) 0%, transparent 70%)'}} />
        <div className="relative mx-auto max-w-3xl text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300">
            <Zap className="h-3.5 w-3.5" />
            Gratis los primeros 7 días
          </div>
          <h2 className="mb-6 text-5xl font-black leading-tight sm:text-6xl">
            Tu negocio merece<br />
            <span className="text-shimmer">una radio propia</span>
          </h2>
          <p className="mb-10 text-xl text-gray-400">
            Únete a los negocios mexicanos que ya usan IA para vender más por WhatsApp.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-indigo-500 to-purple-600 px-10 py-5 text-lg font-black text-white shadow-2xl shadow-indigo-500/40 hover:shadow-indigo-500/60 hover:scale-105 transition-all glow-indigo"
          >
            Crear mi cuenta gratis
            <ArrowRight className="h-5 w-5" />
          </Link>
          <div className="mt-6 flex flex-wrap justify-center gap-5 text-sm text-gray-600">
            <span className="flex items-center gap-1.5"><Clock className="h-4 w-4" /> Sin tarjeta de crédito</span>
            <span className="flex items-center gap-1.5"><Shield className="h-4 w-4" /> Datos seguros</span>
            <span className="flex items-center gap-1.5"><Zap className="h-4 w-4" /> Listo en 10 minutos</span>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="border-t border-white/5 px-5 py-10">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-5 sm:flex-row sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600">
              <Radio className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="font-black text-white">IaRadio</span>
            <span className="text-gray-600 text-sm">— Radio Publicitaria por WhatsApp con IA</span>
          </div>
          <div className="flex gap-5 text-sm text-gray-600">
            <Link to="/login" className="hover:text-gray-300 transition-colors">Iniciar sesión</Link>
            <Link to="/register" className="hover:text-gray-300 transition-colors">Registrarse</Link>
          </div>
        </div>
        <p className="mt-6 text-center text-xs text-gray-700">© {new Date().getFullYear()} IaRadio. Hecho con ❤️ en México.</p>
      </footer>

    </div>
  )
}


