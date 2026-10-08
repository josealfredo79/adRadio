export default function ChatAvatar({ name, logo, color, size = 52 }: { name: string; logo: string; color: string; size?: number }) {
  return logo ? (
    <img src={logo} alt="" className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />
  ) : (
    <div
      className="flex shrink-0 items-center justify-center rounded-full text-lg font-bold text-white"
      style={{ width: size, height: size, background: `linear-gradient(135deg, ${color}, ${color}99)` }}
    >
      {(name || '?')[0].toUpperCase()}
    </div>
  )
}
