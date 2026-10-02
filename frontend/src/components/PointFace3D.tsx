import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import BotFace, { type FaceMood } from '@/components/BotFace'

// Rostro 3D de puntos (estilo "face mesh") que mueve los labios con la voz de
// verdad. Estilo: puntos celestes en forma de triangulito sobre azul marino,
// dispersos en la piel y CONCENTRADOS en las líneas que dan la expresión
// (párpados, cejas, nariz, labios, pliegues, contorno). Sin modelos ni
// imágenes: todo se arma con matemáticas sobre la superficie de la cara.
//
// - Hablando: la mandíbula y el labio inferior siguen `getLevel()` (el volumen
//   real del audio que suena, ver useSpeaker.level).
// - Escuchando: la boca sigue tu voz (`volume`) y la cabeza asiente un poco.
// - Pensando: mira hacia arriba. Contento: sonrisa. Parpadea solo.
// La deformación corre en el vertex shader: por cuadro solo cambian 3 números.
// Si el navegador no tiene WebGL, se muestra la carita de siempre (BotFace).

interface Props {
  mood: FaceMood
  /** 0–1: volumen del micrófono mientras escucha */
  volume?: number
  /** 0–1: apertura de boca mientras habla (voz real) */
  getLevel?: () => number
  size?: number
}

const g = (dx: number, dy: number, sx: number, sy: number) => Math.exp(-((dx * dx) / (2 * sx * sx) + (dy * dy) / (2 * sy * sy)))
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

// Generador pseudoaleatorio con semilla: la cara sale igual en cada visita.
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

// ─── La superficie de la cara ───────────────────────────────────────────────
// y va de -1 (mentón) a 1 (coronilla); x hacia los lados; z hacia la cámara.

const narrow = (y: number) => 1 - 0.32 * smooth(-0.3, -1, y) // quijada hacia el mentón
const halfWidth = (y: number) => Math.sqrt(Math.max(0, 1 - y * y)) * 0.74 * narrow(y)

/** Relieve de las facciones (cuencas, nariz, labios, mentón…). */
function relief(x: number, y: number): number {
  const ax = Math.abs(x)
  return 1.4 * (
    -0.11 * g(ax - 0.26, y - 0.0, 0.11, 0.07) + // cuencas de los ojos
    0.05 * g(ax - 0.26, y - 0.0, 0.06, 0.035) + // ojos
    0.05 * g(ax - 0.27, y - 0.16, 0.15, 0.04) + // cejas
    0.1 * g(x, y + 0.1, 0.05, 0.15) + // tabique
    0.17 * g(x, y + 0.26, 0.07, 0.06) + // punta de la nariz
    0.06 * g(ax - 0.1, y + 0.28, 0.045, 0.04) + // aletas
    0.06 * g(x, y + 0.45, 0.16, 0.03) + // labio superior
    0.07 * g(x, y + 0.52, 0.14, 0.035) + // labio inferior
    0.06 * g(ax - 0.36, y + 0.12, 0.12, 0.12) + // pómulos
    0.07 * g(x, y + 0.78, 0.14, 0.09) // mentón
  )
}

/** Profundidad de la cara en (x, y): elipsoide + relieve de las facciones. */
function surfaceZ(x: number, y: number): number {
  const sx = x / (0.74 * narrow(y))
  const sz = Math.sqrt(Math.max(0, 1 - sx * sx - y * y))
  return sz * 0.82 * (1 - 0.12 * smooth(-0.35, -1, y)) + relief(x, y) * smooth(0.12, 0.6, sz)
}

// ─── Las líneas que dan la expresión ────────────────────────────────────────

type Curve = (t: number) => [number, number]

/** Curvas en coordenadas de la cara. Las de un solo lado se reflejan. */
function featureCurves(): { curve: Curve; n: number; mirror?: boolean }[] {
  const eye = (cx: number, upper: boolean): Curve => (t) => {
    const x = cx - 0.12 + 0.24 * t
    const lift = 0.012 * (t - 0.5) // rabito del ojo un poco más alto
    const arc = Math.sin(Math.PI * t)
    return [x, lift + (upper ? 0.05 * Math.pow(arc, 0.9) : -0.028 * arc)]
  }
  return [
    { curve: eye(0.26, true), n: 42, mirror: true }, // párpado superior
    { curve: eye(0.26, false), n: 30, mirror: true }, // párpado inferior
    { curve: (t) => [0.1 + 0.34 * t, 0.15 + 0.045 * Math.sin(Math.PI * Math.pow(t, 0.8))], n: 30, mirror: true }, // ceja
    { curve: (t) => [0.045 + 0.025 * t, -0.02 - 0.2 * t], n: 14, mirror: true }, // costados del tabique
    {
      // base de la nariz: una curva suave con las aletas hacia arriba
      curve: (t) => {
        const x = -0.13 + 0.26 * t
        return [x, -0.3 + 0.035 * Math.pow(Math.abs(x) / 0.13, 2)]
      },
      n: 40,
    },
    { curve: (t) => [0.1 + 0.045 * Math.cos(Math.PI * (0.5 + t)), -0.27 + 0.04 * Math.sin(Math.PI * (0.5 + t))], n: 14, mirror: true }, // aleta
    { curve: (t) => [0.025, -0.33 - 0.1 * t], n: 8, mirror: true }, // surco del labio
    {
      // labio superior con el arco de Cupido
      curve: (t) => {
        const x = -0.18 + 0.36 * t
        const u = Math.abs(x) / 0.18
        return [x, -0.48 + 0.055 * (1 - Math.pow(u, 1.6)) - 0.018 * Math.exp(-(x * x) / (2 * 0.025 * 0.025))]
      },
      n: 46,
    },
    {
      // línea de la boca
      curve: (t) => {
        const x = -0.19 + 0.38 * t
        return [x, -0.48 - 0.012 * (1 - Math.pow(x / 0.19, 2))]
      },
      n: 44,
    },
    {
      // labio inferior
      curve: (t) => {
        const x = -0.16 + 0.32 * t
        return [x, -0.49 - 0.06 * Math.pow(Math.max(0, 1 - Math.pow(x / 0.16, 2)), 0.8)]
      },
      n: 40,
    },
    { curve: (t) => [0.13 + 0.09 * Math.sin(Math.PI * 0.5 * t), -0.27 - 0.23 * t], n: 22, mirror: true }, // pliegue de la sonrisa
    { curve: (t) => [-0.1 + 0.2 * t, -0.74 - 0.025 * Math.sin(Math.PI * t)], n: 16 }, // mentón
    { curve: (t) => [0, 0.86 - 0.62 * t], n: 18 }, // línea central de la frente
    { curve: (t) => [0, -0.6 - 0.32 * t], n: 10 }, // línea central del mentón
    { curve: (t) => [0.95 * halfWidth(0.86 - 1.81 * t), 0.86 - 1.81 * t], n: 90, mirror: true }, // contorno
  ]
}

interface FaceGeometry {
  base: Float32Array
  colors: Float32Array
  jaw: Float32Array
  upperLip: Float32Array
  corners: Float32Array
  lids: Float32Array
}

function buildFace(fillCount: number): FaceGeometry {
  const pts: number[] = []
  const shade: number[] = []
  const rand = rng(20261001)

  const add = (x: number, y: number, bright: number, jitter: number) => {
    const jx = x + (rand() - 0.5) * jitter
    const jy = y + (rand() - 0.5) * jitter
    pts.push(jx, jy, surfaceZ(jx, jy))
    shade.push(bright, bright, bright)
  }

  // Piel: puntos dispersos y desparejos (no una rejilla), más tenues.
  let placed = 0
  while (placed < fillCount) {
    const y = -0.95 + rand() * 1.83
    const x = (rand() * 2 - 1) * halfWidth(y) * 0.95
    add(x, y, 0.55 + rand() * 0.35, 0)
    placed++
  }

  // Líneas de expresión: densas y más brillantes.
  for (const { curve, n, mirror } of featureCurves()) {
    for (let i = 0; i < n; i++) {
      const [x, y] = curve(i / (n - 1))
      add(x, y, 0.9 + rand() * 0.1, 0.012)
      if (mirror) add(-x, y, 0.9 + rand() * 0.1, 0.012)
    }
  }

  // Pesos de animación según la posición de cada punto.
  const count = pts.length / 3
  const jaw = new Float32Array(count)
  const upper = new Float32Array(count)
  const corners = new Float32Array(count)
  const lids = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    const x = pts[i * 3]
    const y = pts[i * 3 + 1]
    // Todo lo que está bajo la línea de la boca baja con la mandíbula; la
    // línea misma se queda con el labio de arriba, así se abre un hueco.
    // Angosta (σ≈0.17): abre en óvalo como una boca, no de mejilla a mejilla.
    jaw[i] = smooth(-0.495, -0.51, y) * smooth(-1.02, -0.62, y) * Math.exp(-(x * x) / (2 * 0.17 * 0.17))
    upper[i] = g(x, y + 0.45, 0.17, 0.035)
    corners[i] = g(Math.abs(x) - 0.18, y + 0.48, 0.045, 0.04)
    lids[i] = g(Math.abs(x) - 0.26, y - 0.035, 0.12, 0.025)
  }
  return { base: new Float32Array(pts), colors: new Float32Array(shade), jaw, upperLip: upper, corners, lids }
}

/** Triangulito como "sprite" de cada punto, como en la referencia. */
function triangleTexture(): THREE.Texture {
  const c = document.createElement('canvas')
  c.width = c.height = 32
  const ctx = c.getContext('2d')
  if (ctx) {
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.moveTo(16, 4)
    ctx.lineTo(29, 27)
    ctx.lineTo(3, 27)
    ctx.closePath()
    ctx.fill()
  }
  const tex = new THREE.CanvasTexture(c)
  // Sin mipmaps: al achicarse, el triángulo se promediaba con el fondo
  // transparente, quedaba bajo el alphaTest y la mayoría de los puntos se
  // descartaban (se veían diminutos y apagados).
  tex.generateMipmaps = false
  tex.minFilter = THREE.LinearFilter
  tex.magFilter = THREE.LinearFilter
  return tex
}

const MOOD_COLOR: Record<FaceMood, THREE.Color> = {
  idle: new THREE.Color('#5fd3f3'),
  listening: new THREE.Color('#8be9ff'),
  thinking: new THREE.Color('#a5b4fc'),
  speaking: new THREE.Color('#7fe3ff'),
  happy: new THREE.Color('#86efac'),
  confused: new THREE.Color('#fda4af'),
}

export default function PointFace3D({ mood, volume = 0, getLevel, size = 280 }: Props) {
  const mount = useRef<HTMLDivElement>(null)
  const moodRef = useRef(mood)
  const volumeRef = useRef(volume)
  const levelRef = useRef(getLevel)
  const [failed, setFailed] = useState(false)
  moodRef.current = mood
  volumeRef.current = volume
  levelRef.current = getLevel

  useEffect(() => {
    const el = mount.current
    if (!el) return
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      setFailed(true)
      return
    }
    const W = size
    const H = Math.round(size * 1.15)
    const small = window.innerWidth < 640
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, small ? 1.5 : 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(30, W / H, 0.1, 20)
    camera.position.set(0, -0.05, 4.2)

    const face = buildFace(small ? 2200 : 3000)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(face.base, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(face.colors, 3))
    // Pesos por punto (mandíbula, labio de arriba, sonrisa, parpadeo). La
    // deformación la hace la GPU: por cuadro solo cambian 3 números.
    geo.setAttribute('aJaw', new THREE.BufferAttribute(face.jaw, 1))
    geo.setAttribute('aUpper', new THREE.BufferAttribute(face.upperLip, 1))
    geo.setAttribute('aCorner', new THREE.BufferAttribute(face.corners, 1))
    geo.setAttribute('aLid', new THREE.BufferAttribute(face.lids, 1))
    const uniforms = { uOpen: { value: 0 }, uSmile: { value: 0 }, uBlink: { value: 0 } }

    const sprite = triangleTexture()
    const mat = new THREE.PointsMaterial({
      size: 0.042,
      sizeAttenuation: true,
      vertexColors: true,
      map: sprite,
      alphaTest: 0.25,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      color: MOOD_COLOR.idle.clone(),
    })
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms)
      shader.vertexShader = shader.vertexShader
        .replace(
          '#include <common>',
          `#include <common>
attribute float aJaw;
attribute float aUpper;
attribute float aCorner;
attribute float aLid;
uniform float uOpen;
uniform float uSmile;
uniform float uBlink;`,
        )
        .replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
transformed.y += -uOpen * 0.15 * aJaw + uOpen * 0.022 * aUpper + uSmile * 0.03 * aCorner - uBlink * 0.04 * aLid;
transformed.z -= uOpen * 0.03 * aJaw;`,
        )
    }
    const head = new THREE.Points(geo, mat)
    scene.add(head)

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let visible = true
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
    io.observe(el)

    let open = 0
    let smile = 0
    let blink = 0
    let nextBlink = performance.now() + 2500
    let raf = 0

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      if (!visible) return
      const t = now / 1000
      const m = moodRef.current

      // Boca: voz real al hablar, tu voz al escuchar.
      // window.__iaradioFaceTest (0–1) solo lo pone una prueba automática: el
      // navegador de pruebas no tiene bocina y el volumen medido sería 0.
      const forced = (window as Window & { __iaradioFaceTest?: number }).__iaradioFaceTest
      const target =
        typeof forced === 'number' ? forced
          : m === 'speaking' ? (levelRef.current?.() ?? 0)
            : m === 'listening' ? volumeRef.current * 0.7
              : 0
      open += (target - open) * (target > open ? 0.55 : 0.22)
      smile += ((m === 'happy' ? 1 : m === 'idle' ? 0.2 : 0) - smile) * 0.08
      if (now > nextBlink) {
        blink = 1
        nextBlink = now + 2500 + Math.random() * 3000
      }
      blink *= 0.82
      uniforms.uOpen.value = open
      uniforms.uSmile.value = smile
      uniforms.uBlink.value = blink

      // Cabeza: casi de frente, como la referencia; gira poquito, asiente al
      // escuchar y mira arriba al pensar.
      const sway = reduceMotion ? 0 : 1
      const yaw = Math.sin(t * 0.45) * 0.2 * sway
      const pitch =
        m === 'thinking' ? -0.2 : m === 'listening' ? 0.06 + Math.sin(t * 2.2) * 0.03 * sway : Math.sin(t * 0.33) * 0.035 * sway
      const roll = m === 'thinking' ? 0.08 : m === 'confused' ? -0.1 : 0
      head.rotation.y += (yaw - head.rotation.y) * 0.06
      head.rotation.x += (pitch - head.rotation.x) * 0.06
      head.rotation.z += (roll - head.rotation.z) * 0.06
      mat.color.lerp(MOOD_COLOR[m], 0.06)

      renderer.render(scene, camera)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      geo.dispose()
      mat.dispose()
      sprite.dispose()
      renderer.dispose()
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement)
    }
  }, [size])

  if (failed) return <BotFace mood={mood} volume={volume} size={Math.round(size * 0.6)} />

  return (
    <div
      ref={mount}
      role="img"
      aria-label={mood === 'speaking' ? 'Asistente hablando' : mood === 'listening' ? 'Asistente escuchando' : 'Asistente'}
      style={{ width: size, height: Math.round(size * 1.15) }}
      className="select-none"
    />
  )
}
