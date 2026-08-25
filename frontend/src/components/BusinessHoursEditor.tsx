import { DAY_LABELS, DAY_ORDER, type BusinessHours } from '@/pages/publicSite/utils'

/** Reusable 7-day hours editor for `User.business_hours` — same field drives
 * both the public site's displayed hours and how many appointment slots the
 * bot offers (see backend/app/services/availability_service.py). Originally
 * only reachable from the landing-page design wizard (WidgetPage.tsx); also
 * mounted in AppointmentsPage.tsx so it's discoverable from where someone
 * managing citas would actually look for it. */
export default function BusinessHoursEditor({
  value,
  onChange,
}: {
  value: BusinessHours
  onChange: (next: BusinessHours) => void
}) {
  const toggleDayClosed = (day: string) => {
    onChange({ ...value, [day]: value[day] ? null : ['09:00', '18:00'] })
  }
  const setDayRange = (day: string, range: [string, string]) => {
    onChange({ ...value, [day]: range })
  }
  const hoursValid = DAY_ORDER.every((day) => {
    const v = value[day]
    return !v || v[0] < v[1]
  })

  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {DAY_ORDER.map((day) => {
          const val = value[day] ?? null
          return (
            <div key={day} className="flex items-center gap-2 text-sm">
              <span className="w-9 text-xs text-gray-500 dark:text-gray-400 shrink-0">{DAY_LABELS[day]}</span>
              <label className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 shrink-0">
                <input type="checkbox" checked={val === null} onChange={() => toggleDayClosed(day)} />
                Cerrado
              </label>
              {val && (
                <>
                  <input
                    type="time"
                    value={val[0]}
                    onChange={(e) => setDayRange(day, [e.target.value, val[1]])}
                    className="rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1 text-xs bg-background text-foreground"
                  />
                  <span className="text-gray-400 dark:text-gray-500">-</span>
                  <input
                    type="time"
                    value={val[1]}
                    onChange={(e) => setDayRange(day, [val[0], e.target.value])}
                    className="rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1 text-xs bg-background text-foreground"
                  />
                </>
              )}
            </div>
          )
        })}
      </div>
      {!hoursValid && (
        <p className="text-xs text-red-500">La hora de apertura debe ser antes que la de cierre.</p>
      )}
    </div>
  )
}
