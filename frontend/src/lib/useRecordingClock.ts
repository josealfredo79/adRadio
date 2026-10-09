import { useEffect, useState } from 'react'

/** Cronómetro "m:ss" que corre mientras `recording` sea true. */
export function useRecordingClock(recording: boolean): string {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!recording) return
    setSeconds(0)
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [recording])
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
