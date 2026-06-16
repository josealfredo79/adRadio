import { useState, useEffect, useRef } from 'react'

export function useCountUp(target: number, duration = 1800, start = false) {
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

export function AnimatedStat({ n, label, suffix = '' }: { n: number; label: string; suffix?: string }) {
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
