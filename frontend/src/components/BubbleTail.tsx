// La colita de la primera burbuja de cada tanda, como en WhatsApp.
export default function BubbleTail({ side, fill }: { side: 'left' | 'right'; fill: string }) {
  return (
    <svg
      aria-hidden
      width="8"
      height="13"
      viewBox="0 0 8 13"
      className="absolute top-0"
      style={side === 'left' ? { left: -8 } : { right: -8, transform: 'scaleX(-1)' }}
    >
      <path d="M8 0H1.5C.4 0-.3 1.2.3 2.1L8 13z" style={{ fill }} />
    </svg>
  )
}
