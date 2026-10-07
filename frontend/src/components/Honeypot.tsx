// Campo trampa para bots (backend: app/core/bot_guard.py). Fuera de la
// pantalla, sin tabulador ni autocompletar: una persona nunca lo llena; un bot
// que rellena todos los campos, sí.
export default function Honeypot({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input
      type="text"
      name="website"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      tabIndex={-1}
      autoComplete="off"
      aria-hidden="true"
      style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, opacity: 0 }}
    />
  )
}
