// Cómo se mueve cada punto de la cabeza escaneada al hablar, sonreír y
// parpadear. Lo comparten PointFace3D (puntos) y MeshHead3D (malla sólida).
// Unidades del modelo: ver PointFace3D.

const g = (dx: number, dy: number, sx: number, sy: number) => Math.exp(-((dx * dx) / (2 * sx * sx) + (dy * dy) / (2 * sy * sy)))
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

const MOUTH_HALF = 0.4
/** Línea donde se juntan los labios (igual que en build_head_points.py). */
const lipLine = (x: number) => 0.405 + 0.03 * (1 - (x / MOUTH_HALF) ** 2)

/** Pesos de animación de un punto: mandíbula, labio de arriba, comisuras, párpado. */
export function weights(x: number, y: number, z: number, role: number): [number, number, number, number] {
  const ax = Math.abs(x)
  const corner = g(ax - MOUTH_HALF, y - 0.4, 0.1, 0.08) * smooth(1.4, 1.8, z)
  // Cuánto se abre la boca a lo ancho: todo al centro y casi nada en las
  // comisuras, para que la piel junto a ellas no se rasgue al bajar.
  const open = Math.exp(-(x * x) / (2 * 0.27 * 0.27))
  if (role === 1) return [0, open, corner, 0]
  if (role === 2) return [open, 0, corner, 0]
  // Piel: lo que está bajo la línea de la boca baja con la mandíbula, menos
  // hacia los lados y hacia atrás (la quijada gira, no se desliza); el cuello
  // se queda en su lugar.
  // Dentro de la boca el corte es seco (el labio de abajo baja entero); hacia
  // las mejillas se suaviza para no rasgar la piel.
  const band = 0.006 + 0.25 * smooth(0.25, 0.45, ax)
  const jaw = smooth(lipLine(x) + 0.002, lipLine(x) - band, y) * smooth(-1.1, -0.6, y) * open * smooth(0.9, 1.7, z)
  const upper = smooth(0.75, 0.55, y) * smooth(lipLine(x) - 0.02, lipLine(x) + 0.04, y) * Math.exp(-(x * x) / (2 * 0.35 * 0.35)) * smooth(1.6, 2.0, z) * 0.5
  const lid = smooth(1.68, 1.76, y) * g(ax - 0.59, y - 1.8, 0.2, 0.08) * smooth(1.5, 1.9, z)
  return [jaw, upper, corner, lid]
}
