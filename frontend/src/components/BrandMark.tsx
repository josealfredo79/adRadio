// Marca de IaRadio: la "i" cuyo punto transmite. Misma geometría que
// public/favicon.svg y docs/brand/ — si cambias una, cambia las demás.
export default function BrandMark({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} role="img" aria-label="IaRadio">
      <rect width="100" height="100" rx="22" fill="#4F46E5" />
      <rect x="43" y="46" width="14" height="40" rx="7" fill="#fff" />
      <circle cx="50" cy="28" r="8" fill="#FF5A36" />
      <path d="M37.74 17.72A16 16 0 0 0 37.74 38.28M62.26 17.72A16 16 0 0 1 62.26 38.28" stroke="#fff" strokeWidth="6" fill="none" strokeLinecap="round" />
      <path d="M30.08 11.29A26 26 0 0 0 30.08 44.71M69.92 11.29A26 26 0 0 1 69.92 44.71" stroke="#fff" strokeWidth="6" fill="none" strokeLinecap="round" opacity=".5" />
    </svg>
  )
}
